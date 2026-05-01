"""Tests de auditoría de SCIAN y consistencia de canales."""

from __future__ import annotations

from src.audit.scian import (
    check_canal_consistente_con_scian,
    check_canales_no_vacio,
    check_scian_en_objetivo,
    conteo_por_scian,
)
from src.core.models import Establecimiento


def _crear_est(db, **kwargs) -> Establecimiento:
    defaults = {
        "hash_dedup": "scian-default",
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


def test_scian_objetivo_acepta_los_8(db):
    """Insertar uno de los 8 SCIAN objetivo no genera error."""
    _crear_est(db, hash_dedup="s1", scian_codigo="311830")  # tortillería
    _crear_est(
        db, hash_dedup="s2", scian_codigo="311110", canales=["AlimentoBalanceado"]
    )
    _crear_est(
        db, hash_dedup="s3", scian_codigo="813110", canales=["AsociacionesAgropecuarias"]
    )
    h = check_scian_en_objetivo(db)
    assert h.total_problemas == 0


def test_scian_fuera_objetivo_se_marca(db):
    """SCIAN no listado → error."""
    _crear_est(db, hash_dedup="s4", scian_codigo="999999", canales=["Tortillerias"])
    h = check_scian_en_objetivo(db)
    assert h.severidad == "error"
    assert h.total_problemas == 1


def test_canal_inconsistente_se_marca(db):
    """SCIAN tortillería con canal AlimentoBalanceado → error."""
    _crear_est(
        db, hash_dedup="s5", scian_codigo="311830", canales=["AlimentoBalanceado"]
    )
    h = check_canal_consistente_con_scian(db)
    assert h.severidad == "error"
    assert h.total_problemas == 1


def test_canal_consistente_ok(db):
    """SCIAN tortillería con canal Tortillerias → 0 problemas."""
    _crear_est(db, hash_dedup="s6", scian_codigo="311830", canales=["Tortillerias"])
    h = check_canal_consistente_con_scian(db)
    assert h.total_problemas == 0


def test_canales_vacio_se_marca(db):
    """Establecimiento con canales=[] → error."""
    _crear_est(db, hash_dedup="s7", scian_codigo="311830", canales=[])
    h = check_canales_no_vacio(db)
    assert h.severidad == "error"
    assert h.total_problemas == 1


def test_conteo_por_scian_es_info(db):
    """Distribución es informativa, no error."""
    _crear_est(db, hash_dedup="s8", scian_codigo="311830")
    _crear_est(db, hash_dedup="s9", scian_codigo="311830")
    _crear_est(
        db, hash_dedup="s10", scian_codigo="311110", canales=["AlimentoBalanceado"]
    )
    h = conteo_por_scian(db)
    assert h.severidad == "info"
    # 2 SCIAN distintos
    assert len(h.ejemplos) == 2
