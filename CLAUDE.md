# CLAUDE.md — Memoria del proyecto CRM-Granos-MX

**Quién lee esto:** Claude Code (yo, en futuras sesiones) y cualquier ingeniero que entre al proyecto.
**Lo que hace este archivo:** te da el contexto completo del proyecto en una sola lectura para que no tengas que reconstruirlo cada vez.
**Reglas para mantenerlo:** cada vez que cierres una fase, actualizas (a) el estado, (b) decisiones nuevas tomadas, (c) riesgos descubiertos. No es opcional.

---

## 1. Estado del proyecto

**Fases cerradas:** 0 (arqueología + scaffold), 1 (reconciliación), 1.bis (cimientos), todas 2026-04-30.
**Próxima:** Fase 2 — diseño de chequeos de calidad. Bloqueada solo por la tramitación de Google Places API key (D5).
**Última actualización:** 2026-04-30 al cerrar Fase 1.bis.

### Capa transversal lista (Fase 1.bis)

- `src/core/config.py` — `Settings` Pydantic, `get_settings()` cacheada.
- `src/core/db.py` — `engine`, `SessionLocal`, `get_db` dependencia FastAPI, `Base` declarativa.
- `src/core/logging.py` — `setup_logging()` con loguru (consola + archivo + JSON prod).
- `src/core/models.py` — 14 modelos ORM SQLAlchemy 2.0 estilo `Mapped[...]`.
- `src/core/repos/` — `EstablecimientoRepo`, `VendedorRepo` (más se agregan al ritmo de cada fase).
- `src/compliance/lfpdppp.py` — `registrar_operacion()` para bitácora.
- `tests/conftest.py` — fixture `db` con transaction-per-test (rollback automático).
- `tests/test_smoke.py` + `tests/test_db.py` — **11 tests pasan**, ruff limpio.
- `.github/workflows/ci.yml` — Postgres+PostGIS service, ruff + pytest + alembic en cada PR.
- venv `.venv/` con `pip install -e ".[dev,notebooks]"` completo.

### Lo que está hecho
- Carpeta `CRM-Granos-MX/` creada al lado de los demás proyectos del monorepo, con scaffold completo y `git init`.
- Token INEGI DENUE validado contra el endpoint real (`/v1/consulta/Cuantificar/...` — el del prompt maestro estaba obsoleto).
- Dimensionamiento inicial: **124,432 establecimientos** en las 13 entidades priorizadas, repartidos en **4 canales de venta** (ver §5).
- Stack instalado y validado de punta a punta:
  - Postgres.app 18.3 + PostGIS 3.6.2 + pg_trgm 1.6 corriendo en localhost.
  - DB `crm_granos_mx` creada con extensiones habilitadas.
  - venv en `.venv/` con 4 deps mínimas (sqlalchemy, psycopg, alembic, python-dotenv).
  - Conexión Python ↔ Postgres verificada.
- Schema aplicado: **14 tablas + 4 vistas** del proyecto + 2 sistema PostGIS, con **6 índices GIST/GIN** (geom, fuzzy nombre, JSONB municipios, arrays canales/fuentes).
- Catálogo PII (`_columnas_pii`) sembrado con **21 columnas conocidas**, cada una con base legal y finalidad LFPDPPP.
- Migración Alembic `a1b2c3d4e5f6` (baseline) aplicada y registrada en `alembic_version`.
- `CLAUDE.md` raíz proyecto + `CLAUDE.md` raíz workspace + `notebooks/00_arqueologia.ipynb` listos.

### Lo que NO está hecho
- Cliente DENUE para descarga real — Fase 3.
- Cliente Google Places — Fase 4. API key no tramitada todavía.
- Aviso de privacidad LFPDPPP — Fase 7.
- Frontend — Fase 8.
- Comercial-app v2 paralelo — proyecto separado futuro (no parte de este).

---

## 2. Qué construye este proyecto (en una frase)

Sistema dual de inteligencia comercial para Intergranel: **mapea a todos los compradores potenciales de granos en México** (tortillerías + fabricantes de alimento balanceado + forrajeras rurales + asociaciones agropecuarias), los clasifica con scoring 0-100, los asigna a vendedores por zona, y respeta LFPDPPP 2025 desde el día uno.

