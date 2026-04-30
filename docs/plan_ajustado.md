# Plan ajustado — CRM-Granos-MX (Fase 1)

**Fecha:** 2026-04-30
**Autor:** Claude Code
**Para:** operador del negocio (Carlos)
**Reemplaza:** ningún plan previo. Es la primera versión ajustada del prompt maestro v2 a la realidad del proyecto recién instalado.

---

## TL;DR (lectura mínima de 90 segundos)

- **Hoy tenemos:** scaffold, schema baseline aplicado, 21 columnas PII catalogadas, token INEGI validado, dimensionamiento de 124,432 establecimientos en 13 entidades. **Nada de código de negocio todavía.**
- **El prompt v2 plantea 8 fases de trabajo.** Fase 0 cerrada, faltan 1 → 8.
- **Mi propuesta de orden:** Fase 2 (auditoría) se reduce porque no heredamos data → la convertimos en "diseño de chequeos de calidad". Las fases 3 → 4 → 5 → 6 → 7 → 8 quedan como están, pero con ajustes en alcance y orden.
- **Camino crítico:** Fase 3 (descarga real DENUE) bloquea todo lo demás. Estimo ~3 días corriendo sin pausa con throttling, ~2 semanas con desarrollo iterativo y validaciones.
- **Tienes 7 decisiones pendientes** (§3) que afectan alcance, costo o arquitectura. Las marco con 🔴 cuando son bloqueantes, 🟡 cuando son ajustables después.

---

## 1. Análisis de gaps por componente

Cada fila: componente del plan global (derivado del prompt v2 + lo que aprendimos en Fase 0), estado actual, acción propuesta, fase donde se construye.

### 1.1 Capa de configuración

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| `.env` con todas las vars | ✅ existe | mantener | Fase 0 ✓ |
| `Settings` con Pydantic Settings | ❌ no existe | construir en `src/core/config.py` | Fase 1.bis (junto con DB) |
| Engine SQLAlchemy con pool | ❌ no existe | construir en `src/core/db.py` | Fase 1.bis |
| Logging con loguru (sinks por nivel) | ❌ no existe | construir en `src/core/logging.py` | Fase 1.bis |
| `get_db` dependency FastAPI | ❌ no existe | en `src/core/db.py`, se usará desde Fase 8 | Fase 1.bis |

> **Fase 1.bis** es una mini-fase que propongo intercalar **antes** de Fase 2 — son los cimientos transversales que toda fase posterior va a usar. Sin esto, Fase 2 escribiría código que toca DB sin engine real.

### 1.2 Capa de datos (modelos ORM)

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| Schema SQL aplicado en Postgres | ✅ existe (14 tablas + 4 vistas) | mantener | Fase 0 ✓ |
| Modelos ORM declarativos | ❌ no existe | construir `src/core/models.py` con SQLAlchemy 2 ORM imperativo | Fase 1.bis |
| Repositorios (Repository Pattern) | ❌ no existe | construir `src/core/repos/` por dominio | Fase 1.bis |

**Decisión:** uso ORM declarativo SQLAlchemy 2.0 con `Mapped[...]` (estilo nuevo). NO defino las vistas como ORM — quedan como queries directas.

