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


def test_detectar_cadenas_corporativas_por_razon_social(db):
    """3 establecimientos con misma razón social → cadena corporativa."""
    for i in range(3):
        _crear_est(
            db,
            hash_dedup=f"corp-{i}",
            nombre=f"Sucursal {i+1}",
            razon_social="ALIMENTOS PLIEGO SA DE CV",
        )
    detectar_cadenas(db)
    db.flush()

    cadenas = db.execute(select(Cadena)).scalars().all()
    cadena = next((c for c in cadenas if "alimentos pliego" in c.nombre_grupo_norm), None)
    assert cadena is not None
    assert cadena.sucursales_count == 3
    assert cadena.tipo == "cadena_corporativa"


def test_detectar_cadenas_marca_solo_si_se_pide(db):
    """Sin `incluir_marca_residual`, no agrupa por marca residual."""
    for i in range(3):
        _crear_est(
            db,
            hash_dedup=f"marca-{i}",
            nombre=f"Tortillería La Esperanza {i+1}",
            nombre_norm=f"tortilleria la esperanza {i+1}",
        )
    detectar_cadenas(db)
    cadenas = db.execute(select(Cadena)).scalars().all()
    assert not any("esperanza" in (c.nombre_grupo_norm or "") for c in cadenas)

    detectar_cadenas(db, incluir_marca_residual=True)
    cadenas = db.execute(select(Cadena)).scalars().all()
    cadena = next((c for c in cadenas if "esperanza" in (c.nombre_grupo_norm or "")), None)
    assert cadena is not None
    assert cadena.tipo == "heuristica"


def test_detectar_cadenas_2_no_es_cadena(db):
    """2 establecimientos con misma razón social → NO es cadena (umbral=3)."""
    for i in range(2):
        _crear_est(
            db,
            hash_dedup=f"single-{i}",
            nombre=f"Tortillería Sola {i+1}",
            razon_social="EMPRESA CHICA SA DE CV",
        )
    detectar_cadenas(db)
    cadenas = db.execute(select(Cadena)).scalars().all()
    cadena = next((c for c in cadenas if "empresa chica" in c.nombre_grupo_norm), None)
    assert cadena is None


def test_detectar_cadenas_idempotente(db):
    """Re-correr no duplica cadenas."""
    for i in range(3):
        _crear_est(
            db,
            hash_dedup=f"idem-{i}",
            nombre=f"Sucursal {i+1}",
            razon_social="MOLINERA TEST SA DE CV",
        )
    detectar_cadenas(db)
    n_cadenas_1 = db.execute(select(Cadena)).scalars().all()
    detectar_cadenas(db)
    n_cadenas_2 = db.execute(select(Cadena)).scalars().all()
    assert len(n_cadenas_1) == len(n_cadenas_2)
