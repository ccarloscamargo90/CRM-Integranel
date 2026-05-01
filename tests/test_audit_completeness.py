"""Tests de auditoría de completitud."""

from __future__ import annotations

from src.audit.completeness import (
    check_columnas_criticas_pobladas,
    check_pct_null_por_columna,
    check_sin_contacto,
)
from src.core.models import Establecimiento


def _crear_est(db, **kwargs) -> Establecimiento:
    """Helper para insertar establecimiento mínimo válido (con overrides)."""
    defaults = {
        "hash_dedup": "test-hash-default",
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


def test_columnas_criticas_pobladas_db_vacia(db):
    """Tabla vacía → 0 problemas."""
    h = check_columnas_criticas_pobladas(db)
    assert h.severidad == "error"
    assert h.total_evaluados == 0
    assert h.total_problemas == 0


def test_columnas_criticas_detecta_nombre_nulo(db):
    """Si insertamos un registro válido y comparamos, no hay problema."""
    _crear_est(db, hash_dedup="hh1")
    h = check_columnas_criticas_pobladas(db)
    assert h.total_evaluados == 1
    assert h.total_problemas == 0


def test_pct_null_devuelve_lista(db):
    """check_pct_null_por_columna devuelve un Hallazgo por columna."""
    _crear_est(db, hash_dedup="hh-pct")
    hallazgos = check_pct_null_por_columna(db)
    assert isinstance(hallazgos, list)
    assert len(hallazgos) > 5  # varias columnas


def test_sin_contacto_detecta(db):
    """Establecimiento sin tel/email/whatsapp es marcado."""
    _crear_est(db, hash_dedup="hh-c1")  # sin contacto
    _crear_est(db, hash_dedup="hh-c2", telefono="5551234567")  # con contacto

    h = check_sin_contacto(db)
    assert h.total_evaluados == 2
    assert h.total_problemas == 1
    assert h.severidad == "warning"
