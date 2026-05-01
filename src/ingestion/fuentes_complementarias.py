"""Cruce de establecimientos con fuentes complementarias (CONAFAB, CANAMI, etc).

Carga el seed `data/seeds/fuentes_complementarias.yaml` con razones sociales
conocidas de socios de cámaras y grandes productores, y aplica etiquetas a
`establecimientos.etiquetas[]` cuando matchea por razón social UPPER+TRIM.

Etiquetas comunes:
- CONAFAB: socio del Consejo Nacional Fabricantes Alimento Balanceado.
- PECUARIO_GRANDE: productor pecuario top en MX (Bachoco, Pilgrim's, Norson).
- HARINERO_INDUSTRIAL: socio CANAMI o equivalente (Maseca, Minsa, Harimasa).

Estas etiquetas alimentan el scoring de Fase 6 — un establecimiento marcado
CONAFAB es cliente verificado y obtiene boost en su score.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion

SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "seeds"
    / "fuentes_complementarias.yaml"
)


def cargar_seed() -> list[dict[str, Any]]:
    if not SEED_PATH.exists():
        raise FileNotFoundError(f"No existe seed: {SEED_PATH}")
    with SEED_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("empresas", [])


def aplicar_etiquetas(session: Session) -> dict[str, Any]:
    """Cruza por razón social UPPER+TRIM. Para cada match, hace
    `array_unique(etiquetas || nuevas_etiquetas)` para no duplicar.

    Devuelve métricas por etiqueta.
    """
    empresas = cargar_seed()

    metricas: dict[str, int] = {}
    total_matches = 0

    for emp in empresas:
        razon = emp["razon_social"].strip().upper()
        etiquetas = emp.get("etiquetas", [])
        if not etiquetas:
            continue

        # Convertir lista Python a literal de Postgres array
        etiquetas_pg = "{" + ",".join(f'"{e}"' for e in etiquetas) + "}"

        res = session.execute(
            text(
                """
                UPDATE establecimientos
                   SET etiquetas = ARRAY(
                     SELECT DISTINCT unnest(etiquetas || CAST(:tags AS TEXT[]))
                   )
                 WHERE UPPER(TRIM(razon_social)) = :razon
                """
            ),
            {"razon": razon, "tags": etiquetas_pg},
        )
        n = res.rowcount or 0
        if n > 0:
            total_matches += n
            for et in etiquetas:
                metricas[et] = metricas.get(et, 0) + n

    session.commit()

    registrar_operacion(
        session=session,
        tipo_operacion="aplicar_etiquetas_complementarias",
        finalidad=(
            "Etiquetar establecimientos como socios CONAFAB / PECUARIO_GRANDE / "
            "HARINERO_INDUSTRIAL para alimentar el scoring de Fase 6."
        ),
        base_legal="Datos públicos: presentaciones, DOF, anuarios cámaras",
        notas=f"empresas_evaluadas={len(empresas)} establecimientos_etiquetados={total_matches}",
    )
    session.commit()

    logger.info(
        "Etiquetas aplicadas: {t} matches totales. Distribución: {d}",
        t=total_matches,
        d=metricas,
    )
    return {
        "empresas_seed": len(empresas),
        "establecimientos_etiquetados": total_matches,
        "por_etiqueta": metricas,
    }