### 1.3 Capa de ingestion

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| Cliente DENUE Cuantificar | 🟡 probado en Fase 0 (curl) pero no como módulo | construir `src/ingestion/denue.py` con httpx + tenacity + paginación | Fase 3 |
| Cliente DENUE BuscarEntidad | ❌ no existe | en `denue.py`, paginación 5,000 | Fase 3 |
| Cliente DENUE Ficha (detalle CLEE) | ❌ no existe | en `denue.py` | Fase 3 |
| Cliente DENUE Nombre (búsqueda por keyword) | 🟡 probado en Fase 0 | en `denue.py` para fuentes complementarias | Fase 3 |
| Cliente Google Places (Text Search) | ❌ no existe | construir `src/ingestion/places_api.py` con FieldMask + cache 30 días | Fase 4 |
| Cliente Google Places (Place Details) | ❌ no existe | en `places_api.py` | Fase 4 |
| Circuit breaker Google Cloud budget | ❌ no existe | en `places_api.py` (lee `MONTHLY_BUDGET_USD` de Settings) | Fase 4 |
| Cliente SAT 69-B (descarga Excel oficial) | ❌ no existe | construir `src/ingestion/sat_publica.py` | Fase 5.1 |
| Cliente INEGI Indicadores API | ❌ no existe | construir `src/ingestion/inegi_indicadores.py` | Fase 5.2 |
| Cargador Marco Geoestadístico (shapefile) | ❌ no existe | construir `src/ingestion/marco_geoestadistico.py` con geopandas + ST_Multi | Fase 5.3 |
| Cliente CONAFAB (cámara fabricantes alimento) | ❌ no existe | investigar fuente; si existe API/listado público, construir | Fase 5.4 (opcional) |
| Cliente CANAMI (cámara maíz industrializado) | ❌ no existe | sitio no resuelve DNS → investigar Concamin, DOF | Fase 5.4 (opcional) |
| Persistencia de granjas integradas (SENASICA/SIAP) | ❌ no existe | investigar API; granjas no están en DENUE | Fase 5.5 (opcional) |

### 1.4 Capa de audit

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| Detector duplicados exactos (CLEE) | ❌ no existe | construir `src/audit/duplicates.py::find_exact_duplicates()` | Fase 2 |
| Detector duplicados probables (fuzzy nombre+dirección) | ❌ no existe | rapidfuzz con threshold 90 | Fase 2 |
| Chequeo completitud por columna | ❌ no existe | construir `src/audit/completeness.py` | Fase 2 |
| Chequeo bbox MX (lat 14.5–32.7, lon -118.4–-86.7) | ❌ no existe | construir `src/audit/geo_anomalies.py` | Fase 2 |
| Chequeo lat/lon invertidas | ❌ no existe | en `geo_anomalies.py` (heurística: si lat>0 y |lat|<|lon| sospechoso) | Fase 2 |
| Chequeo SCIAN fuera de los 8 objetivo | ❌ no existe | en `audit/` | Fase 2 |
| Chequeo teléfonos formato MX (10 dígitos) | ❌ no existe | en `audit/` | Fase 2 |
| Chequeo direcciones sospechosas ("domicilio conocido", sin número) | ❌ no existe | en `audit/` | Fase 2 |
| Reporte HTML/Markdown exportable | ❌ no existe | en `audit/` con plantilla Jinja2 | Fase 2 |

> **Cambio de alcance Fase 2:** el prompt v2 asumía que íbamos a heredar data del legacy. Como decidimos "proyecto nuevo desde cero", **Fase 2 deja de auditar data existente** (no hay) y se convierte en **"definir y construir los chequeos"** que vamos a aplicar a la primera descarga real (Fase 3) y a cada refresh posterior. Estimación reducida: ~3 días en vez de los ~6 que requeriría con data heredada.

### 1.5 Capa de enrichment

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| Matcher DENUE↔Google Places (nombre + radio 200m + fuzzy 80) | ❌ no existe | construir `src/enrichment/matching.py` | Fase 4 |
| Detector de cadenas (fuzzy nombre normalizado) | ❌ no existe | construir `src/enrichment/cadenas.py` | Fase 4 (post-enriquecimiento) |
| Scoring por canal con pesos diferenciados | ❌ no existe | construir `src/enrichment/scoring.py` con dispatch por canal | Fase 6 |
| Asignación automática a vendedor por municipio | ❌ no existe | en `enrichment/asignacion.py` | Fase 6 |
| Densidad de competencia (pocas tortillerías en 500m) | ❌ no existe | usa PostGIS `ST_DWithin`, query directa | Fase 6 |