---

## 3. Modelo de negocio que explica el diseño

Intergranel comercializa **maíz blanco** (a Tortillerías), **maíz amarillo + sorgo** (a Alimento Balanceado), y **granza** (subproducto del molido del maíz blanco) que se vende a forrajeras y fabricantes de alimento balanceado. **Un mismo cliente puede ser dual** (te compra producto y te vende subproducto), por eso el campo `canales[]` en `establecimientos` es un array, no un valor único.

```
                     INTERGRANEL
                          │
        ┌─────────────────┼─────────────────┐
        │ maíz blanco     │ maíz amarillo   │ granza (subproducto)
        ▼                 ▼                 ▼
┌────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│ TORTILLERÍAS   │  │ ALIMENTO         │  │ FORRAJERAS           │
│ (consumidor    │  │ BALANCEADO       │  │ (rural, vende a      │
│  final maíz    │  │ (Bachoco,        │  │  granjeros pequeños) │
│  blanco)       │  │  Purina, Nupec)  │  │                      │
└────────┬───────┘  └────────┬─────────┘  └──────────┬───────────┘
         │ produce granza    │                       │
         └───────────────────┴───────────────────────┘
                             │
                             ▼
                       ┌──────────────────┐
                       │ ASOCIACIONES     │
                       │ AGROPECUARIAS    │
                       │ (B2B2C: vende a  │
                       │  socios          │
                       │  ganaderos)      │
                       └──────────────────┘
```

---

## 4. Stack y arquitectura

| Capa | Tecnología | Notas |
|---|---|---|
| Lenguaje | Python 3.11+ (probado en 3.13.7) | |
| BD local | PostgreSQL 16 + PostGIS 3.4 vía **Postgres.app** | sin Docker, sin Homebrew |
| BD producción | Render PostgreSQL + extensión PostGIS | $7-20/mes |
| ORM / migraciones | SQLAlchemy 2.x + GeoAlchemy2 + Alembic | `target_metadata=None`, raw SQL en migraciones |
| HTTP | httpx + tenacity | retries con backoff exponencial |
| Validación | Pydantic v2 + Pydantic Settings | `.env` se lee con `Settings()` |
| Geo | shapely + geopandas + geopy | spatial joins se hacen en PostGIS, no en pandas |
| Fuzzy | rapidfuzz | nombre+dirección, threshold 80-90 |
| API | FastAPI + Uvicorn | JWT en cookie httpOnly |
| Auth | passlib (bcrypt) + python-jose (JWT) | 3 roles: admin/vendedor/jefe |
| Logs | loguru | sinks por nivel + archivo |
| Tests | pytest + pytest-asyncio + pytest-cov | DB de tests = Postgres efímero (testcontainers en Fase 1) |
| Linter | ruff (`E,F,I,N,W,B,UP`) | line-length 100 |

**Por qué no Docker:** Mac del operador es no-técnico, sin Homebrew. Postgres.app es 5-min install nativo con PostGIS incluido. La diferencia con producción Render es despreciable para este caso.

**Por qué no SQLAlchemy ORM declarativo todavía:** las migraciones Alembic baseline son SQL crudo (`op.execute(...)`) para máxima visibilidad y control, igual que en `intergranel-iq`. Los modelos ORM se introducen cuando el schema esté estable (probablemente Fase 1 cuando reconciliemos).

---

## 5. Los 4 canales de venta y los 8 SCIAN

| Canal | SCIAN | Descripción | En MX | En 13 prior |
|---|---|---|---:|---:|
| **Tortillerías** | 311830 | Tortillerías + molinos nixtamal | 111,805 | 77,876 |
| | 461160 | Comercio menor masa/tortillas | 51,912 | 33,483 |
| | 311212 | Harina de maíz nixtamalizada | 226 | 45 |
| | 311211 | Harina de trigo | 14 | 6 |
| **AlimentoBalanceado** | 311110 | Fabricantes alimento animal | 865 | 317 |
| **ForrajerasPecuario** | 434112 | Forrajeras rurales (mayoreo med. veterinarios) | 14,017 | 7,655 |
| | 434225 | Mayoreo granos alimenticios | 6,084 | 3,007 |
| **AsociacionesAgropecuarias** | 813110 | Asociaciones, cámaras y uniones de productores | 4,683 | 2,043 |
| **TOTAL** | 8 SCIAN | | **189,606** | **124,432** |

