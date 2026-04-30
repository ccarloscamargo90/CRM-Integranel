"""enrichment — matching inter-fuentes y scoring de prospectos.

Módulos planeados:
- matching.py   → match DENUE↔Google Places por nombre + radio 200m + fuzzy 80 (Fase 4)
- scoring.py    → score 0-100 por establecimiento, dual por canal (Fase 6)
                  - Canal Tortillerías: pesos del prompt (vol Google 25, zona 20, NSE 10, ...)
                  - Canal Alimento Balanceado: pesos ajustados (capacidad industrial > NSE)

Las vistas `vw_prospectos_priorizados_tortillerias` y
`vw_prospectos_priorizados_alimento_balanceado` se materializan desde aquí.
"""