**Pesos de scoring por canal — propuesta inicial (validar contra equipo de ventas):**

| Componente | Tortillerías | AlimentoBalanceado | ForrajerasPecuario | Asociaciones |
|---|---:|---:|---:|---:|
| Tamaño estimado (estrato DENUE) | 20 | 35 | 25 | 15 |
| Antigüedad (años en DENUE) | 10 | 5 | 10 | 5 |
| Volumen Google (rating·log(reviews)) | 25 | 5 | 15 | 0 |
| Zona prioritaria (centro-sureste) | 20 | 15 | 25 | 25 |
| NSE de la AGEB | 10 | 0 | 5 | 5 |
| Densidad de competencia (a menor, mejor) | 5 | 0 | 5 | 5 |
| Datos contacto (tel + dirección completa) | 10 | 10 | 15 | 15 |
| **Bonificación cadena (≥3 sucursales)** | +5 | +10 | 0 | 0 |
| **Bonificación red asociaciones (≥50 socios)** | 0 | 0 | 0 | +30 |
| Riesgo fiscal (Lista 69-B) | -100 | -100 | -100 | -100 |

Justificación rápida:
- **AlimentoBalanceado** importa más el tamaño (industriales) y menos la zona (compran a granel sin importar dónde).
- **ForrajerasPecuario** importa la zona rural y el contacto telefónico (negocio low-tech).
- **Asociaciones** valen por el efecto multiplicador (B2B2C). NSE no aplica directamente.

### 1.6 Capa de compliance

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| Catálogo `_columnas_pii` poblado | ✅ existe (21 filas) | mantener | Fase 0 ✓ |
| `compliance.lfpdppp.registrar_operacion(...)` helper | ❌ no existe | construir `src/compliance/lfpdppp.py` | Fase 1.bis (lo usan Fases 3+) |
| Aviso de privacidad simplificado (1 página) | ❌ no existe | construir `src/compliance/aviso_privacidad.py` + plantilla | Fase 7 |
| Aviso integral para sitio web | ❌ no existe | en `aviso_privacidad.py` | Fase 7 |
| Endpoint ARCO con timer 20 días hábiles | ❌ no existe | construir `src/compliance/arco.py` + endpoint FastAPI | Fase 7 |
| Cruce automático con SAT 69-B (flag riesgo_69b) | ❌ no existe | construir job que corre tras cada descarga DENUE + tras cada refresh 69-B | Fase 5.1 |
| Tagging de fuente legal por dato | ✅ existe (campo `fuentes` TEXT[] en establecimientos) | usar consistentemente | Fase 3+ |

### 1.7 Capa de API

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| App FastAPI con CORS + lifespan | ❌ no existe | construir `src/api/main.py` | Fase 8 |
| Auth JWT (cookie httpOnly) + bcrypt | ❌ no existe | construir `src/api/auth.py` | Fase 8 |
| Roles (admin / vendedor / jefe) con dependencias | ❌ no existe | construir `src/api/dependencies.py` | Fase 8 |
| `GET /prospectos` con filtros | ❌ no existe | en `src/api/routes/prospectos.py` | Fase 8 |
| `GET /prospectos/{id}` detalle | ❌ no existe | mismo | Fase 8 |
| `GET /rutas?origen=...` (TSP simplificado) | ❌ no existe | construir `src/api/routes/rutas.py` (heurística greedy de PostGIS) | Fase 8 |
| `POST /prospectos/{id}/contacto` (dispara compliance_log) | ❌ no existe | en `src/api/routes/prospectos.py` | Fase 8 |
| Tests de API con httpx + TestClient | ❌ no existe | en `tests/test_api/` | Fase 8 |

