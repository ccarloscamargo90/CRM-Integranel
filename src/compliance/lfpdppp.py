"""Capa de cumplimiento LFPDPPP 2025 — helpers transversales.

Reglas no negociables (ver `CLAUDE.md` §8):
1. Toda operación que toque PII se registra en `compliance_log` ANTES de devolver datos.
2. Las columnas PII conocidas viven en `_columnas_pii` (catálogo); cualquier columna
   no listada ahí es responsabilidad de quien la introdujo agregarla en una migración.
3. ARCO debe responderse en ≤20 días hábiles.

Uso típico en Fases posteriores:
    from src.compliance.lfpdppp import registrar_operacion

    registrar_operacion(
        session=db,
        usuario_id=current_user.id,
        tipo_operacion="exportacion_csv",
        finalidad="Listado de prospectos asignados al vendedor para visita en campo",
        base_legal="Interés legítimo comercial B2B",
        establecimiento_ids=[1, 2, 3, 42],
        columnas_tocadas=["telefono", "email", "contacto_nombre"],
    )
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from src.core.models import ComplianceLog


def registrar_operacion(
    *,
    session: Session,
    tipo_operacion: str,
    finalidad: str,
    base_legal: str,
    usuario_id: int | None = None,
    establecimiento_ids: Sequence[int] | None = None,
    columnas_tocadas: Sequence[str] | None = None,
    arco_solicitud_id: str | None = None,
    arco_plazo_dias_habiles: int | None = None,
    notas: str | None = None,
) -> list[ComplianceLog]:
    """Inserta una fila en `compliance_log` por cada `establecimiento_id` afectado.

    Si `establecimiento_ids` es None o vacío, registra una sola fila genérica
    (útil para descargas masivas DENUE donde aún no hay establecimientos
    individuales relacionables).

    El caller decide commit. Devuelve los objetos creados (con id asignado tras flush).
    """
    if not tipo_operacion or not finalidad or not base_legal:
        raise ValueError(
            "registrar_operacion requiere tipo_operacion, finalidad y base_legal"
        )

    # Si la operación es ARCO, el plazo default es 20 días hábiles.
    if tipo_operacion.startswith("arco_") and arco_plazo_dias_habiles is None:
        arco_plazo_dias_habiles = 20

    cols = list(columnas_tocadas) if columnas_tocadas else None

    if not establecimiento_ids:
        log = ComplianceLog(
            usuario_id=usuario_id,
            tipo_operacion=tipo_operacion,
            establecimiento_id=None,
            columnas_pii_tocadas=cols,
            finalidad=finalidad,
            base_legal=base_legal,
            arco_solicitud_id=arco_solicitud_id,
            arco_plazo_dias_habiles=arco_plazo_dias_habiles,
            notas=notas,
        )
        session.add(log)
        session.flush()
        return [log]

    logs: list[ComplianceLog] = []
    for est_id in establecimiento_ids:
        log = ComplianceLog(
            usuario_id=usuario_id,
            tipo_operacion=tipo_operacion,
            establecimiento_id=est_id,
            columnas_pii_tocadas=cols,
            finalidad=finalidad,
            base_legal=base_legal,
            arco_solicitud_id=arco_solicitud_id,
            arco_plazo_dias_habiles=arco_plazo_dias_habiles,
            notas=notas,
        )
        session.add(log)
        logs.append(log)
    session.flush()
    return logs
