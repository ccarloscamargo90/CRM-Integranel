"""Detección de duplicados en `establecimientos`.

Tres tipos:
1. **CLEE duplicado** — la columna es UNIQUE en schema, así que esto NUNCA debería
   pasar; si pasa, hay que corregir la lógica de upsert. Severidad: error.
2. **hash_dedup duplicado** — igual, schema UNIQUE. Si pasa, error de generación
   de hash. Severidad: error.
3. **Fuzzy duplicado** — mismo establecimiento capturado dos veces con CLEEs
   diferentes (ej. una vez por DENUE oficial y otra por Google manual).
   Detección por nombre+dirección con rapidfuzz threshold 90+. Severidad: warning.
"""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from src.audit.models import Hallazgo
from src.core.models import Establecimiento


def check_clee_duplicates(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """CLEE debería ser único por schema. Si hay duplicados, hay un bug de upsert."""
    stmt = text("""
        SELECT clee, COUNT(*) AS n
        FROM establecimientos
        WHERE clee IS NOT NULL
        GROUP BY clee
        HAVING COUNT(*) > 1
        LIMIT :limite
    """)
    duplicados = session.execute(stmt, {"limite": max_ejemplos}).all()

    total_evaluados = session.execute(
        select(func.count()).select_from(Establecimiento).where(Establecimiento.clee.is_not(None))
    ).scalar_one()

    return Hallazgo(
        chequeo="duplicates.clee",
        severidad="error",
        total_evaluados=total_evaluados,
        total_problemas=len(duplicados),
        detalle="CLEE debe ser único; si aparece duplicado hay bug en upsert DENUE",
        ejemplos=[{"clee": r[0], "ocurrencias": r[1]} for r in duplicados],
    )


def check_hash_duplicates(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """hash_dedup también debe ser único; si no, hay colisión real o bug en hash."""
    stmt = text("""
        SELECT hash_dedup, COUNT(*) AS n
        FROM establecimientos
        GROUP BY hash_dedup
        HAVING COUNT(*) > 1
        LIMIT :limite
    """)
    duplicados = session.execute(stmt, {"limite": max_ejemplos}).all()

    total_evaluados = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()

    return Hallazgo(
        chequeo="duplicates.hash_dedup",
        severidad="error",
        total_evaluados=total_evaluados,
        total_problemas=len(duplicados),
        detalle="hash_dedup debe ser único; colisión real o bug en sha1(nombre+cp+lat+lon)",
        ejemplos=[{"hash": r[0], "ocurrencias": r[1]} for r in duplicados],
    )


def check_fuzzy_duplicates(
    session: Session,
    *,
    threshold: int = 90,
    municipio_codigo: str | None = None,
    max_ejemplos: int = 10,
) -> Hallazgo:
    """Detecta probables duplicados por similaridad nombre+dirección dentro del
    mismo municipio. NO toca DB; carga los registros y compara con rapidfuzz.

    `municipio_codigo` opcional: si se pasa, solo compara dentro de ese municipio
    (más rápido y la heurística "mismo municipio + nombre similar" es razonable).
    Si es None, comparación global por bloques de municipio (más lento pero
    completo).
    """
    stmt = (
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.colonia,
            Establecimiento.cp,
            Establecimiento.municipio_codigo,
        )
        .where(Establecimiento.nombre_norm.is_not(None))
    )
    if municipio_codigo is not None:
        stmt = stmt.where(Establecimiento.municipio_codigo == municipio_codigo)

    filas = session.execute(stmt).all()

    # Bloque por municipio para acotar comparaciones — O(n²) por bloque, no global.
    por_municipio: dict[str, list[tuple[Any, ...]]] = {}
    for f in filas:
        key = f.municipio_codigo or "_sin_municipio"
        por_municipio.setdefault(key, []).append(f)

    pares_dup: list[dict[str, Any]] = []
    for muni, registros in por_municipio.items():
        if len(registros) < 2:
            continue
        # Construir clave fuzzy = nombre_norm + colonia
        for i in range(len(registros)):
            for j in range(i + 1, len(registros)):
                a, b = registros[i], registros[j]
                key_a = f"{a.nombre_norm} {a.colonia or ''}".strip()
                key_b = f"{b.nombre_norm} {b.colonia or ''}".strip()
                score = fuzz.token_sort_ratio(key_a, key_b)
                if score >= threshold:
                    pares_dup.append(
                        {
                            "id_a": a.id,
                            "id_b": b.id,
                            "municipio": muni,
                            "nombre_a": a.nombre_norm,
                            "nombre_b": b.nombre_norm,
                            "score": score,
                        }
                    )
                    if len(pares_dup) >= max_ejemplos:
                        break
            if len(pares_dup) >= max_ejemplos:
                break
        if len(pares_dup) >= max_ejemplos:
            break

    return Hallazgo(
        chequeo="duplicates.fuzzy",
        severidad="warning",
        total_evaluados=len(filas),
        total_problemas=len(pares_dup),
        detalle=(
            f"Pares con score rapidfuzz >= {threshold} "
            f"(scope: {'municipio ' + municipio_codigo if municipio_codigo else 'todos los municipios'})"
        ),
        ejemplos=pares_dup[:max_ejemplos],
    )