### 1.8 Capa de presentación (dashboard / UI)

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| Dashboard ejecutivo | ❌ no existe | **🔴 decisión pendiente** (ver §3) | Fase 8 |
| Mapa Leaflet con clustering | ❌ no existe | depende de la decisión arriba | Fase 8 |
| Reportes CSV por vendedor | ❌ no existe | endpoint FastAPI con StreamingResponse | Fase 8 |

### 1.9 Capa de operaciones (DevOps)

| Componente | Estado | Acción | Dónde |
|---|---|---|---|
| Tests con pytest | 🟡 smoke test existe | construir suite por capa, fixture Postgres efímero | Fase 1.bis y onwards |
| CI con GitHub Actions (tests + ruff + alembic check) | ❌ no existe | crear `.github/workflows/ci.yml` | Fase 1.bis |
| Scheduler APScheduler | ❌ no existe | construir `src/operations/scheduler.py` con jobs (refresh DENUE incremental, SAT 69-B mensual, regenerar score) | Fase 6+ |
| Deploy a Render (Web Service + Postgres + extensión PostGIS) | ❌ no existe | crear `render.yaml` + verificar que PostGIS está en plan starter | Fase 8 |
| Backups automáticos | ❌ no existe | usar el backup automático de Render Postgres + script local | Fase 8 |
| Monitoreo de errores (Sentry o equivalente) | ❌ no existe | opcional, evaluar en Fase 8 | Fase 8 |

---

## 2. Plan ajustado — orden recomendado de fases

### Fase 1.bis — Cimientos transversales (NUEVA — propuesta)

**Por qué existe:** sin esto, Fase 2 escribe código que no tiene `Settings`, `engine`, `logger`, ni helpers de compliance. Es la base que toda fase posterior usa.

**Entregables:**
- `src/core/config.py` — `Settings` con Pydantic, lee `.env`
- `src/core/db.py` — engine + session + `get_db` para FastAPI
- `src/core/logging.py` — loguru con sinks por nivel + archivo en `logs/`
- `src/core/models.py` — modelos ORM SQLAlchemy 2.0 declarativos para las 14 tablas
- `src/core/repos/` — repositorios por dominio (uno por bounded context: `establecimientos.py`, `vendedores.py`, etc.)
- `src/compliance/lfpdppp.py` — helper `registrar_operacion()`
- `tests/conftest.py` — fixture de Postgres efímero (testcontainers o DB de test dedicada)
- `.github/workflows/ci.yml` — pytest + ruff + `alembic check`
- Instalación de las deps que faltan (~30 paquetes vía `pip install -e ".[dev]"`)

**Estimación:** 2 días.
**Riesgo:** geopandas/fiona/pyproj pueden tener fricción de instalación en macOS Tahoe arm64. Mitigación: usar wheels (que ya hay para arm64 desde 2024).

### Fase 2 — Diseño de chequeos de calidad (alcance reducido)

**Cambio vs prompt v2:** ya no audita data heredada (no hay). Diseña los chequeos.

**Entregables:**
- `src/audit/duplicates.py`, `completeness.py`, `geo_anomalies.py`
- `notebooks/02_auditoria_denue.ipynb` (estructurado pero sin data — lo poblamos en Fase 3)
- `docs/auditoria/criterios_calidad.md` — qué se considera registro válido y qué se descarta

**Estimación:** 3 días.
**Riesgo:** bajo. Es código de validación contra reglas conocidas.

### Fase 3 — Descarga real DENUE (camino crítico)

**Entregables:**
- `src/ingestion/denue.py` — cliente completo (Cuantificar, BuscarEntidad paginado, Ficha, Nombre)
- `src/ingestion/denue_pipeline.py` — orquestador: para cada (entidad, SCIAN), descarga, valida (Fase 2), upsert.
- Descarga real:
  - 13 entidades × 8 SCIAN = 104 batches.
  - ~124,432 establecimientos a paginar 5,000 por request → ~25 requests por SCIAN×entidad.
  - Total: ~250 requests con throttling 60/min → ~4-5 horas de descarga.
