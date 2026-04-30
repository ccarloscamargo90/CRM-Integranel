# CRM-Granos-MX

**Sistema de Inteligencia Comercial dual** para Intergranel:
- **Canal Tortillerías** — tortillerías, molinos de nixtamal, harineras, distribuidores de masa (compran maíz blanco).
- **Canal Alimento Balanceado** — fabricantes de alimento para ganado y pet food, granjas integradas (compran maíz amarillo, sorgo, granza).

> La granza, subproducto del molido en Tortillerías, alimenta el Canal Alimento Balanceado. Un mismo establecimiento puede ser **dual** — comprador y vendedor a la vez.

---

## Estado

**Fase actual:** 0 — Arqueología comparativa + scaffold (en curso, 2026-04-30).

**Roadmap (8 fases):**
1. Fase 0 — Arqueología y scaffold ⬅️ aquí
2. Fase 1 — Reporte de reconciliación
3. Fase 2 — Auditoría de la data DENUE
4. Fase 3 — Expansión nacional vía DENUE API (13 entidades centro-sureste)
5. Fase 4 — Enriquecimiento con Google Places API
6. Fase 5 — Cruce con datos públicos (SAT 69-B, INEGI Indicadores, Marco Geoestadístico)
7. Fase 6 — Algoritmo de scoring de prospectos
8. Fase 7 — Capa de cumplimiento LFPDPPP 2025
9. Fase 8 — API de prospección + dashboard

Detalles en [`CLAUDE.md`](./CLAUDE.md).

---

## Stack

- Python 3.11+ (probado en 3.13)
- PostgreSQL 16 + PostGIS 3.4 (local: Postgres.app, prod: Render)
- SQLAlchemy 2.x + Alembic + GeoAlchemy2
- FastAPI + Uvicorn (API) + Jinja2 (server-rendered)
- Pydantic v2 + Pydantic Settings (config + validación)
- httpx + tenacity (cliente HTTP con retries)
- pandas + rapidfuzz (limpieza, fuzzy matching)
- geopandas + shapely + geopy (geo)
- pytest + ruff + mypy (calidad)

---

## Quick start (desarrollador)

### 1. Clonar y entrar

```bash
cd "/Users/carlosacamargo/Library/CloudStorage/GoogleDrive-ccarloscamargo90@gmail.com/Mi unidad/1) INTERGRANEL/CODIGO CLAUDE/CRM-Granos-MX"
```

### 2. Instalar PostgreSQL local

Sigue [`db/postgres_setup.md`](./db/postgres_setup.md) — instala **Postgres.app** (5 min, drag & drop, PostGIS incluido).

### 3. Crear entorno virtual e instalar deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,notebooks]"
```

### 4. Variables de entorno

```bash
cp .env.example .env
# Editar .env con tus tokens reales
```

### 5. Crear la base de datos y aplicar migraciones

```bash
createdb crm_granos_mx
psql crm_granos_mx -c "CREATE EXTENSION postgis;"
alembic upgrade head
```

### 6. Verificar que todo arranca

```bash
pytest -v
```

---

## Estructura del repositorio

```
CRM-Granos-MX/
├── CLAUDE.md                ← memoria viva del proyecto (LEE ESTO PRIMERO)
├── .env.example
├── README.md
├── requirements.txt
├── pyproject.toml
├── alembic.ini
├── src/
│   ├── core/                ← config, db, logging, modelos SQLAlchemy
│   ├── ingestion/           ← clientes DENUE, Google Places, SAT, INEGI
│   ├── audit/               ← duplicados, completitud, anomalías geo
│   ├── enrichment/          ← fuzzy matching, scoring de prospectos
│   ├── compliance/          ← LFPDPPP 2025, aviso privacidad, ARCO
│   └── api/                 ← endpoints FastAPI
├── notebooks/               ← Jupyter notebooks por fase
├── data/                    ← raw / processed / exports (gitignored)
├── docs/                    ← arquitectura, glosario, compliance
├── db/
│   └── schema.sql           ← DDL de referencia (la verdad vive en Alembic)
├── migrations/              ← migraciones Alembic versionadas
└── tests/
```

---

## Compliance

Este proyecto trata datos personales de personas físicas con actividad empresarial.
Aplica la **LFPDPPP reformada 2025** (autoridad: Secretaría Anticorrupción y Buen Gobierno).

Reglas no negociables:
1. Toda columna con datos personales se marca en la tabla `_columnas_pii`.
2. Cada operación que toque datos personales se registra en `compliance_log`.
3. Datos del SAT distintos del Listado 69-B no se obtienen — protege el Art. 69 CFF.
4. Google Places se consume **únicamente** vía API oficial. Scraping queda en Anexo con triple confirmación.
5. Ningún `.env` ni dump con PII jamás se sube al repositorio.

Detalles en [`docs/compliance_lfpdppp.md`](./docs/compliance_lfpdppp.md) (se redacta en Fase 7).

---

## Relación con otros proyectos del monorepo

- **`intergranel-iq/`** — sistema legacy de inteligencia de mercado + módulo de prospección. **No se toca.** Solo es referencia histórica.
- **`comercial-app/`** — flujo de venta v1 (PEDIDO→COBRANZA). Cuando llegue Fase 8, este proyecto **no** integra con la v1; se planea un `comercial-app v2` paralelo.
- **`intergranel-iq` y `CRM-Granos-MX` son independientes**: bases de datos separadas, deploys separados, código separado.
