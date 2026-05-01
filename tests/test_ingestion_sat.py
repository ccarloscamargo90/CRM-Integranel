"""Tests del parser SAT 69-B + cruce de riesgo."""

from __future__ import annotations

from sqlalchemy import text

from src.enrichment.cruzar_69b import cruzar_riesgo_69b
from src.ingestion.sat_publica import _parse_fecha, iter_registros

SAMPLE_CSV = (
    '"Aviso legal omitido"\n'
    "Listado completo de contribuyentes (Artículo 69-B del CFF)\n"
    "No,RFC,Nombre del Contribuyente,Situación del contribuyente,"
    "Número y fecha de oficio global de presunción SAT,Publicación página SAT presuntos,"
    "Número y fecha de oficio global de presunción DOF,Publicación DOF presuntos,"
    "Número y fecha de oficio global de contribuyentes que desvirtuaron SAT,"
    "Publicación página SAT desvirtuados,"
    "Número y fecha de oficio global de contribuyentes que desvirtuaron DOF,"
    "Publicación DOF desvirtuados,"
    "Número y fecha de oficio global de definitivos SAT,"
    "Publicación página SAT definitivos,"
    "Número y fecha de oficio global de definitivos DOF,"
    "Publicación DOF definitivos,"
    "Número y fecha de oficio global de sentencia favorable SAT,"
    "Publicación página SAT sentencia favorable,"
    "Número y fecha de oficio global de sentencia favorable DOF,"
    "Publicación DOF sentencia favorable\n"
    '1,FAKE010101AA1,"FAKE EMPRESA DEFINITIVA SA DE CV",Definitivo,'
    '500-X de fecha 1 de enero de 2024,01/01/2024,500-X de fecha 1 de enero de 2024,15/01/2024,'
    ',,,'
    ',500-Y de fecha 1 de junio de 2024,01/06/2024,500-Y,30/06/2024'
    ',,,,\n'
    '2,FAKE020202BB2,"FAKE LIMPIA SA DE CV",Sentencia Favorable,'
    '500-A,01/01/2023,500-A,15/01/2023,500-B,01/06/2023,500-B,30/06/2023'
    ',500-C,01/12/2023,500-C,15/12/2023,500-D,01/03/2024,500-D,15/03/2024\n'
)


def test_parse_fecha_acepta_formatos():
    import datetime as dt

    assert _parse_fecha("01/06/2024") == dt.date(2024, 6, 1)
    assert _parse_fecha("2024-06-01") == dt.date(2024, 6, 1)
    assert _parse_fecha("") is None
    assert _parse_fecha(None) is None
    assert _parse_fecha("texto") is None


def test_iter_registros_skipea_2_primeras_lineas():
    registros = list(iter_registros(SAMPLE_CSV.encode("latin-1")))
    assert len(registros) == 2
    assert registros[0]["rfc"] == "FAKE010101AA1"
    assert registros[0]["situacion"] == "Definitivo"
    assert registros[1]["situacion"] == "Sentencia Favorable"


def test_iter_registros_extrae_fecha_publicacion_priorizada():
    """La fecha priorizada es DOF Definitivos > Desvirtuados > Sentencia > Presuntos."""
    registros = list(iter_registros(SAMPLE_CSV.encode("latin-1")))
    # Definitivo: toma fecha de DOF definitivos
    assert registros[0]["fecha_publicacion"] == "30/06/2024"
    # Sentencia Favorable: como tiene definitivos también, toma DOF definitivos
    assert registros[1]["fecha_publicacion"] == "15/12/2023"


def test_cruzar_riesgo_69b_marca_por_razon_social(db):
    """Inserta un establecimiento y un row 69-B con razón social coincidente."""
    db.execute(
        text(
            "INSERT INTO establecimientos (hash_dedup, nombre, nombre_norm, "
            "scian_codigo, razon_social) VALUES "
            "('h1', 'Tort A', 'tort a', '311830', 'EMPRESA RIESGO SA DE CV')"
        )
    )
    db.execute(
        text(
            "INSERT INTO sat_lista_69b (rfc, razon_social, estatus, fecha_publicacion_dof) "
            "VALUES ('FAKE0101', 'EMPRESA RIESGO SA DE CV', 'Definitivo', '2024-01-15')"
        )
    )
    db.flush()

    res = cruzar_riesgo_69b(db)
    assert res["marcados_por_razon"] == 1
    assert res["marcados_riesgo"] == 1

    riesgo = db.execute(
        text("SELECT riesgo_69b, riesgo_69b_fecha FROM establecimientos WHERE nombre='Tort A'")
    ).one()
    assert riesgo.riesgo_69b is True
    assert riesgo.riesgo_69b_fecha is not None


def test_cruzar_no_marca_si_estatus_desvirtuado(db):
    """Si el estatus es Desvirtuado, NO se marca riesgo."""
    db.execute(
        text(
            "INSERT INTO establecimientos (hash_dedup, nombre, nombre_norm, "
            "scian_codigo, razon_social) VALUES "
            "('h2', 'Tort B', 'tort b', '311830', 'EMPRESA LIMPIA SA DE CV')"
        )
    )
    db.execute(
        text(
            "INSERT INTO sat_lista_69b (rfc, razon_social, estatus, fecha_publicacion_dof) "
            "VALUES ('FAKE0202', 'EMPRESA LIMPIA SA DE CV', 'Desvirtuado', '2024-01-15')"
        )
    )
    db.flush()

    res = cruzar_riesgo_69b(db)
    assert res["marcados_riesgo"] == 0

    riesgo = db.execute(
        text("SELECT riesgo_69b FROM establecimientos WHERE nombre='Tort B'")
    ).scalar()
    assert riesgo is False
