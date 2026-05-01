"""Tests del orquestador de auditoría."""

from __future__ import annotations

import pytest

from src.audit.runner import CHEQUEOS_DEFAULT, run_all, run_subset
from src.core.models import Establecimiento


def _crear_est(db, **kwargs) -> Establecimiento:
    defaults = {
        "hash_dedup": "runner-default",
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


def test_run_all_db_vacia(db):
    """Sin data, el reporte sale aprobado y todo en 0."""
    reporte = run_all(db)
    assert reporte.total_registros == 0
    assert reporte.aprobado is True
    assert len(reporte.errores) == 0
    assert len(reporte.hallazgos) > 10  # múltiples chequeos


def test_run_all_con_un_registro_valido(db):
    _crear_est(
        db,
        hash_dedup="r1",
        latitud=19.43,
        longitud=-99.13,
        telefono="5551234567",
        anio_alta_denue=2018,
    )
    reporte = run_all(db)
    assert reporte.total_registros == 1
    assert reporte.aprobado, f"Errores: {[h.chequeo for h in reporte.errores]}"


def test_run_all_con_registro_problematico(db):
    """Registro con SCIAN inválido, lat/lon fuera bbox, sin contacto."""
    _crear_est(
        db,
        hash_dedup="r2",
        scian_codigo="999999",  # fuera de objetivo
        latitud=45.0,  # fuera de bbox MX
        longitud=-50.0,  # fuera de bbox MX
        canales=["Tortillerias"],  # OK pero scian no es objetivo
    )
    reporte = run_all(db)
    assert reporte.aprobado is False
    chequeos_con_error = {h.chequeo for h in reporte.errores}
    assert "scian.fuera_objetivo" in chequeos_con_error
    assert "geo.fuera_bbox_mx" in chequeos_con_error


def test_run_subset_solo_corre_lo_pedido(db):
    _crear_est(db, hash_dedup="r3")
    reporte = run_subset(db, ["scian.fuera_objetivo", "scian.canales_vacio"])
    assert len(reporte.hallazgos) == 2
    assert {h.chequeo for h in reporte.hallazgos} == {
        "scian.fuera_objetivo",
        "scian.canales_vacio",
    }


def test_run_subset_chequeo_inexistente_falla(db):
    with pytest.raises(ValueError, match="no registrados"):
        run_subset(db, ["chequeo.inventado"])


def test_run_all_omitir(db):
    """`omitir` skipea chequeos ineficientes en universos chicos."""
    _crear_est(db, hash_dedup="r4")
    reporte = run_all(db, omitir={"duplicates.fuzzy"})
    assert "duplicates.fuzzy" not in {h.chequeo for h in reporte.hallazgos}


def test_chequeos_default_no_vacio():
    assert len(CHEQUEOS_DEFAULT) >= 15


def test_resumen_serializa_ok(db):
    _crear_est(db, hash_dedup="r5")
    reporte = run_all(db)
    resumen = reporte.resumen()
    assert {"fecha", "universo", "total_registros", "n_hallazgos"} <= resumen.keys()


def test_reporte_serializa_a_json(db):
    """ReporteAuditoria es Pydantic — debe serializar a JSON limpio."""
    _crear_est(db, hash_dedup="r6")
    reporte = run_all(db)
    json_str = reporte.model_dump_json()
    assert "establecimientos" in json_str
    assert "hallazgos" in json_str