**Subtipos por canal** (campo `tipo_establecimiento`):

- **Tortillerías**: `tortilleria_tradicional`, `tortilleria_moderna`, `molino_nixtamal`, `harinera_maiz`, `harinera_trigo`, `comercio_masa`, `autoservicio`, `desconocido`.
- **AlimentoBalanceado**: `fabricante_industrial`, `desconocido`.
- **ForrajerasPecuario**: `forrajera_rural`, `mayoreo_granos`, `desconocido`.
- **AsociacionesAgropecuarias**: `asociacion_ganadera_local`, `union_ganadera_regional`, `sociedad_produccion_rural`, `camara`, `desconocido`.

### SCIAN excluidos (el prompt original los pedía, los descartamos con justificación)

| SCIAN | Motivo de descarte | Cuándo se usa |
|---|---|---|
| 311111, 311119 | **No existen en SCIAN 2018**. El correcto es 311110. | Nunca |
| 461110 | Abarrotes menudeo: 387,149 en priorizados → ruido masivo | Cruce on-demand Fase 5 |
| 431110 | Abarrotes mayoreo: 2,633 en priorizados, marginal | Cruce on-demand Fase 5 |
| 1121-1129 | **DENUE no tiene granjas pecuarias**, son sector primario | Fase 5 con SENASICA / SIAP / Censo Agropecuario |

### 13 entidades priorizadas (ordenadas por densidad combinada de los 4 canales)

| # | Estado | Cve INEGI | Total 4 canales | Notas |
|---|---|---|---:|---|
| 1 | EdoMex | 15 | 33,181 | densidad mayor, área metropolitana |
| 2 | Puebla | 21 | 18,036 | rural y urbano mezclados |
| 3 | Oaxaca | 20 | 16,830 | mayoría tortillerías, pocas forrajeras |
| 4 | CDMX | 09 | 13,650 | densidad urbana — pocas forrajeras |
| 5 | Veracruz | 30 | 9,773 | sureste rural, muchas asociaciones |
| 6 | Chiapas | 07 | 6,552 | rural alto, alta concentración A.G. |
| 7 | Hidalgo | 13 | 6,366 | |
| 8 | Tlaxcala | 29 | 5,917 | densidad alta de tortillerías |
| 9 | Morelos | 17 | 3,720 | |
| 10 | Yucatán | 31 | 2,890 | |
| 11 | Tabasco | 27 | 2,795 | |
| 12 | Quintana Roo | 23 | 1,049 | |
| 13 | Campeche | 04 | 873 | la más chica, alta proporción forrajeras |

---

## 6. Mapa del código (estado actual)

```
src/
├── core/         (vacío salvo __init__.py — config/db/logging/models en Fase 1)
├── ingestion/    (vacío — clientes DENUE/Places/SAT/INEGI en Fases 3-5)
├── audit/        (vacío — auditoría calidad data en Fase 2)
├── enrichment/   (vacío — matching DENUE↔Google y scoring en Fases 4 y 6)
├── compliance/   (vacío — LFPDPPP, ARCO, aviso privacidad en Fase 7)
└── api/          (vacío — FastAPI endpoints en Fase 8)
```

Cada subpaquete tiene un `__init__.py` con docstring que describe qué módulos van adentro y en qué fase. Léelos antes de implementar.

---

## 7. Mapa de la BD (post-baseline)

`db/schema.sql` es la **fuente de verdad textual del schema** (referencia humana). `migrations/versions/2026_04_30_*_baseline.py` la aplica a la DB. Todo cambio de schema futuro va por una nueva migración Alembic, no editando el schema.sql.

### Tablas principales

| Tabla | Propósito |
|---|---|
| `establecimientos` | tabla central — un establecimiento = una fila |
| `cadenas` | grupos detectados por fuzzy matching (sucursales de la misma marca) |
| `vendedores` | catálogo del equipo comercial |
| `usuarios` | auth con bcrypt + 3 roles (admin/vendedor/jefe) |
| `interacciones` | bitácora comercial (visitas, llamadas, cotizaciones, etc.) |
| `enriquecimiento_google` | datos de Google Places por establecimiento (1:1 cuando hay match) |

