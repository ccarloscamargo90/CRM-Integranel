"""Validación de campos de contacto y dirección.

Chequeos:
1. `check_telefono_formato_mx` — teléfonos deben ser 10 dígitos numéricos
   (formato MX). Acepta variantes con +52, espacios, guiones — el chequeo
   normaliza primero. Si tras normalizar no son 10 dígitos, error.
2. `check_email_formato` — email debe matchear regex razonable.
3. `check_direccion_sospechosa` — direcciones tipo "domicilio conocido", sin
   número exterior, etc. — warning.
4. `check_anio_alta_denue_razonable` — anio_alta_denue entre 2005 y año actual.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from src.audit.models import Hallazgo
from src.core.models import Establecimiento

_RE_DIGITOS = re.compile(r"\D+")
_RE_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")

DIRECCIONES_SOSPECHOSAS_PATRONES = (
    "domicilio conocido",
    "sin numero",
    "sin número",
    "sn",
    "s/n",
    "n/d",
    "n/a",
)


def _normaliza_telefono_mx(tel: str | None) -> str | None:
    """Quita todo no-dígito; si empieza con 52 o +52 (MX) lo recorta a 10 dígitos."""
    if not tel:
        return None
    solo_digitos = _RE_DIGITOS.sub("", tel)
    # Lada MX +52 — recorta el prefijo
    if solo_digitos.startswith("521") and len(solo_digitos) == 13:  # +52 1 (móvil)
        return solo_digitos[3:]
    if solo_digitos.startswith("52") and len(solo_digitos) == 12:
        return solo_digitos[2:]
    return solo_digitos


def check_telefono_formato_mx(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """Después de normalizar, debe haber exactamente 10 dígitos."""
    rows = session.execute(
        select(Establecimiento.id, Establecimiento.nombre_norm, Establecimiento.telefono)
        .where(Establecimiento.telefono.is_not(None))
    ).all()

    invalidos: list[dict[str, Any]] = []
    for r in rows:
        norm = _normaliza_telefono_mx(r.telefono)
        if norm is None or len(norm) != 10:
            invalidos.append(
                {
                    "id": r.id,
                    "nombre": r.nombre_norm,
                    "telefono_original": r.telefono,
                    "telefono_normalizado": norm,
                    "longitud": len(norm) if norm else 0,
                }
            )

    return Hallazgo(
        chequeo="contacto.telefono_formato_mx",
        severidad="warning",
        total_evaluados=len(rows),
        total_problemas=len(invalidos),
        detalle="Tras normalizar, debe ser exactamente 10 dígitos (MX)",
        ejemplos=invalidos[:max_ejemplos],
    )


def check_email_formato(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """Email debe matchear regex razonable (no validación 100% RFC, sólo sano)."""
    rows = session.execute(
        select(Establecimiento.id, Establecimiento.nombre_norm, Establecimiento.email)
        .where(Establecimiento.email.is_not(None))
    ).all()

    invalidos: list[dict[str, Any]] = []
    for r in rows:
        if not _RE_EMAIL.match((r.email or "").strip()):
            invalidos.append(
                {"id": r.id, "nombre": r.nombre_norm, "email": r.email}
            )

    return Hallazgo(
        chequeo="contacto.email_formato",
        severidad="warning",
        total_evaluados=len(rows),
        total_problemas=len(invalidos),
        detalle="Email debe coincidir con [\\w.+-]+@[\\w-]+\\.[\\w.-]+",
        ejemplos=invalidos[:max_ejemplos],
    )


def check_direccion_sospechosa(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """Direcciones con texto tipo 'domicilio conocido' o sin número exterior."""
    cond_patrones = or_(
        *[
            func.lower(Establecimiento.direccion).like(f"%{p}%")
            for p in DIRECCIONES_SOSPECHOSAS_PATRONES
        ]
    )
    cond_sin_numero_ext = and_(
        Establecimiento.direccion.is_not(None),
        Establecimiento.numero_exterior.is_(None),
    )
    cond = or_(cond_patrones, cond_sin_numero_ext)

    total_evaluados = session.execute(
        select(func.count())
        .select_from(Establecimiento)
        .where(Establecimiento.direccion.is_not(None))
    ).scalar_one()
    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond)
    ).scalar_one()
    ejemplos = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.direccion,
            Establecimiento.numero_exterior,
        )
        .where(cond)
        .limit(max_ejemplos)
    ).all()

    return Hallazgo(
        chequeo="contacto.direccion_sospechosa",
        severidad="warning",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle=(
            "Patrones: "
            + ", ".join(DIRECCIONES_SOSPECHOSAS_PATRONES)
            + " — o sin numero_exterior"
        ),
        ejemplos=[
            {"id": r[0], "nombre": r[1], "direccion": r[2], "ext": r[3]}
            for r in ejemplos
        ],
    )


def check_anio_alta_denue_razonable(
    session: Session, *, anio_min: int = 2005, max_ejemplos: int = 10
) -> Hallazgo:
    """anio_alta_denue debería estar en [anio_min, año actual]."""
    anio_actual = dt.date.today().year
    cond = and_(
        Establecimiento.anio_alta_denue.is_not(None),
        or_(
            Establecimiento.anio_alta_denue < anio_min,
            Establecimiento.anio_alta_denue > anio_actual,
        ),
    )

    total_evaluados = session.execute(
        select(func.count())
        .select_from(Establecimiento)
        .where(Establecimiento.anio_alta_denue.is_not(None))
    ).scalar_one()
    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond)
    ).scalar_one()
    ejemplos = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.anio_alta_denue,
        )
        .where(cond)
        .limit(max_ejemplos)
    ).all()

    return Hallazgo(
        chequeo="contacto.anio_alta_denue",
        severidad="warning",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle=f"anio_alta_denue debe estar en [{anio_min}, {anio_actual}]",
        ejemplos=[{"id": r[0], "nombre": r[1], "anio": r[2]} for r in ejemplos],
    )
