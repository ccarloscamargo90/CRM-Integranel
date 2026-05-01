"""ARCO — Acceso, Rectificación, Cancelación, Oposición.

Implementa el workflow legal de respuesta a solicitudes de derechos ARCO
bajo LFPDPPP 2025. Plazo legal: 20 días hábiles desde recepción.

Funciones principales:
- `registrar_solicitud()`: alta nueva con folio + cálculo de fecha límite.
- `listar_pendientes()`: solicitudes en `recibida` o `en_proceso`.
- `listar_proximas_a_vencer()`: solicitudes con ≤3 días para vencer.
- `marcar_vencidas()`: job diario que actualiza estatus a 'vencida'.
- `responder_solicitud()`: registra respuesta y cambia estatus.
- `exportar_acceso()`: para tipo='acceso', genera CSV con todos los datos
   del solicitante (cumple con derecho de Acceso del Art. 22 LFPDPPP).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion

PLAZO_DIAS_HABILES = 20


def _generar_folio(session: Session) -> str:
    """Folio: ARCO-YYYYMMDD-NNN secuencial dentro del día."""
    hoy = dt.date.today().strftime("%Y%m%d")
    n_hoy = session.execute(
        text("SELECT COUNT(*) FROM arco_solicitudes WHERE folio LIKE :patron"),
        {"patron": f"ARCO-{hoy}-%"},
    ).scalar() or 0
    return f"ARCO-{hoy}-{n_hoy + 1:03d}"


def _calcular_fecha_limite(fecha_recepcion: dt.date, dias_habiles: int = PLAZO_DIAS_HABILES) -> dt.date:
    """Suma `dias_habiles` (lunes-viernes) a `fecha_recepcion`.

    No considera días festivos oficiales — para precisión legal mayor,
    consultar calendario laboral mexicano (DOF).
    """
    fecha = fecha_recepcion
    sumados = 0
    while sumados < dias_habiles:
        fecha += dt.timedelta(days=1)
        if fecha.weekday() < 5:  # 0-4 = lunes a viernes
            sumados += 1
    return fecha


def registrar_solicitud(
    session: Session,
    *,
    tipo: str,
    solicitante_nombre: str,
    descripcion: str,
    solicitante_email: str | None = None,
    solicitante_telefono: str | None = None,
    solicitante_rfc: str | None = None,
    solicitante_razon_social: str | None = None,
    establecimiento_id: int | None = None,
    datos_solicitados: list[str] | None = None,
    notas_internas: str | None = None,
) -> dict[str, Any]:
    """Registra una solicitud ARCO nueva. Devuelve {folio, fecha_limite_respuesta}."""
    if tipo not in ("acceso", "rectificacion", "cancelacion", "oposicion"):
        raise ValueError(f"Tipo inválido: {tipo}")

    folio = _generar_folio(session)
    hoy = dt.date.today()
    fecha_limite = _calcular_fecha_limite(hoy)

    session.execute(
        text(
            """
            INSERT INTO arco_solicitudes (
                folio, tipo, estatus,
                solicitante_nombre, solicitante_email, solicitante_telefono,
                solicitante_rfc, solicitante_razon_social,
                establecimiento_id, descripcion, datos_solicitados,
                fecha_recepcion, fecha_limite_respuesta, notas_internas
            ) VALUES (
                :folio, :tipo, 'recibida',
                :nombre, :email, :tel, :rfc, :razon,
                :est_id, :desc, :datos,
                NOW(), :limite, :notas
            )
            """
        ),
        {
            "folio": folio,
            "tipo": tipo,
            "nombre": solicitante_nombre,
            "email": solicitante_email,
            "tel": solicitante_telefono,
            "rfc": solicitante_rfc,
            "razon": solicitante_razon_social,
            "est_id": establecimiento_id,
            "desc": descripcion,
            "datos": datos_solicitados,
            "limite": fecha_limite,
            "notas": notas_internas,
        },
    )
    session.flush()

    registrar_operacion(
        session=session,
        tipo_operacion=f"arco_{tipo}",
        finalidad=f"Recepción de solicitud ARCO de tipo {tipo}",
        base_legal="LFPDPPP Art. 22-32 — derechos del titular",
        establecimiento_ids=[establecimiento_id] if establecimiento_id else None,
        arco_solicitud_id=folio,
        arco_plazo_dias_habiles=PLAZO_DIAS_HABILES,
        notas=f"Recibida {hoy} | Vence {fecha_limite} | {solicitante_nombre[:50]}",
    )
    session.commit()

    logger.info("ARCO recibida: {f} tipo={t} vence={v}", f=folio, t=tipo, v=fecha_limite)
    return {"folio": folio, "fecha_limite_respuesta": fecha_limite}


def listar_pendientes(session: Session) -> list[dict[str, Any]]:
    """Solicitudes en 'recibida' o 'en_proceso'."""
    rows = session.execute(
        text(
            """
            SELECT folio, tipo, estatus, solicitante_nombre,
                   fecha_recepcion::date AS fecha_recepcion,
                   fecha_limite_respuesta,
                   (fecha_limite_respuesta - CURRENT_DATE) AS dias_restantes
            FROM arco_solicitudes
            WHERE estatus IN ('recibida','en_proceso')
            ORDER BY fecha_limite_respuesta ASC
            """
        )
    ).all()
    return [
        {
            "folio": r.folio,
            "tipo": r.tipo,
            "estatus": r.estatus,
            "solicitante": r.solicitante_nombre,
            "fecha_recepcion": r.fecha_recepcion,
            "fecha_limite": r.fecha_limite_respuesta,
            "dias_restantes": r.dias_restantes,
        }
        for r in rows
    ]


def listar_proximas_a_vencer(session: Session, *, dias: int = 3) -> list[dict[str, Any]]:
    """Solicitudes con `dias` o menos para vencer. Para alertas."""
    return [r for r in listar_pendientes(session) if r["dias_restantes"] is not None and r["dias_restantes"] <= dias]


def marcar_vencidas(session: Session) -> int:
    """Job diario: pasa solicitudes a 'vencida' si excedieron fecha_limite."""
    res = session.execute(
        text(
            """
            UPDATE arco_solicitudes
               SET estatus = 'vencida'
             WHERE estatus IN ('recibida','en_proceso')
               AND fecha_limite_respuesta < CURRENT_DATE
            """
        )
    )
    n = res.rowcount or 0
    session.commit()
    if n > 0:
        logger.warning("ARCO vencidas: {n} solicitudes pasaron a 'vencida'", n=n)
    return n


def responder_solicitud(
    session: Session,
    *,
    folio: str,
    respuesta: str,
    procedente: bool,
    usuario_responsable_id: int | None = None,
    documentos_anexos: dict | None = None,
) -> dict[str, Any]:
    """Marca una solicitud como respondida (o no_procedente)."""
    estatus_nuevo = "respondida" if procedente else "no_procedente"

    res = session.execute(
        text(
            """
            UPDATE arco_solicitudes
               SET estatus = :estatus,
                   respuesta = :respuesta,
                   fecha_respuesta = NOW(),
                   usuario_responsable_id = :uid,
                   documentos_anexos = :docs
             WHERE folio = :folio
               AND estatus IN ('recibida','en_proceso','vencida')
            RETURNING id, tipo, establecimiento_id
            """
        ),
        {
            "estatus": estatus_nuevo,
            "respuesta": respuesta,
            "uid": usuario_responsable_id,
            "docs": documentos_anexos,
            "folio": folio,
        },
    ).one_or_none()

    if not res:
        raise ValueError(f"Folio {folio} no existe o ya fue cerrado")

    session.commit()

    registrar_operacion(
        session=session,
        tipo_operacion=f"arco_{res.tipo}",
        finalidad=f"Respuesta a solicitud ARCO {folio}",
        base_legal="LFPDPPP Art. 32 — plazo de respuesta 20 días hábiles",
        establecimiento_ids=[res.establecimiento_id] if res.establecimiento_id else None,
        usuario_id=usuario_responsable_id,
        arco_solicitud_id=folio,
        notas=f"estatus={estatus_nuevo}. Respuesta: {respuesta[:200]}",
    )
    session.commit()

    logger.info("ARCO respondida: {f} estatus={e}", f=folio, e=estatus_nuevo)
    return {"folio": folio, "estatus_final": estatus_nuevo}


def exportar_acceso(session: Session, *, folio: str) -> bytes:
    """Para solicitudes tipo='acceso': genera CSV con todos los datos del titular.

    Busca por `solicitante_rfc` (si lo proporcionó) o por `establecimiento_id`.
    Devuelve bytes del CSV listo para enviar.
    """
    sol = session.execute(
        text(
            "SELECT solicitante_rfc, solicitante_razon_social, establecimiento_id "
            "FROM arco_solicitudes WHERE folio = :f"
        ),
        {"f": folio},
    ).one_or_none()
    if not sol:
        raise ValueError(f"Folio {folio} no existe")

    # Localizar establecimientos del titular
    where = []
    params: dict[str, Any] = {}
    if sol.solicitante_rfc:
        where.append("rfc = :rfc")
        params["rfc"] = sol.solicitante_rfc
    if sol.solicitante_razon_social:
        where.append("UPPER(TRIM(razon_social)) = UPPER(TRIM(:razon))")
        params["razon"] = sol.solicitante_razon_social
    if sol.establecimiento_id:
        where.append("id = :eid")
        params["eid"] = sol.establecimiento_id

    if not where:
        raise ValueError("La solicitud no tiene RFC, razón social ni establecimiento_id")

    rows = session.execute(
        text(
            "SELECT id, clee, nombre, razon_social, rfc, telefono, email, "
            "direccion, colonia, cp, municipio, estado, "
            "estado_pipeline, vendedor_id, fecha_alta, fecha_actualizacion "
            f"FROM establecimientos WHERE {' OR '.join(where)}"
        ),
        params,
    ).mappings().all()

    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    else:
        out.write("# No se encontraron datos del titular en el sistema\n")

    return out.getvalue().encode("utf-8")