### Tablas auxiliares (compliance + trazabilidad)

| Tabla | Propósito |
|---|---|
| `_columnas_pii` | catálogo: qué columna de qué tabla lleva PII y bajo qué base legal |
| `compliance_log` | bitácora LFPDPPP: cada acceso/uso de PII queda registrado |
| `denue_descargas_log` | trazabilidad de descargas DENUE |
| `google_places_log` | log de calls a Places API + costo USD por call |
| `sat_lista_69b` | ingesta del Listado 69-B del SAT (Fase 5) |
| `indicadores_geograficos` | población, NSE, consumo tortilla por AGEB |
| `agebs` | shapefiles de AGEBs con geometría PostGIS |

### Vistas

- `vw_establecimientos_resumen` — join aplanado para dashboard.
- `vw_pipeline_vendedor` — KPIs por vendedor.
- `vw_cobertura_municipio` — agregados por municipio + canal + segmento ABC.
- `vw_prospectos_priorizados` — top por score, filtrable por canal y entidad.

---

## 8. Compliance LFPDPPP 2025 — reglas no negociables

1. **Toda columna que pueda contener PII** está en la tabla `_columnas_pii` con: `tabla, columna, base_legal, finalidad, retencion_meses`. Si una columna no está ahí, no se puede usar PII en ella. Es un catálogo de cumplimiento, defensa ante la Secretaría Anticorrupción y Buen Gobierno.

2. **Toda operación que toque PII** (lectura masiva, exportación, contacto comercial, transferencia) registra una fila en `compliance_log` con `usuario, tabla, columna_set, finalidad, fecha`. La función helper vive en `src/compliance/lfpdppp.py`. Endpoints FastAPI lo aplican vía dependencia.

3. **Datos del SAT distintos del Listado 69-B no se obtienen.** Art. 69 CFF prohíbe acceder a información tributaria de contribuyentes. Solo 69-B es público, y se descarga del Excel oficial mensual.

4. **Google Places sólo vía API oficial.** Scraping queda en Anexo del prompt maestro con triple confirmación. NO se ejecuta sin autorización explícita en chat.

5. **Cero PII jamás al repositorio.** `.env` está en `.gitignore`. Cualquier export con PII va a `data/exports/` (gitignored). Antes de cualquier operación destructiva o export masivo, se pregunta al usuario.

6. **ARCO (Acceso/Rectificación/Cancelación/Oposición)** debe responderse en ≤20 días hábiles. El timer arranca al recibir solicitud y vive en `compliance_log`. Endpoint en `src/compliance/arco.py` (Fase 7).

7. **Aviso de privacidad** se publica antes del primer contacto comercial real (Fase 7). Hay dos versiones: simplificado (1 página, primer contacto) e integral (sitio web).

---

## 9. Decisiones de diseño tomadas (cronológico)

### 2026-04-29
- **Proyecto independiente del legacy `intergranel-iq`.** No se toca el viejo. Inspiración sí, dependencia no.
- **Stack PostgreSQL + PostGIS** (no SQLite), local con Postgres.app, prod con Render.
- **Hosting Render** (ya conocido por el operador). Alternativas (Supabase, Vercel) descartadas por simplicidad.
- **Auth con 3 roles** (admin/vendedor/jefe), login web + recovery — igual que el viejo proyecto que sí funcionaba.
- **Comercial-app v1 NO se integra.** Si Intergranel quiere flujo post-conversión, será un comercial-app v2 nuevo paralelo (proyecto separado, futuro).
- **Tabla catálogo `_columnas_pii`** (en lugar de columna boolean por fila) como mecanismo de defensa LFPDPPP.

