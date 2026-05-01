"""Tests del pipeline de ingestión — upsert, geom, log, compliance."""

from __future__ import annotations

from sqlalchemy import select, text

from src.core.models import Establecimiento
from src.ingestion.denue_csv_parser import csv_row_to_establecimiento_dict
from src.ingestion.denue_pipeline import actualizar_geom, upsert_batch


def _csv_row(clee: str, nombre: str, lat: float, lon: float) -> dict[str, str]:
    """Fila CSV mínima con los campos que el parser necesita."""
    return {
        "clee": clee,
        "nom_estab": nombre,
        "raz_social": "",
        "codigo_act": "311830",
        "nombre_act": "Tortillerías",
        "per_ocu": "0 a 5 personas",
        "cod_postal": "00000",
        "cve_ent": "23",
        "entidad": "Quintana Roo",
        "cve_mun": "005",
        "latitud": str(lat),
        "longitud": str(lon),
        "fecha_alta": "2018-05",
    }


def _raw(clee: str, nombre: str, lat: float, lon: float) -> dict:
    """Wrapper compatible con tests viejos — usa csv parser."""
    return csv_row_to_establecimiento_dict(_csv_row(clee, nombre, lat, lon))


def test_upsert_inserta_filas_nuevas(db):
    registros = [
        _raw("23005311830000010000000000U7", "Tort A", 19.0, -88.5),
        _raw("23005311830000020000000000U8", "Tort B", 19.1, -88.6),
    ]
    ins, upd = upsert_batch(db, registros)
    assert ins == 2
    assert upd == 0
    assert db.execute(select(Establecimiento.id).where(
        Establecimiento.clee == "23005311830000010000000000U7"
    )).scalar_one_or_none() is not None


def test_upsert_actualiza_si_clee_existe(db):
    """Re-correr el mismo CLEE actualiza, no duplica."""
    r1 = _raw("23005311830000010000000000U7", "Tort Original", 19.0, -88.5)
    r2 = _raw("23005311830000010000000000U7", "Tort Renombrada", 19.0, -88.5)

    ins1, _ = upsert_batch(db, [r1])
    ins2, upd2 = upsert_batch(db, [r2])
    assert ins1 == 1
    assert ins2 == 0
    assert upd2 == 1

    nombre = db.execute(
        select(Establecimiento.nombre).where(
            Establecimiento.clee == "23005311830000010000000000U7"
        )
    ).scalar_one()
    assert nombre == "Tort Renombrada"


def test_upsert_preserva_campos_manuales(db):
    """Si el operador editó vendedor_id o estado_pipeline, el upsert NO lo pisa."""
    r = _raw("23005311830000010000000000U7", "Tort", 19.0, -88.5)
    upsert_batch(db, [r])

    db.execute(
        text(
            "UPDATE establecimientos SET estado_pipeline='visitado', notas='dueño don juan' "
            "WHERE clee = :clee"
        ),
        {"clee": "23005311830000010000000000U7"},
    )
    db.flush()

    upsert_batch(db, [r])
    row = db.execute(
        text("SELECT estado_pipeline, notas FROM establecimientos WHERE clee=:clee"),
        {"clee": "23005311830000010000000000U7"},
    ).one()
    assert row.estado_pipeline == "visitado"
    assert row.notas == "dueño don juan"


def test_actualizar_geom_rellena_donde_es_null(db):
    r = _raw("23005311830000010000000000U7", "Tort", 19.0, -88.5)
    upsert_batch(db, [r])

    geom_inicial = db.execute(
        text("SELECT geom FROM establecimientos WHERE clee=:c"),
        {"c": "23005311830000010000000000U7"},
    ).scalar()
    assert geom_inicial is None

    n = actualizar_geom(db)
    assert n == 1

    coords = db.execute(
        text("""
            SELECT ST_X(geom::geometry) AS lon, ST_Y(geom::geometry) AS lat
            FROM establecimientos WHERE clee=:c
        """),
        {"c": "23005311830000010000000000U7"},
    ).one()
    assert coords.lon == -88.5
    assert coords.lat == 19.0


def test_upsert_fusiona_fuentes(db):
    """Si el registro ya tiene 'Manual', se preserva al hacer upsert con DENUE."""
    r = _raw("23005311830000010000000000U7", "Tort", 19.0, -88.5)
    upsert_batch(db, [r])

    db.execute(
        text(
            "UPDATE establecimientos SET fuentes = ARRAY['Manual', 'DENUE_CSV']::text[] "
            "WHERE clee=:c"
        ),
        {"c": "23005311830000010000000000U7"},
    )
    db.flush()

    upsert_batch(db, [r])
    fuentes = db.execute(
        text("SELECT fuentes FROM establecimientos WHERE clee=:c"),
        {"c": "23005311830000010000000000U7"},
    ).scalar()
    assert set(fuentes) == {"Manual", "DENUE_CSV"}
