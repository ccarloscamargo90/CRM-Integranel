"""Tests del módulo ARCO."""

from __future__ import annotations

import datetime as dt

import pytest

from src.compliance.arco import (
    _calcular_fecha_limite,
    listar_pendientes,
    marcar_vencidas,
    registrar_solicitud,
    responder_solicitud,
)


def test_calcular_fecha_limite_skipea_fines_de_semana():
    # Recepción viernes → 20 días hábiles después es viernes 4 semanas después
    viernes = dt.date(2026, 5, 1)  # viernes
    limite = _calcular_fecha_limite(viernes, dias_habiles=5)
    # 5 días hábiles después de un viernes = viernes siguiente
    assert limite == dt.date(2026, 5, 8)


def test_calcular_fecha_limite_20_dias():
    lunes = dt.date(2026, 5, 4)  # lunes
    limite = _calcular_fecha_limite(lunes, dias_habiles=20)
    # 20 días hábiles = 4 semanas después
    assert limite == dt.date(2026, 6, 1)


def test_registrar_solicitud_crea_folio_y_calcula_limite(db):
    res = registrar_solicitud(
        db,
        tipo="acceso",
        solicitante_nombre="Juan Pérez",
        solicitante_rfc="PEPJ800101AAA",
        descripcion="Quiero saber qué datos tienen sobre mi tortillería",
    )
    assert res["folio"].startswith("ARCO-")
    assert res["fecha_limite_respuesta"] > dt.date.today()


def test_registrar_solicitud_tipo_invalido_rechaza(db):
    with pytest.raises(ValueError, match="Tipo inválido"):
        registrar_solicitud(
            db,
            tipo="otro",
            solicitante_nombre="X",
            descripcion="Y",
        )


def test_listar_pendientes_solo_recibida_y_en_proceso(db):
    registrar_solicitud(
        db,
        tipo="cancelacion",
        solicitante_nombre="María López",
        descripcion="Borren mis datos",
    )
    pendientes = listar_pendientes(db)
    nuevos = [p for p in pendientes if "María" in p["solicitante"]]
    assert len(nuevos) == 1
    assert nuevos[0]["estatus"] == "recibida"


def test_responder_solicitud(db):
    res = registrar_solicitud(
        db,
        tipo="acceso",
        solicitante_nombre="Pedro Ramírez",
        descripcion="Acceso a mis datos",
    )
    folio = res["folio"]

    final = responder_solicitud(
        db,
        folio=folio,
        respuesta="Se adjunta CSV con los datos del titular.",
        procedente=True,
    )
    assert final["estatus_final"] == "respondida"


def test_marcar_vencidas_no_afecta_pendientes_normales(db):
    """Solicitud nueva NO se marca como vencida (su límite es futuro)."""
    registrar_solicitud(
        db,
        tipo="oposicion",
        solicitante_nombre="Ana Torres",
        descripcion="No quiero más contacto comercial",
    )
    n = marcar_vencidas(db)
    # Las recién registradas tienen 20 días hábiles, no se vencen
    assert n == 0