### 2026-04-30
- **4 canales de venta** (no 2 como decía el prompt original): Tortillerías, AlimentoBalanceado, ForrajerasPecuario, AsociacionesAgropecuarias.
- **8 SCIAN primarios validados contra DENUE.** El prompt traía 311111/311119 que no existen — corregido a 311110.
- **URL DENUE correcta es `/v1/consulta/Cuantificar/...`** (con `/consulta/` extra). El prompt traía `/v1/Cuantificar/` que devuelve 404.
- **SCIAN 461110/431110 (abarrotes) excluidos de descarga primaria** — 387K y 2.6K respectivamente, son ruido. Quedan como cruce on-demand Fase 5.
- **Granjas pecuarias (SCIAN 1121-1129) NO están en DENUE.** Para ellas hay que ir a SENASICA/SIAP/Censo Agropecuario (Fase 5).
- **CANAMI (Cámara Nacional Maíz Industrializado) sitio web no resuelve DNS.** Pendiente Fase 5: investigar fuentes alternativas.
- **Modelo de canales como `TEXT[]` (array PostgreSQL)**, no campo único. Permite establecimientos duales (compradores y vendedores de subproducto).

---

## 10. Riesgos identificados

### Riesgos técnicos
- **Google Drive sync vs git.** El proyecto vive dentro de Google Drive sincronizado. Operaciones git largas pueden colisionar con la sync de Drive y corromper. Mitigación: si vemos errores raros en git, sospecharlo primero. El proyecto vecino `intergranel-iq` tiene el mismo riesgo y no ha tenido incidentes serios.
- **Cobertura de Postgres.app vs Render.** Versiones distintas (Postgres.app 17 vs Render 16), funciones marginales pueden diferir. Mitigación: ejecutar tests en CI contra Postgres 16 antes de cada deploy. Para Fase 0 no aplica.
- **Token INEGI rate limit.** 60 req/min según buenas prácticas. Una descarga nacional con 124,432 registros + paginación podría tomar 4-6 horas. Mitigación: throttling con tenacity, persistencia incremental, retomar desde último estado.

### Riesgos de cumplimiento
- **Aviso de privacidad no existe todavía.** Mientras estemos en arqueología/scaffold no aplica. Pero antes del primer contacto comercial real (Fase 8) DEBE estar publicado.
- **`razon_social` puede contener nombre de PF (persona física).** Se marca PII en `_columnas_pii`. Cualquier tabla de prospectos que se exporte sin filtrar PII rompe LFPDPPP.
- **Token INEGI en chat de Claude.** El usuario lo pasó en texto plano. Riesgo bajo (sesión privada), pero rotarlo si se duda.

### Riesgos de proyecto
- **Cambio de SCIAN del prompt original.** Cualquier docs externos (slides, propuestas) que ya cite los 8 SCIAN del prompt requiere actualizar. Si alguien sigue al pie de la letra el prompt sin leer este CLAUDE.md, va a buscar SCIAN que no existen.
- **Granjas integradas no se cubren en Fases 3-4.** Bachoco propia, porcícolas grandes son grandes consumidores pero requieren fuentes que no son DENUE. Si el equipo comercial pregunta "¿y Bachoco granjas?", la respuesta hoy es "Fase 5".

---

## 11. Glosario del dominio

| Término | Significado |
|---|---|
| **DENUE** | Directorio Estadístico Nacional de Unidades Económicas, mantenido por INEGI. Padrón público actualizado ~semestralmente. |
| **CLEE** | Clave Única de Establecimiento del DENUE. 28 caracteres. Estructura: 2 entidad + 3 municipio + 6 SCIAN + 6 número + 6 ceros + carácter verificador. |
| **SCIAN** | Sistema de Clasificación Industrial de América del Norte. INEGI usa SCIAN 2018 (no 2023). 6 dígitos clasifican actividad económica. |
| **AGEB** | Área Geoestadística Básica. Subdivisión municipal de INEGI. Es la unidad mínima para nivel socioeconómico (NSE) y muchos indicadores. |
| **NSE** | Nivel Socioeconómico. Por AGEB hay clasificación A/B+/B/C+/C/C-/D+/D/E. Importa para scoring (mayor NSE → mayor capacidad de compra). |
| **ENIGH** | Encuesta Nacional de Ingresos y Gastos de los Hogares. Mide consumo de tortilla per cápita por entidad. |
| **SIAP** | Servicio de Información Agroalimentaria y Pesquera (SADER). Datos de producción agrícola y pecuaria. |
| **SADER** | Secretaría de Agricultura y Desarrollo Rural. Sustituyó a SAGARPA. |
| **SENASICA** | Servicio Nacional de Sanidad, Inocuidad y Calidad Agroalimentaria. Tiene padrón de unidades pecuarias certificadas. |
| **CONAFAB** | Consejo Nacional de Fabricantes de Alimento Balanceado. Cámara que agrupa a Bachoco, Purina, Nupec, ALPESA, etc. ~80 socios. |
| **CANAMI** | Cámara Nacional del Maíz Industrializado. Agrupa harineros (Maseca/Gruma, Minsa, Harimasa) y procesadores. |
| **Listado 69-B** | Lista oficial del SAT con contribuyentes que emitieron operaciones presuntamente inexistentes. Pública. Usar para excluir prospectos riesgosos. |
| **LFPDPPP** | Ley Federal de Protección de Datos Personales en Posesión de los Particulares. Reformada Mar-2025. Autoridad: Secretaría Anticorrupción y Buen Gobierno (ya no INAI). Multas hasta 320,000 UMAs. |
| **ARCO** | Derechos del titular de datos: Acceso, Rectificación, Cancelación, Oposición. Plazo de respuesta: 20 días hábiles. |
| **Granza** | Subproducto del molido del maíz blanco para tortillería. Va para alimento balanceado / forrajeras. Conecta económicamente Tortillerías ↔ Pecuario. |
| **Forrajera** | Tienda de pueblo que vende alimento balanceado, granos, alfalfa al ganadero pequeño. Casi siempre rural. SCIAN 434112. |
| **Estrato** (DENUE) | Rango de personal ocupado. "0 a 5 personas", "6 a 10", "11 a 30", "31 a 50", "51 a 100", "101 a 250", "251 y más". Sirve como proxy de tamaño. |

