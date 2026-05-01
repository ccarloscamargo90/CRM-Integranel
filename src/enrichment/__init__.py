"""enrichment — matching DENUE↔Google + scoring + asignación + detección cadenas.

Módulos:
- `matching.py`        Matcher DENUE↔Google con fuzzy + radio 200m (Fase 4)
- `cadenas.py`         Detector de cadenas con palabras-marca (Fase 4)
- `places_pipeline.py` Orquestador D3.B (Fase 4)
- `scoring.py`         Score 0-100 por canal (Fase 6 — pendiente)
- `asignacion.py`      Auto-asignación a vendedor por municipio (Fase 6 — pendiente)

El pipeline `places_pipeline.run_enriquecimiento` selecciona automáticamente
los ~5K candidatos D3.B y respeta el `MONTHLY_BUDGET_USD` vía circuit breaker
del cliente.
"""

from src.enrichment.cadenas import detectar_cadenas, listar_top_cadenas
from src.enrichment.matching import enriquecer_establecimiento
from src.enrichment.places_pipeline import (
    ResumenEnriquecimiento,
    run_enriquecimiento,
    seleccionar_candidatos_d3b,
)

__all__ = [
    "ResumenEnriquecimiento",
    "detectar_cadenas",
    "enriquecer_establecimiento",
    "listar_top_cadenas",
    "run_enriquecimiento",
    "seleccionar_candidatos_d3b",
]
