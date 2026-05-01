"""Chequeos de completitud — % NULL por columna y registros sin campos críticos.

Tres tipos:
1. `check_columnas_criticas_pobladas` — error si nombre, scian_codigo, hash_dedup
   tienen NULL (deberían venir siempre del DENUE).
2. `check_pct_null_por_columna` — info: estadística de % NULL para diagnóstico.
3. `check_sin_contacto` — warning: prospectos sin teléfono ni email ni whatsapp
   son menos accionables.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from src.audit.models import Hallazgo
from src.core.models import Establecimiento

# Columnas que NUNCA deberían tener NULL si el establecimiento viene de DENUE.
COLUMNAS_CRITICAS = ("nombre", "nombre_norm", "scian_codigo", "hash_dedup")

# Columnas a evaluar para reporte estadístico de % NULL.
COLUMNAS_DIAGNOSTICO = (
    "clee", "razon_social", "rfc",
    "telefono", "whatsapp", "email", "sitio_web",
    "latitud", "longitud", "geom",
    "estrato_personal_denue", "anio_alta_denue",
    "vendedor_id", "segmento_abc", "score_prioridad",
)


def check_columnas_criticas_pobladas(
    session: Session, *, max_ejemplos: int = 10
) -> Hallazgo:
    """Si una de las columnas críticas tiene NULL, el establecimiento es inválido."""
    cond_nula = or_(
        *[getattr(Establecimiento, c).is_(None) for c in COLUMNAS_CRITICAS]
    )
    total_evaluados = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()

    rows_problema = session.execute(
        select(
            Establecimiento.id,
            *[getattr(Establecimiento, c) for c in COLUMNAS_CRITICAS],
        )
        .where(cond_nula)
        .limit(max_ejemplos)
    ).all()

    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond_nula)
    ).scalar_one()

    ejemplos: list[dict[str, Any]] = []
    for r in rows_problema:
        d = {"id": r[0]}
        for i, c in enumerate(COLUMNAS_CRITICAS, start=1):
            d[c] = r[i]
        ejemplos.append(d)

    return Hallazgo(
        chequeo="completeness.columnas_criticas",
        severidad="error",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle=f"Columnas obligatorias: {', '.join(COLUMNAS_CRITICAS)}",
        ejemplos=ejemplos,
    )


def check_pct_null_por_columna(session: Session) -> list[Hallazgo]:
    """Devuelve un Hallazgo por columna con % NULL — informativo, no error."""
    total = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()

    if total == 0:
        return [
            Hallazgo(
                chequeo="completeness.pct_null",
                severidad="info",
                total_evaluados=0,
                total_problemas=0,
                detalle="Tabla vacía",
            )
        ]

    hallazgos: list[Hallazgo] = []
    for col in COLUMNAS_DIAGNOSTICO:
        atributo = getattr(Establecimiento, col)
        n_nulos = session.execute(
            select(func.count()).select_from(Establecimiento).where(atributo.is_(None))
        ).scalar_one()
        hallazgos.append(
            Hallazgo(
                chequeo=f"completeness.pct_null.{col}",
                severidad="info",
                total_evaluados=total,
                total_problemas=n_nulos,
                detalle=f"% NULL de la columna `{col}`",
            )
        )
    return hallazgos


def check_sin_contacto(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """Establecimientos sin teléfono Y sin whatsapp Y sin email — poca accionabilidad."""
    cond_sin_contacto = and_(
        Establecimiento.telefono.is_(None),
        Establecimiento.whatsapp.is_(None),
        Establecimiento.email.is_(None),
    )
    total_evaluados = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()
    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond_sin_contacto)
    ).scalar_one()

    ejemplos = session.execute(
        select(Establecimiento.id, Establecimiento.nombre_norm, Establecimiento.municipio)
        .where(cond_sin_contacto)
        .limit(max_ejemplos)
    ).all()

    return Hallazgo(
        chequeo="completeness.sin_contacto",
        severidad="warning",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle="Sin teléfono, whatsapp ni email — candidato a enriquecimiento Google Places",
        ejemplos=[
            {"id": r[0], "nombre": r[1], "municipio": r[2]} for r in ejemplos
        ],
    )