- Reporte por entidad con conteo logrado vs Cuantificar previo (cobertura %).

**Entregables docs:**
- `notebooks/03_cobertura_geografica.ipynb` — mapa coroplético por entidad y por canal.

**Estimación:** 5 días (3 de código + 1 de descarga real + 1 de validaciones manuales).
**Riesgos:**
- INEGI puede tener throttling más estricto del que asumo. Mitigación: tenacity con backoff exponencial.
- 124K filas es mucho — hay que cargar en lotes con upsert por CLEE para que sea idempotente.

### Fase 4 — Enriquecimiento Google Places (con costo)

**Entregables:**
- `src/ingestion/places_api.py` — cliente Text Search + Place Details + cache 30 días + circuit breaker.
- `src/enrichment/matching.py` — matcher DENUE↔Google.
- `src/enrichment/cadenas.py` — detector de cadenas con fuzzy nombre.

**Decisiones de costo:**
- Estrategia recomendada: **enriquecer solo segmentos A y B** después de Fase 6 (scoring inicial). Eso reduce el universo de ~124K a ~15-25K (~$5-15 USD según cuotas Essentials).
- Free tier mensual: 10K calls Essentials gratis. Cuotas posteriores Essentials ~$0.005/call.
- Si vamos por todos los 124K Essentials: ~$620 USD. **No recomiendo**.
- Estrategia alternativa (más cara, más cobertura): enriquecer todos los Tortillerías top-decil + todos los AlimentoBalanceado + todos los Asociaciones (el universo más chico). ~5K calls. ~$25 USD.

**Estimación:** 4 días + ~$25 USD.
**Riesgo:** matching puede fallar mucho en establecimientos rurales (forrajeras de pueblo casi sin presencia en Google). Mitigación: tracking de `match_status` y aceptar que canal ForrajerasPecuario tendrá baja cobertura Google.

### Fase 5 — Cruce con datos públicos adicionales

**Entregables:**
- 5.1 `src/ingestion/sat_publica.py` + cron mensual + cruce automático que actualiza `riesgo_69b`.
- 5.2 `src/ingestion/inegi_indicadores.py` para ENIGH (consumo tortilla por entidad), SIAP (producción maíz), Censo (NSE por AGEB).
- 5.3 `src/ingestion/marco_geoestadistico.py` para cargar shapefiles AGEB en `agebs` con PostGIS, luego spatial join contra `establecimientos.geom`.
- 5.4 (opcional, esfuerzo investigación) CONAFAB + CANAMI: investigar fuentes alternativas, posiblemente listas DOF.
- 5.5 (opcional) SENASICA / SIAP padrón pecuario para granjas integradas — sólo si hay API consumible.

**Estimación:** 5 días núcleo (5.1, 5.2, 5.3) + ~3 días opcionales (5.4, 5.5).
**Riesgos:**
- Shapefile AGEBs INEGI pesa ~600 MB y la carga vía geopandas puede ser lenta. Mitigación: usar `ogr2ogr` o `shp2pgsql`.
- CONAFAB/CANAMI puede no tener fuente pública consumible. Si no, lo agendamos a Fase 6.5 manual (cuando tengas un PDF/Excel de socios, lo subes y yo lo parseo).

### Fase 6 — Algoritmo de scoring + asignación

**Entregables:**
- `src/enrichment/scoring.py` con dispatch por canal (ver §1.5 con pesos propuestos).
- `src/enrichment/asignacion.py` — auto-asignación por municipio.
- Vista materializada `vw_prospectos_priorizados` con refresh.
- Calibración: muestra de 50 prospectos top entregada al equipo de ventas, comparar conversión real vs score predicho.

**Estimación:** 4 días + tiempo de calibración (semanas, ya con visitas reales).
**Riesgo:** los pesos son hipótesis. La calibración es un loop largo. Mitigación: pesos como variables de entorno → A/B test sin redeploy.

