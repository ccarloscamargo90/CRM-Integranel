"""Tests de validación de contacto."""

from __future__ import annotations

from src.audit.contacto import (
    _normaliza_telefono_mx,
    check_anio_alta_denue_razonable,
    check_direccion_sospechosa,
    check_email_formato,
    check_telefono_formato_mx,
)
from src.core.models import Establecimiento


def _crear_est(db, **kwargs) -> Establecimiento:
    defaults = {
        "hash_dedup": "contacto-default",
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


# ---------- _normaliza_telefono_mx ----------


def test_normaliza_telefono_10_digitos():
    assert _normaliza_telefono_mx("5551234567") == "5551234567"


def test_normaliza_telefono_con_lada_52():
    assert _normaliza_telefono_mx("525551234567") == "5551234567"


def test_normaliza_telefono_con_lada_521_movil():
    assert _normaliza_telefono_mx("5215551234567") == "5551234567"


def test_normaliza_telefono_con_simbolos():
    assert _normaliza_telefono_mx("+52 (55) 5123-4567") == "5551234567"


def test_normaliza_telefono_none():
    assert _normaliza_telefono_mx(None) is None
    assert _normaliza_telefono_mx("") is None


# ---------- check_telefono_formato_mx ----------


def test_telefono_valido(db):
    _crear_est(db, hash_dedup="c1", telefono="5551234567")
    h = check_telefono_formato_mx(db)
    assert h.total_problemas == 0


def test_telefono_corto_se_marca(db):
    _crear_est(db, hash_dedup="c2", telefono="123")
    h = check_telefono_formato_mx(db)
    assert h.severidad == "warning"
    assert h.total_problemas == 1


# ---------- check_email_formato ----------


def test_email_valido(db):
    _crear_est(db, hash_dedup="c3", email="hola@mundo.mx")
    h = check_email_formato(db)
    assert h.total_problemas == 0


def test_email_invalido(db):
    _crear_est(db, hash_dedup="c4", email="no-es-email")
    h = check_email_formato(db)
    assert h.total_problemas == 1


# ---------- check_direccion_sospechosa ----------


def test_direccion_domicilio_conocido(db):
    _crear_est(db, hash_dedup="c5", direccion="Domicilio conocido", numero_exterior="1")
    h = check_direccion_sospechosa(db)
    assert h.total_problemas == 1


def test_direccion_sin_numero_exterior(db):
    _crear_est(
        db, hash_dedup="c6", direccion="Avenida Reforma esquina con Insurgentes"
    )
    # numero_exterior NULL
    h = check_direccion_sospechosa(db)
    assert h.total_problemas == 1


def test_direccion_completa(db):
    _crear_est(
        db,
        hash_dedup="c7",
        direccion="Avenida Reforma 222",
        numero_exterior="222",
    )
    h = check_direccion_sospechosa(db)
    assert h.total_problemas == 0


# ---------- check_anio_alta_denue_razonable ----------


def test_anio_alta_razonable(db):
    _crear_est(db, hash_dedup="c8", anio_alta_denue=2018)
    h = check_anio_alta_denue_razonable(db)
    assert h.total_problemas == 0


def test_anio_alta_demasiado_viejo(db):
    _crear_est(db, hash_dedup="c9", anio_alta_denue=1995)
    h = check_anio_alta_denue_razonable(db)
    assert h.total_problemas == 1


def test_anio_alta_futuro(db):
    _crear_est(db, hash_dedup="c10", anio_alta_denue=2099)
    h = check_anio_alta_denue_razonable(db)
    assert h.total_problemas == 1
