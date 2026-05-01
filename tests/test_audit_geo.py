"""Tests de auditoría geográfica."""

from __future__ import annotations

from src.audit.geo_anomalies import (
    check_coords_nulas_o_cero,
    check_fuera_bbox_mx,
    check_lat_lon_invertidas,
)
from src.core.models import Establecimiento


def _crear_est(db, **kwargs) -> Establecimiento:
    defaults = {
        "hash_dedup": "geo-default",
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


def test_coords_nulas_detecta(db):
    """Establecimiento sin coords es flag warning."""
    _crear_est(db, hash_dedup="g1")  # sin lat/lon
    _crear_est(db, hash_dedup="g2", latitud=19.43, longitud=-99.13)  # CDMX OK
    h = check_coords_nulas_o_cero(db)
    assert h.total_problemas == 1
    assert h.severidad == "warning"


def test_coords_cero_detecta(db):
    """Coords (0, 0) literales son sospechosas."""
    _crear_est(db, hash_dedup="g3", latitud=0.0, longitud=0.0)
    h = check_coords_nulas_o_cero(db)
    assert h.total_problemas == 1


def test_fuera_bbox_detecta_lat_invalida(db):
    """Lat fuera de rango MX → error."""
    _crear_est(
        db, hash_dedup="g4", latitud=45.0, longitud=-99.13
    )  # 45 está fuera de 14.5–32.7
    h = check_fuera_bbox_mx(db)
    assert h.severidad == "error"
    assert h.total_problemas == 1


def test_fuera_bbox_acepta_cdmx(db):
    """CDMX (lat 19.43, lon -99.13) debe pasar."""
    _crear_est(db, hash_dedup="g5", latitud=19.43, longitud=-99.13)
    h = check_fuera_bbox_mx(db)
    assert h.total_problemas == 0


def test_lat_lon_invertidas(db):
    """Lat=-99 (parece longitud), lon=19 (parece latitud) → flag."""
    _crear_est(db, hash_dedup="g6", latitud=-99.13, longitud=19.43)
    h = check_lat_lon_invertidas(db)
    assert h.severidad == "error"
    assert h.total_problemas == 1