---

## 12. Cómo trabajar con este proyecto

### Cuando tomes una decisión nueva
1. Anótala en §9 con fecha.
2. Si invalida algo del prompt maestro, di explícitamente qué del prompt cambia.
3. Si crea nuevo riesgo, agrégalo a §10.

### Cuando descubras que el prompt maestro se equivoca
- **No improvises silenciosamente**. Documenta el cambio en §9 con justificación con datos (igual que con SCIAN 311111 → 311110).
- **Pregunta al operador antes de avanzar** si el cambio toca alcance o presupuesto.

### Cuando agregues una columna nueva con PII
1. Añadirla a la tabla.
2. **Inmediatamente** insertar fila en `_columnas_pii` con base legal y finalidad.
3. Si vas a exportar esa columna, dependencia FastAPI tiene que registrar en `compliance_log`.

### Cuando agregues una migración
- Sigue las reglas de `intergranel-iq/MIGRATIONS.md` (vecino) — están bien escritas. Las copio adaptadas a `MIGRATIONS.md` de este proyecto cuando aparezca la primera migración real (post-baseline).
- Antes de `alembic upgrade head` en producción: backup. `pg_dump` > archivo timestampado.
- Para SQLite el viejo proyecto tenía batch operations; aquí no aplica (Postgres soporta `ALTER TABLE` sin restricciones equivalentes).

### Cuando vayas a gastar dinero
- Cualquier llamada a Google Places: estimar costo antes en USD, mostrar al operador, esperar confirmación.
- Circuit breaker: si gasto mensual > `MONTHLY_BUDGET_USD` (default 100), pausar.
- Render: cualquier upgrade de plan o servicio nuevo → confirmación previa.

### Cuando algo te parezca raro
- Pregunta. El operador prefiere preguntas tontas a improvisaciones costosas.

---

## 13. Referencias rápidas

- **Prompt maestro v2** del proyecto: el operador lo tiene en su carpeta personal; partes citadas verbatim están en este CLAUDE.md cuando aplican.
- **Proyecto vecino legacy:** [`intergranel-iq/`](../intergranel-iq/) — sólo referencia, no se toca.
- **Otro proyecto vecino:** [`comercial-app/`](../comercial-app/) — flujo de venta v1 no integrado a este proyecto.
- **DENUE API:** `https://www.inegi.org.mx/app/api/denue/v1/consulta/...` (URL correcta, con `/consulta/`).
- **Token INEGI gestionado:** ver `.env` (gitignored). Otorgado 2026-04-30 dedicado a este proyecto.
- **Setup local Postgres:** [`db/postgres_setup.md`](./db/postgres_setup.md).
- **Bootstrap dev:** ver [README.md](./README.md) §Quick start.
