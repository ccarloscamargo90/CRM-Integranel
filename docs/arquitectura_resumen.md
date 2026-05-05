# Arquitectura del CRM Granos MX — Resumen

Generado el 2026-05-05 como prueba de conectividad y documentación de referencia rápida.

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Base de datos | PostgreSQL 16 + PostGIS 3.4 |
| ORM / Migraciones | SQLAlchemy 2.x + GeoAlchemy2 + Alembic |
| API | FastAPI + Uvicorn (2 workers) |
| Auth | bcrypt directo + JWT HS256 (cookie httpOnly) |
| Frontend | Jinja2 + HTMX 1.9 + Tailwind CSS 3.4 + Leaflet 1.9 |
| HTTP client | httpx + tenacity |
| Validación | Pydantic v2 + Pydantic Settings |
| Geo | shapely + geopandas + geopy + PostGIS |
| Fuzzy matching | rapidfuzz |
| Logs | loguru |
| Tests | pytest (189 tests) |
| Linter | ruff |
| Deploy | Render (Web $7/mes + Postgres $7/mes) |

## Módulos src/

```
src/
├── core/          config, db, logging, modelos ORM, repositorios, heurísticas, constantes
├── ingestion/     DENUE (ZIP CSV), Places API, SAT 69-B, INEGI indicadores, marco geoestadístico, CLI
├── audit/         calidad de datos: duplicados, completitud, geo, SCIAN, contacto
├── enrichment/    matching DENUE↔Google, cadenas, scoring 0-100, cruce SAT 69-B
├── compliance/    LFPDPPP bitácora, módulo ARCO (Acceso/Rectificación/Cancelación/Oposición)
└── api/           FastAPI: auth, rutas REST /prospectos, rutas web HTML (dashboard, lista, mapa, detalle)
```

## Base de datos — tablas principales

| Tabla | Descripción |
|---|---|
| `establecimientos` | 136,012 prospectos con geom PostGIS, score, segmento ABC |
| `cadenas` | 3,247 grupos de sucursales detectados por fuzzy |
| `vendedores` | equipo comercial con municipios_ids JSONB |
| `usuarios` | auth (admin / vendedor / jefe) |
| `interacciones` | bitácora comercial (visitas, llamadas, cotizaciones…) |
| `enriquecimiento_google` | ratings, teléfono, sitio web de Places API |
| `sat_lista_69b` | 14,189 registros SAT con riesgo fiscal |
| `indicadores_geograficos` | consumo tortilla, producción maíz, pobreza por entidad |
| `agebs` | shapefiles INEGI con geometría PostGIS |
| `arco_solicitudes` | solicitudes ARCO con SLA 20 días hábiles |
| `compliance_log` | bitácora LFPDPPP de cada acceso a PII |
| `_columnas_pii` | catálogo de 21 columnas PII con base legal |

## Rutas API REST

- `POST /auth/login` / `POST /auth/logout` / `GET /auth/me`
- `GET /prospectos` — listado filtrable, paginado, vendedor solo ve los suyos
- `GET /prospectos/{id}` — detalle + compliance log automático
- `POST /prospectos/{id}/contacto` — registra interacción + cambia pipeline

## Rutas Web (HTML/HTMX)

- `GET /` — dashboard KPIs
- `GET /lista` — tabla filtrable con HTMX swap
- `GET /prospecto/{id}` — detalle + form contacto
- `GET /mapa` — Leaflet con clustering por segmento ABC
- `GET /api/mapa-data` — JSON para el mapa (hasta 5,000 puntos)

## Canales de venta

| Canal | SCIAN | Registros |
|---|---|---:|
| Tortillerías | 311830, 461160, 311212, 311211 | 111,410 |
| ForrajerasPecuario | 434112, 434225 | 10,662 |
| AsociacionesAgropecuarias | 813110 | 2,043 |
| AlimentoBalanceado | 311110 | 317 |
| **Total** | | **124,432** |

## Scoring y segmentación

- Algoritmo por canal con pesos distintos (tamaño, antigüedad, volumen Google, scoring geográfico, cadenas, etiquetas CONAFAB/PECUARIO_GRANDE/HARINERO_INDUSTRIAL).
- Segmento ABC por percentil global: A (top 20%) = 27,951 / B = 55,400 / C = 52,661.
- Riesgo SAT 69-B → segmento X (descalificado).

## Migraciones Alembic (7 total)

1. `a1b2c3d4e5f6` — baseline (schema completo)
2. `04a9b1e3356b` — drop UNIQUE hash_dedup
3. `35e3f2210f11` — drop UNIQUE cadenas.nombre_grupo
4. `a9b846c36859` — drop UNIQUE enriquecimiento_google.place_id
5. `4c187a972d6e` — drop UNIQUE establecimientos.google_place_id
6. `9602d1aaf900` — add etiquetas TEXT[] con índice GIN
7. `e77ccdc77b2c` — create arco_solicitudes

## Deploy Render

- `render.yaml` — blueprint declarativo: web service + PostgreSQL + cron job SAT 69-B mensual.
- `preDeployCommand`: `alembic upgrade head && python scripts/seed_admin.py`
- Costo estimado: ~$14 USD/mes.
