"""audit — auditoría automática de calidad de datos.

Módulos planeados (Fase 2):
- duplicates.py     → exactos por CLEE + probables por fuzzy nombre+dirección
- completeness.py   → % NULL por columna, registros con campos críticos vacíos
- geo_anomalies.py  → coords fuera de bbox MX, lat/lon invertidas, puntos en océano

Cada chequeo emite reporte estructurado (JSON) que se anexa a `docs/auditoria/`
y un dashboard HTML self-contained con tabla de hallazgos por severidad.
"""