### Fase 7 — Capa de cumplimiento LFPDPPP 2025

**Entregables:**
- `src/compliance/aviso_privacidad.py` + plantillas Jinja2 (simplificado y integral).
- `src/compliance/arco.py` + endpoints FastAPI (POST recibe solicitud, GET status, PUT respuesta).
- `docs/compliance_lfpdppp.md` — documento ejecutivo con inventario PII + bases legales + finalidades + retención.
- Generador de respuestas ARCO automatizado (acceso → CSV personal del solicitante).

**Estimación:** 4 días + revisión legal externa (no estimable).
**Riesgo:** los textos del aviso de privacidad **no deben publicarse sin revisión legal**. Yo redacto el draft y se lo pasas a tu abogado o asesoría LFPDPPP.

### Fase 8 — API + Dashboard

**Entregables:**
- API FastAPI completa con auth, roles, endpoints.
- Frontend (decisión pendiente — ver §3.D).
- Deploy a Render con `render.yaml`.
- Tests de integración end-to-end.
- Documento `docs/runbook.md` con procedimientos operativos (qué hacer si descarga DENUE falla, cómo rotar tokens, etc.).

**Estimación:** 7-12 días según decisión de frontend.
**Riesgo:** Render puede tener fricciones con extensión PostGIS en plan starter. Mitigación: validar antes de deploy real con un proyecto de prueba.

---

## 3. Decisiones que requieren tu input antes de Fase 2

Numeradas. 🔴 = bloqueante. 🟡 = ajustable después pero conviene hablar.

### 🟡 D1 — Fase 1.bis: ¿la metemos o vamos directo a Fase 2?

Mi propuesta es intercalar Fase 1.bis (cimientos transversales) antes de Fase 2 porque sin engine SQLAlchemy / Settings / logger / modelos ORM, el código de Fase 2 vivirá en limbo. Estimo 2 días.

Alternativa: meter cimientos como "primer día de Fase 2" sin hacerlo fase aparte — más rápido pero menos visible.

**Recomiendo Fase 1.bis aparte.** Decisión: ¿OK?

### 🟡 D2 — Modelos ORM SQLAlchemy: estilo

Tres opciones:
- **D2.A** Declarative imperativo `Mapped[...]` (estilo SQLAlchemy 2.0 nuevo, recomendado)
- **D2.B** Declarative clásico (estilo 1.x, más viejo)
- **D2.C** Sin modelos ORM, sólo SQL crudo + Pydantic models

Recomiendo D2.A. Mejor IDE support y type checking. Decisión: ¿OK?

### 🔴 D3 — Estrategia de costos Google Places (Fase 4)

Tres niveles:
- **D3.A — Conservador (~$5-15 USD).** Enriquecer solo segmentos A y B después de Fase 6 scoring. Cobertura: 15-25K registros.
- **D3.B — Balanceado (~$25 USD).** Enriquecer todos los AlimentoBalanceado + Asociaciones + tortillerías top-decil + todas las cadenas detectadas. ~5K calls.
- **D3.C — Cobertura alta (~$50-100 USD).** Enriquecer todo el universo Tortillerías + ForrajerasPecuario excepto los muy chicos. ~30-50K calls.

Tu budget es $100/mes total. Recomiendo **D3.B** primero, evaluar resultados, decidir si vale la pena ampliar. Decisión: ¿qué nivel?

### 🔴 D4 — Frontend del dashboard (Fase 8)

Tres caminos:
- **D4.A — Server-rendered con FastAPI + Jinja2 + HTMX.** Más simple, menos JS. Funciona remoto vía Render. Mantenimiento más barato.
- **D4.B — Frontend separado React + Vite + TypeScript.** Más rico, mejor UX, más esfuerzo. Estilo intergranel-iq pipeline.
- **D4.C — Solo HTML estático con Plotly + Leaflet (estilo intergranel-iq dashboard).** Compartido vía link de Render Static Site, sin login web. **Pero T4 (auth con 3 roles) requeriría algo más.**

