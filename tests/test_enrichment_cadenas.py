"""Tests del detector de cadenas."""

from __future__ import annotations

from sqlalchemy import select

from src.core.models import Cadena, Establecimiento
from src.enrichment.cadenas import _clave_marca, detectar_cadenas


def _crear_est(db, **kwargs) -> Establecimiento:
    defaults = {
        "hash_dedup": "default-hash",
        "nombre": "Test",
        "nombre_norm": "test",
        "scian_codigo": "311830",
        "canales": ["Tortillerias"],
    }
    defaults.update(kwargs)
    est = Establecimiento(**defaults)
    db.add(est)
    db.flush()
    return est


def test_clave_marca_quita_genericas():
    assert _clave_marca("tortilleria la esperanza") == "esperanza"


def test_clave_marca_quita_conectores():
    assert _clave_marca("molino de don pedro") == "don pedro"


def test_clave_marca_solo_genericas_devuelve_none():
    assert _clave_marca("tortilleria la") is None
    assert _clave_marca("la el") is None


def test_clave_marca_filtra_2_chars():
    assert _clave_marca("ab cd ef esperanza") == "esperanza"


def test_detectar_cadenas_3_sucursales(db):
    """3 establecimientos con misma marca → cadena creada."""
    for i in range(3):
        _crear_est(
            db,
            hash_dedup=f"chain-{i}",
            nombre=f"Tortillería La Esperanza {i+1}",
            nombre_norm=f"tortilleria la esperanza {i+1}",
        )
    detectar_cadenas(db)
    db.flush()

    cadenas = db.execute(select(Cadena)).scalars().all()
    assert len(cadenas) >= 1
    cadena = next((c for c in cadenas if "esperanza" in c.nombre_grupo_norm), None)
    assert cadena is not None
    assert cadena.sucursales_count == 3
    assert cadena.canal_principal == "Tortillerias"

    # Verifica que los 3 establecimientos quedaron vinculados
    vinculados = db.execute(
        select(Establecimiento).where(Establecimiento.cadena_id == cadena.id)
    ).scalars().all()
    assert len(vinculados) == 3


def test_detectar_cadenas_2_no_es_cadena(db):
    """2 establecimientos con misma marca → NO es cadena (umbral=3)."""
    for i in range(2):
        _crear_est(
            db,
            hash_dedup=f"single-{i}",
            nombre=f"Tortillería Sola {i+1}",
            nombre_norm=f"tortilleria sola {i+1}",
        )
    detectar_cadenas(db)
    cadenas = db.execute(select(Cadena)).scalars().all()
    cadena_sola = next((c for c in cadenas if "sola" in c.nombre_grupo_norm), None)
    assert cadena_sola is None


def test_detectar_cadenas_idempotente(db):
    """Re-correr no duplica cadenas."""
    for i in range(3):
        _crear_est(
            db,
            hash_dedup=f"idem-{i}",
            nombre=f"Tortillería La Esperanza {i+1}",
            nombre_norm=f"tortilleria la esperanza {i+1}",
        )
    detectar_cadenas(db)
    n_cadenas_1 = db.execute(select(Cadena)).scalars().all()
    detectar_cadenas(db)
    n_cadenas_2 = db.execute(select(Cadena)).scalars().all()
    assert len(n_cadenas_1) == len(n_cadenas_2)
