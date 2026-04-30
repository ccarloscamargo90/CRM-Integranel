"""ingestion — clientes para todas las fuentes externas de datos.

Módulos planeados:
- denue.py                 → DENUE API INEGI (Fase 3)
- places_api.py            → Google Places API (Fase 4)
- sat_publica.py           → Listado 69-B SAT (Fase 5.1)
- inegi_indicadores.py     → ENIGH consumo tortilla, SIAP producción maíz, NSE (Fase 5.2)
- marco_geoestadistico.py  → shapefiles AGEB para spatial join (Fase 5.3)
- conafab.py               → directorio CONAFAB de fabricantes alimento balanceado (Fase 5.4)

Cada cliente debe:
- Loguear timestamp, endpoint, status, tamaño y costo USD estimado.
- Respetar throttling con tenacity.
- Persistir vía upsert (no duplicar si se re-corre).
- Aceptar dry-run para validar lógica sin escribir.
"""