Decisión condicionada: tú dijiste "T4 = A" (auth completa con login web), así que D4.C queda fuera. Entre D4.A y D4.B:
- **Recomiendo D4.A** para arrancar, migrar a D4.B sólo si el equipo necesita drag&drop tipo Kanban o vistas muy interactivas.

### 🟡 D5 — Cuándo tramitar Google Places API key

Dos momentos:
- **D5.A — Ahora (Fase 1.bis):** la tramitamos antes de Fase 4 para tener tiempo de detectar problemas con billing.
- **D5.B — Cuando lleguemos a Fase 4:** justo a tiempo, ahorra impostor de tener key sin usar.

Recomiendo **D5.A**: el setup de Google Cloud + billing + restricciones de IP toma ~30 min y es mejor hacerlo sin presión. La tramitación es gratis si no se usa.

### 🟡 D6 — Aviso de privacidad: redacción

- **D6.A** Yo te paso un draft (basado en LFPDPPP 2025 reformada y mejores prácticas) y tú lo revisas + lo manda a tu asesor legal.
- **D6.B** Tu asesor legal redacta desde cero, yo solo integro el texto al sistema.

Recomiendo **D6.A**. Más rápido y mi draft cubre 90% de lo común; el asesor solo afina.

### 🔴 D7 — Calibración del scoring (Fase 6)

¿Cómo calibramos los pesos del scoring por canal después del scoring inicial?

- **D7.A — Workshop con equipo de ventas:** sentamos 1-2 vendedores con 50 prospectos top, validan si el score corresponde a la realidad, ajustamos pesos.
- **D7.B — Tracking automático:** dejamos que pasen 2-3 meses, comparamos score predicho vs ganados/perdidos reales, ajustamos.
- **D7.C — Ambos (recomendado):** workshop inicial al cerrar Fase 6, tracking automático en producción.

Recomiendo **D7.C**. Workshop debe estar en tu calendario antes de Fase 6.

---

## 4. Resumen de tiempos y costo

| Fase | Días estimados | Costo USD |
|---|---:|---:|
| Fase 0 — Arqueología + scaffold | ✅ cerrada | 0 |
| Fase 1 — Reconciliación (este doc) | ✅ cerrada | 0 |
| Fase 1.bis — Cimientos transversales | 2 | 0 |
| Fase 2 — Chequeos de calidad | 3 | 0 |
| Fase 3 — Descarga DENUE | 5 | 0 |
| Fase 4 — Google Places | 4 | $25 (D3.B) |
| Fase 5 — Datos públicos adicionales (núcleo) | 5 | 0 |
| Fase 5 — Datos opcionales (CONAFAB/CANAMI/SENASICA) | 3 | 0 |
| Fase 6 — Scoring + asignación | 4 | 0 |
| Fase 7 — Compliance LFPDPPP | 4 + revisión legal | 0 (sistema) + asesoría (externa) |
| Fase 8 — API + Dashboard | 7-12 | Render ~$30/mes operación |
| **Subtotal trabajo** | **37-42 días** | **~$25 USD una vez + $30/mes operación** |

> Estos son días-hombre de un ingeniero senior dedicado. En la práctica, con tu cadencia (revisas, apruebas, vuelvo) probablemente sea **2-3 meses calendario** desde Fase 1.bis hasta Fase 8 productiva.

---

## 5. Próximo paso

Cuando me confirmes las 7 decisiones (idealmente "todo según tu recomendación" si te alcanza), doy "adelante" mental para Fase 1.bis y arranco con cimientos.

Si prefieres pensarlo, está bien. Mientras tanto, tienes:
- `CLAUDE.md` actualizado con estado Fase 1 cerrada.
- Este documento como roadmap a manota.
- Postgres + DB lista esperando.
