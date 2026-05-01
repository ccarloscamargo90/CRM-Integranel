"""Validación de SCIAN y consistencia con canales asignados.

Tres chequeos:
1. SCIAN está en los 8 objetivo del proyecto.
2. El canal asignado coincide con el canal natural del SCIAN.
3. Si el establecimiento tiene canales[] vacío, es un problema (debe tener al menos uno).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.audit.models import Hallazgo
from src.core.constantes import SCIAN_OBJETIVO, SCIAN_PRIMARIOS, canal_de_scian
from src.core.models import Establecimiento


def check_scian_en_objetivo(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """SCIAN debe estar en SCIAN_PRIMARIOS — si no, no era parte de la descarga objetivo."""
    cond = Establecimiento.scian_codigo.notin_(SCIAN_PRIMARIOS)

    total_evaluados = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()
    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond)
    ).scalar_one()

    ejemplos = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.scian_codigo,
            Establecimiento.scian_descripcion,
        )
        .where(cond)
        .limit(max_ejemplos)
    ).all()

    return Hallazgo(
        chequeo="scian.fuera_objetivo",
        severidad="error",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle=f"SCIAN objetivo: {sorted(SCIAN_PRIMARIOS)}",
        ejemplos=[
            {"id": r[0], "nombre": r[1], "scian": r[2], "descripcion": r[3]}
            for r in ejemplos
        ],
    )


def check_canal_consistente_con_scian(
    session: Session, *, max_ejemplos: int = 10
) -> Hallazgo:
    """El array `canales` debe incluir el canal natural del SCIAN.

    Por ejemplo, si scian=311830 (tortillerías), 'Tortillerias' debe estar en `canales`.
    Un establecimiento puede tener varios canales (caso dual con granza), pero el natural
    es no-negociable.
    """
    # Solo evaluamos los que tienen SCIAN objetivo (los demás los marca check_scian_en_objetivo).
    rows = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.scian_codigo,
            Establecimiento.canales,
        ).where(Establecimiento.scian_codigo.in_(SCIAN_PRIMARIOS))
    ).all()

    inconsistentes = []
    for row in rows:
        canal_natural = canal_de_scian(row.scian_codigo)
        canales_actuales = list(row.canales or [])
        if canal_natural is None:
            continue  # imposible, ya filtramos
        if canal_natural not in canales_actuales:
            inconsistentes.append(
                {
                    "id": row.id,
                    "nombre": row.nombre_norm,
                    "scian": row.scian_codigo,
                    "canal_esperado": canal_natural,
                    "canales_actuales": canales_actuales,
                }
            )

    return Hallazgo(
        chequeo="scian.canal_inconsistente",
        severidad="error",
        total_evaluados=len(rows),
        total_problemas=len(inconsistentes),
        detalle="El canal natural del SCIAN debe estar en `canales[]`",
        ejemplos=inconsistentes[:max_ejemplos],
    )


def check_canales_no_vacio(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """`canales` no puede estar vacío — todo establecimiento pertenece a algún canal."""
    cond = func.cardinality(Establecimiento.canales) == 0

    total_evaluados = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()
    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond)
    ).scalar_one()

    ejemplos = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.scian_codigo,
        )
        .where(cond)
        .limit(max_ejemplos)
    ).all()

    return Hallazgo(
        chequeo="scian.canales_vacio",
        severidad="error",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle="Establecimiento sin canales[] no es accionable comercialmente",
        ejemplos=[
            {"id": r[0], "nombre": r[1], "scian": r[2]} for r in ejemplos
        ],
    )


def conteo_por_scian(session: Session) -> Hallazgo:
    """Estadística informativa: cuántos establecimientos por SCIAN."""
    rows = session.execute(
        select(Establecimiento.scian_codigo, func.count(Establecimiento.id))
        .group_by(Establecimiento.scian_codigo)
        .order_by(func.count(Establecimiento.id).desc())
    ).all()

    total = sum(r[1] for r in rows)
    distribucion = {
        r[0]: {
            "n": r[1],
            "pct": round(100 * r[1] / total, 2) if total else 0,
            "descripcion": SCIAN_OBJETIVO.get(r[0], (None, None))[0],
        }
        for r in rows
    }

    return Hallazgo(
        chequeo="scian.distribucion",
        severidad="info",
        total_evaluados=total,
        total_problemas=0,
        detalle="Distribución de establecimientos por SCIAN",
        ejemplos=[{"scian": k, **v} for k, v in distribucion.items()],
    )
