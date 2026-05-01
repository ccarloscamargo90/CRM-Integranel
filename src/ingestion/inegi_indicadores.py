"""Carga de indicadores geográficos desde seed YAML.

Fuente principal: `data/seeds/indicadores_geograficos.yaml` con datos
públicos oficiales curados (Censo INEGI 2020, ENIGH 2022, SIAP 2024,
CONEVAL 2022).

Nivel actual: **entidad** (16 entidades priorizadas + opcionalmente otras).

Indicadores cargados:
- `consumo_tortilla_kg_per_capita_anio` — ENIGH
- `poblacion_total` — Censo
- `produccion_maiz_grano_blanco_ton` — SIAP
- `pct_pobreza` — CONEVAL (proxy capacidad de compra)

Para nivel **municipio** y **AGEB**, ver Fase 5.3 (Marco Geoestadístico).
Cuando INEGI Indicadores API se integre, este loader queda como fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion
from src.core.models import IndicadorGeografico

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seeds" / "indicadores_geograficos.yaml"


def cargar_seed_yaml(path: Path = SEED_PATH) -> list[dict[str, Any]]:
    """Lee el YAML y devuelve la lista de indicadores."""
    if not path.exists():
        raise FileNotFoundError(f"No existe seed YAML: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("indicadores", [])


def upsert_indicadores(session: Session, registros: list[dict[str, Any]]) -> int:
    """UPSERT por (nivel, cve, indicador, anio). Devuelve cantidad upserteada."""
    if not registros:
        return 0
    stmt = pg_insert(IndicadorGeografico).values(registros)
    upsert = stmt.on_conflict_do_update(
        index_elements=["nivel", "cve", "indicador", "anio"],
        set_={
            "valor": stmt.excluded.valor,
            "unidad": stmt.excluded.unidad,
            "fuente": stmt.excluded.fuente,
        },
    )
    session.execute(upsert)
    session.flush()
    return len(registros)


def cargar_desde_seed(session: Session) -> dict[str, Any]:
    """Pipeline: lee YAML, hace upsert, registra compliance."""
    registros = cargar_seed_yaml()
    n = upsert_indicadores(session, registros)
    session.commit()

    # Métricas para reporte
    por_indicador: dict[str, int] = {}
    for r in registros:
        por_indicador[r["indicador"]] = por_indicador.get(r["indicador"], 0) + 1

    registrar_operacion(
        session=session,
        tipo_operacion="carga_indicadores_geograficos",
        finalidad=(
            "Cargar indicadores socioeconómicos públicos para alimentar el "
            "scoring de prospectos (consumo tortilla, producción maíz, "
            "población, pobreza)."
        ),
        base_legal="Datos públicos oficiales (Censo INEGI, ENIGH, SIAP, CONEVAL)",
        notas=f"upserteados={n} por_indicador={por_indicador}",
    )
    session.commit()

    logger.info("Indicadores cargados: {n} ({d})", n=n, d=por_indicador)
    return {"upserteados": n, "por_indicador": por_indicador}
