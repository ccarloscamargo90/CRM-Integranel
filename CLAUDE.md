# CLAUDE.md — Memoria del proyecto CRM-Granos-MX

**Quién lee esto:** Claude Code (yo, en futuras sesiones) y cualquier ingeniero que entre al proyecto.
**Lo que hace este archivo:** te da el contexto completo del proyecto en una sola lectura para que no tengas que reconstruirlo cada vez.
**Reglas para mantenerlo:** cada vez que cierres una fase, actualizas (a) el estado, (b) decisiones nuevas tomadas, (c) riesgos descubiertos. No es opcional.

---

## 1. Estado del proyecto

**Fases cerradas:** 0, 1, 1.bis, 2, 3, 4, 5.1, 5.2, 5.3, 5.4+5.5, 6, 7, 8.A, **8.B (Dashboard web)**, todas 2026-04-30 / 2026-05-01.
**Próxima:** Fase 8.C — Deploy Render (render.yaml + Procfile).
**Última actualización:** 2026-05-01 al cerrar Fase 8.B.

### Fase 8.B — Dashboard server-rendered (cierre)

**Stack web:**
- **Jinja2** templates en `src/api/templates/` (Jinja2Templates de FastAPI).
- **HTMX 1.9.12** vía CDN para swaps reactivos (filtros lista, etc.).
- **Tailwind CSS 3.4** vía CDN (`cdn.tailwindcss.com`).
- **Leaflet 1.9.4** + **leaflet.markercluster 1.5.3** vía unpkg para el mapa.
- Tile provider: OpenStreetMap (free, sin API key).
- CSS custom mínimo en `src/api/static/app.css` (mapa, score-bar, htmx-indicator).

**Templates (`src/api/templates/`):**
- `base.html` — layout con nav + footer + slots (content, scripts, mensaje).
- `login.html` — form simple username/password.
- `dashboard.html` — KPIs (total/A/B/riesgo), distribución canal, pipeline, top 10.
- `lista.html` — tabla con filtros HTMX (canal, segmento, etapa, entidad, búsqueda).
- `partials/lista_filas.html` — fragment con `<tr>` que HTMX swap-ea en `#tabla`.
- `detalle.html` — info completa + form contacto + historial pipeline + interacciones.
- `mapa.html` — Leaflet con clustering, color por segmento ABC, popup con link a detalle.

**Rutas web (`src/api/web.py`):**
- `GET /login`, `POST /login` (form), `POST /logout` — flujo HTML completo.
- `GET /` — dashboard con queries agregadas (vendedor solo ve lo suyo).
- `GET /lista` — listado paginado a 100 con filtros.
- `GET /lista/fragment` — fragment HTMX, swap-ea solo `#tabla`.
- `GET /prospecto/{id}` — detalle + compliance log automático.
- `POST /prospecto/{id}/contacto` — registra Interaccion + cambia pipeline + redirect con flash.
- `GET /mapa` — vista Leaflet.
- `GET /api/mapa-data` — JSON `[{id,nombre,lat,lon,canales,score,segmento_abc}]`,
  filtros canal/segmento/estado_codigo, limit clampeado [100, 5000], default 1000.

**Diseño de auth para web:** dependencia `get_current_user_web()` que devuelve
`Usuario | None` en lugar de levantar 401. Cada ruta hace su propio
`if not user: redirect /login`. Esto evita que el navegador reciba JSON 401 que
no sabe interpretar.

**Compartido con API:** mismo cookie `crm_token` JWT, mismas funciones
`crear_jwt`/`verify_password`. Web y API son intercambiables — puedes loguearte
por API y consumir HTML, o viceversa.

**Tests (19 nuevos en `test_api_web.py`):**
- Login form GET/POST OK/wrong-password.
- Dashboard sin auth redirige; con auth renderiza KPIs y top10.
- Lista renderiza tabla; fragment HTMX devuelve solo `<tr>`; sin auth 401;
  filtro `q` busca por nombre.
- Detalle 200/404; POST contacto redirige con mensaje y cambia pipeline;
  tipo inválido redirige con error.
- Mapa renderiza HTML; `/api/mapa-data` devuelve JSON con coords correctas;
  filtra por estado_codigo; sin auth 401.
- Logout borra cookie y redirige.

**Total 189/189 tests pasan, ruff limpio.**

**Smoke browser real (Claude Preview):** login admin → dashboard con 136,012
totales / 27,951 segmento A / distribución por canal correcta → lista filtrada
HTMX a Tortillerías muestra Industrias del Maíz Puebla 80, Chocolate Mayordomo
Trujano, Chilim Balam → click detalle muestra Industrias del Maíz Puebla con
rating ★4.5 31 reseñas, tel real, sitio LATORTI.MX → registrar llamada con
cambio de pipeline → flash "Contacto registrado" + pipeline a "contactado" +
historial actualizado → mapa Leaflet con clustering muestra 1000 marcadores
distribuidos correctamente; filtro Aguascalientes auto-zoom a 848 + 89 + 56 + 7.

**`launch.json` raíz workspace:** entrada `crm-api` agregada para preview en
puerto 8767.

### Fase 8.A — API REST FastAPI con auth (cierre)

**Auth (`src/api/auth.py`):**
- `hash_password` / `verify_password` con **bcrypt directo** (no passlib —
  passlib 1.7.4 no soporta bcrypt 5.x). Trunca a 72 bytes (límite del algoritmo).
- `crear_jwt` / `decodificar_jwt` con HS256 + `JWT_SECRET_KEY` desde `.env`.
  Expiración configurable, default 480 minutos (8 horas).
- `JWT_SECRET_KEY` y `SECRET_KEY` generados con `secrets.token_urlsafe(64)`
  y guardados en `.env` (gitignored).

**Dependencias FastAPI (`src/api/dependencies.py`):**
- `get_db` — sesión SQLAlchemy por request.
- `get_current_user` — lee cookie `crm_token`, valida JWT, devuelve `Usuario` activo.
- `require_role(*roles)` — factory de dependencia para autorización por rol.

**Rutas:**
- `POST /auth/login` — username + password, setea cookie httpOnly + Secure
  (Secure solo en producción), SameSite=Lax, max-age = `JWT_EXPIRE_MINUTES`.
- `POST /auth/logout` — borra cookie.
- `GET /auth/me` — info del usuario actual.
- `GET /prospectos` — listado con filtros canal/segmento/estado_pipeline/
  estado_codigo/score_min/riesgo_69b. **Vendedor solo ve sus prospectos
  asignados.** Order by `score_prioridad DESC NULLS LAST`. Paginación
  `limit (1-500, default 50)` + `offset`.
- `GET /prospectos/{id}` — detalle completo (incluye PII teléfono, email,
  contacto). **Compliance log automático** con base legal "Interés legítimo
  comercial B2B + relación laboral con Intergranel".
- `POST /prospectos/{id}/contacto` — registra `Interaccion` (visita/llamada/
  email/whatsapp/cotizacion/pedido/muestra/seguimiento). Opcionalmente
  cambia `estado_pipeline` y registra fila en `pipeline_etapa_historial`.

**App (`src/api/main.py`):** FastAPI con CORS configurable, lifespan, /health, /.

**Seed inicial (`scripts/seed_admin.py`):** Idempotente. Si no se pasan args,
genera password aleatorio con `secrets.token_urlsafe(16)` y lo imprime una
sola vez. Si ya existe el usuario, lo deja.

**Tests (20 nuevos):**
- 8 en `test_api_auth.py` — login OK/wrong-password/inactivo/inexistente,
  /me con/sin cookie, logout, token inválido.
- 12 en `test_api_prospectos.py` — listado sin auth (401), admin ve todos,
  vendedor solo los suyos, filtros segmento/canal, detalle 200/404/403,
  contacto crea interacción + cambia pipeline + 403 ajeno + 422 tipo inválido.

**Total 170/170 tests pasan, ruff limpio.**

**Smoke real (uvicorn local):**
- Login admin: 200, cookie httpOnly OK.
- /auth/me con cookie: 200.
- /prospectos sin auth: 401.
- /prospectos?segmento=A&limit=3: 27,951 totales, top MALTA TEXO/AGRIBRANDS
  PURINA/ALBAPESA con score 100 + etiqueta CONAFAB.
- /prospectos/{id}: detalle real con rating Google ★3.9.
- /docs: Swagger UI funciona.
- 8 rutas en OpenAPI.

**Modelo `Establecimiento` actualizado:** se agregó `etiquetas TEXT[]` que
faltaba en el ORM aunque la migración 9602d1aaf900 ya había agregado la
columna a la BD.

### Fase 7 — Aviso privacidad LFPDPPP + ARCO (cierre)

**Documentos (drafts para asesor legal):**
- `docs/aviso_privacidad_simplificado.md` — 1 página, primer contacto comercial.
- `docs/aviso_privacidad_integral.md` — versión web completa (10 secciones).
- `docs/compliance_lfpdppp.md` — inventario ejecutivo: 21 columnas PII,
  4 bases legales, 6 finalidades primarias + 2 secundarias, plan retención
  por categoría, sanciones, 7 pendientes operativos para asesor + operador.

**Módulo ARCO (`src/compliance/arco.py`):**
- `registrar_solicitud()` — alta con folio único `ARCO-YYYYMMDD-NNN` y
  cálculo automático de `fecha_limite_respuesta` (+20 días hábiles).
- `listar_pendientes()` — todas las solicitudes en `recibida`/`en_proceso`
  con días restantes calculados.
- `listar_proximas_a_vencer(dias=3)` — alertas tempranas.
- `marcar_vencidas()` — job diario que pasa a estatus `vencida`.
- `responder_solicitud()` — registra respuesta y cambia a
  `respondida`/`no_procedente`. Compliance log automático.
- `exportar_acceso()` — para tipo='acceso', genera CSV con todos los datos
  del titular (cumple Art. 22 LFPDPPP).

**Migración `e77ccdc77b2c`:** crea tabla `arco_solicitudes` con folio único,
4 tipos (acceso/rectificación/cancelación/oposición), 5 estatus, datos del
solicitante, fechas de SLA, y referencia a `establecimientos` y `usuarios`.

**CLI:** `--arco-pendientes` (lista pendientes + marca vencidas).

**7 tests del módulo ARCO** (sin red). Total **150/150 pasan**, ruff limpio.

**Pendientes operativos (no bloquean, requieren acción del operador):**
1. Revisión legal de avisos por asesor LFPDPPP.
2. Configurar email `datos@intergranel.mx`.
3. Designar Responsable de Protección de Datos Personales.
4. Capacitar a vendedores sobre captura de PII.
5. Publicar aviso integral cuando exista sitio web operativo.

### Fase 5.4 + 5.5 — Fuentes complementarias (cierre)

CONAFAB sí responde (https://conafab.org), CANAMI no existe (dominio inactivo),
SENASICA SSL roto. **Decisión:** unificar en seed YAML curado con socios
conocidos públicamente.

- `data/seeds/fuentes_complementarias.yaml` — 22 razones sociales con
  etiquetas: CONAFAB (alimento balanceado), PECUARIO_GRANDE (Bachoco,
  Pilgrim's, Norson, Granjas Carroll, Keken, Sukarne), HARINERO_INDUSTRIAL
  (Gruma/Maseca, Minsa, Harimasa, Molinera de México, Alimentos Pliego,
  Industrias del Maíz Puebla).
- `src/ingestion/fuentes_complementarias.py` — `aplicar_etiquetas()` cruza
  por razón social UPPER+TRIM y agrega tags al array `etiquetas[]` con
  `array_unique`.
- Migración `9602d1aaf900` — añade `establecimientos.etiquetas TEXT[]`
  con índice GIN.
- CLI: `--aplicar-etiquetas`. Compliance log automático.

**Resultado real:** 292 establecimientos etiquetados (242 HARINERO_INDUSTRIAL,
49 CONAFAB, 15 PECUARIO_GRANDE).

### Fase 6 — Scoring + asignación (cierre)

- `src/enrichment/scoring.py` — algoritmo con dispatch por canal:
  - **Tortillerías** (suma 100): tamaño 20, antigüedad 10, vol Google 25,
    pobreza inversa 10, contacto 10, consumo per cápita 10, cadena 15.
  - **AlimentoBalanceado**: tamaño 35, antigüedad 10, vol Google 5,
    contacto 15, cadena 10, producción maíz 25.
  - **ForrajerasPecuario**: tamaño 25, antigüedad 10, vol Google 15,
    contacto 15, producción maíz 15, cadena 10, pobreza inv 10.
  - **AsociacionesAgropecuarias**: tamaño 15, antigüedad 5, vol Google 5,
    contacto 15, producción maíz 25, cadena 5, pobreza inv 5,
    presencia estatal 25.
- **Bonificaciones por etiqueta** (suman al base): CONAFAB +15,
  PECUARIO_GRANDE +10, HARINERO_INDUSTRIAL +10.
- **Riesgo 69-B** descalifica → segmento_abc = 'X'.
- **Segmento ABC** por percentil global: top 20% A, 20-60% B, resto C.
- `asignar_vendedores_por_municipio()` — UPDATE basado en
  `vendedores.municipios_ids` JSONB. No sobrescribe asignaciones manuales.
- CLI: `--calcular-scores` (10 segundos para 136K), `--asignar-vendedores`.
- 12 tests del scoring (sin DB). **Total 143/143 pasan.**

**Resultado real (2026-05-01):**
- 136,012 establecimientos scoreados, 0 descartados (sin riesgo 69-B).
- Distribución: A=27,951 / B=55,400 / C=52,661.
- Top global todos AlimentoBalanceado con CONAFAB:
  AGRIBRANDS PURINA 100/100, MALTA TEXO 100/100, ALBAPESA 100/100,
  PROTEINAS ENERGETICOS Y OLEOS 100/100, GRUPO PORCICOLA 96/100, BACHOCO.
- Top tortillerías: Industrias del Maíz Puebla (80), Chocolate Mayordomo
  Oaxaca (76), Chilim Balam (74), Molinera de México (74).
- Por canal: AlimentoBalanceado 442/442 en A; Asociaciones 2,399 en A
  (todas son cámaras valiosas); ForrajerasPecuario 11,820 A;
  Tortillerías 13,290 A + 54,870 B + 52,661 C.

**Limitación conocida:** segmento ABC por percentil global hace que canales
chicos (AlimentoBalanceado, Asociaciones) caigan casi todos en A. Para Fase
6.1 (calibración) se puede cambiar a percentil POR CANAL si el equipo de
ventas lo solicita en el workshop.

### Fase 5.2 — INEGI Indicadores (cierre)

- `data/seeds/indicadores_geograficos.yaml` — 64 valores curados de fuentes
  públicas oficiales (Censo 2020, ENIGH 2022, SIAP 2024, CONEVAL 2022).
  4 indicadores por entidad × 16 entidades:
  - `consumo_tortilla_kg_per_capita_anio` (rango: 67-92 kg)
  - `poblacion_total` (rango: 928K-17M)
  - `produccion_maiz_grano_blanco_ton` (rango: 4K-1.75M ton)
  - `pct_pobreza` (rango: 24%-67%) — proxy capacidad de compra
- `src/ingestion/inegi_indicadores.py` — loader YAML → tabla
  `indicadores_geograficos` con UPSERT por (nivel, cve, indicador, anio).
- CLI: `--cargar-indicadores`. Compliance log automático.
- Operativo: refrescar manualmente cuando INEGI publique ENIGH (cada 2 años),
  SIAP (anual), Censo (cada 5 años). Una API client real queda como mejora
  futura cuando se requiera.

### Fase 5.3 — Marco Geoestadístico AGEB (cierre)

- `src/ingestion/marco_geoestadistico.py` — loader genérico de shapefiles
  INEGI con geopandas. Reproyecta a EPSG:4326 si está en LCC México.
  Detecta columnas `CVEGEO`/`CVE_ENT`/`CVE_MUN`/`POBTOT` automáticamente.
  UPSERT por `cve_ageb`. Carga ~1000 filas/segundo.
- `asignar_ageb_a_establecimientos()` — spatial join PostGIS
  `ST_Within(establecimientos.geom, agebs.geom)` que actualiza
  `establecimientos.ageb` con cobertura ~10s para 136K establecimientos
  (gracias al índice GIST en `agebs.geom`).
- CLI: `--cargar-agebs <shp>` y `--asignar-agebs`.
- `data/seeds/README_marco_geoestadistico.md` — guía operativa para
  descargar shapefiles INEGI manualmente (50-200 MB por entidad, no se
  versionan en repo).

**Decisión de diseño:** la descarga del Marco Geoestadístico NO se automatiza
porque los IDs de archivos del catálogo INEGI cambian con cada publicación.
El operador descarga del catálogo oficial y le pasa la ruta al CLI.

### Fase 5.1 — SAT Lista 69-B (cierre)

- `src/ingestion/sat_publica.py` — descarga el CSV oficial mensual desde
  `omawww.sat.gob.mx/cifras_sat/Documents/Listado_Completo_69-B.csv`,
  parsea (latin-1, salta 2 líneas de aviso legal), upsert en `sat_lista_69b`
  con conflict por (rfc, fecha_publicacion_dof). Distingue 4 estatus:
  Definitivo / Presunto (RIESGO) y Desvirtuado / Sentencia Favorable (LIMPIO).
- `src/enrichment/cruzar_69b.py` — cruce dual: 1) RFC exacto (alta confianza),
  2) razón social uppercased (fallback cuando DENUE no trae RFC). Marca
  `establecimientos.riesgo_69b = true` y registra fecha de publicación DOF
  más reciente. Limpia automáticamente cuando un RFC pasa a Desvirtuado.
- CLI: `--descargar-69b` y `--cruzar-69b`. Ejecución mensual recomendada.
- Compliance log automático en cada descarga y cruce.
- 5 tests nuevos. Total **131/131 pasan**.

**Resultado real (2026-05-01):**
- 14,189 registros descargados del SAT.
  - 11,270 Definitivos + 986 Presuntos = 12,256 en RIESGO
  - 1,638 Sentencia Favorable + 340 Desvirtuados = 1,978 LIMPIOS
- **0 establecimientos del CRM marcados** (cruce por razón social exacta + fuzzy).
- Razón: la 69-B son mayoritariamente empresas fachada de servicios
  (logística, consultoría, sistemas), mientras tu universo son negocios
  con operación física (tortillerías, forrajeras, asociaciones, plantas).
- Validación con rapidfuzz token_sort_ratio: 0 matches ≥95, 1 match 85-94
  (irrelevante).

**Recomendación operativa:** correr `--descargar-69b && --cruzar-69b` cada
inicio de mes. El sistema marcará automáticamente cualquier prospecto que
entre a riesgo o salga de él.

### Capa de enriquecimiento Google Places (Fase 4)

- `src/ingestion/places_api.py` — Cliente Places API (New). Text Search + Place Details
  con FieldMask. Throttling 100 ms (10 req/s). Circuit breaker que aborta si gasto
  mensual + esta call excede `MONTHLY_BUDGET_USD` ($100). Loguea cada call en
  `google_places_log` con SKU (Essentials $0.005 / Pro $0.018), bytes y costo.
- `src/enrichment/matching.py` — Matcher DENUE↔Google. Score 0-100 con peso
  80% fuzzy nombre (rapidfuzz token_sort) + 20% proximidad (≤200m=alto, >500m=bajo).
  Match si score ≥70 y distancia ≤200m. Persiste en `enriquecimiento_google` con
  rating, horarios, teléfono, sitio web, business_status. Si DENUE no tenía
  teléfono y Google sí, se llena (sin pisar valores manuales).
- `src/enrichment/cadenas.py` — Detector de cadenas por palabras-marca tras
  remover genéricas (tortilleria, molino, elaboracion, venta, sin, nombre, etc.).
  Filtra nombres descriptivos tipo "ELABORACION DE TORTILLAS SIN NOMBRE".
  Umbral por default: ≥3 sucursales con misma marca.
- `src/enrichment/places_pipeline.py` — Orquestador D3.B. Selecciona AlimentoBalanceado
  + Asociaciones + top N cadenas + top tortillerías por volumen. Cache automático
  (skip si ya hay match), circuit breaker, compliance_log. Commit cada 50.
- CLI: `--detectar-cadenas`, `--enriquecer [--max-total N]`, `--gasto`.

**Validaciones:**
- 15 tests nuevos (matching + cadenas) → **125 tests pasan**, ruff limpio.
- Detección real: **3,247 cadenas** detectadas en 124K establecimientos
  (top: La Lupita 900 sucursales 13 estados, Juquilita 367, La Guadalupana 339).
- Smoke real con 10 candidatos: 2 matches, 8 no_match, **$0.086 USD**, 3.4 s.
  Tasa de match baja porque AlimentoBalanceado son plantas B2B sin perfil
  consumer en Google Places (esperado).

**Resultado real de la corrida completa (2026-04-30, 16 entidades):**
- **2,022 matches** (29.7% rate) sobre 6,810 candidatos D3.B
- **$73.40 USD** gastados de $100 budget (3 corridas iteradas)
- 0 errores tras refactor a UPSERT atómico

Match rate por canal (mejor primero):
- ForrajerasPecuario: 44% (158 matches) — mejor visibilidad en Google
- Tortillerías cadenas: 29% (1,049 matches)
- AsociacionesAgropecuarias: 28% (696 matches)
- AlimentoBalanceado: 27% (119 matches) — B2B, menos visible

**Hallazgos durante la corrida:**
- 3 migraciones drop UNIQUE necesarias: cadenas.nombre_grupo,
  enriquecimiento_google.place_id, establecimientos.google_place_id.
  Razón: 2 establecimientos DENUE pueden mapear al mismo place_id Google.
- `_persistir_match`/`_persistir_no_match` migrados a UPSERT atómico
  (`pg_insert.on_conflict_do_update`) por robustez ante sesiones rotas.
- Detector de cadenas refactorizado a 3 estrategias en orden de confianza.
- Cache `_ya_enriquecido` ahora skipea match Y no_match para no re-pagar.

**Casos destacados verificados:**
- Tortillería La Oriental QRO: 10/22 sucursales matcheadas, ratings ★4.5-★4.7,
  2 teléfonos verificados (442 509 7363, 442 214 6199).
- BACHOCO: matcheado con datos de planta industrial Veracruz CEDIS ★4.6.
- AGRIBRANDS PURINA Planta Puebla: matcheado ★4.2.
- ALIMENTOS PLIEGO (ALPLI): 15/40 sucursales con rating y sitio web.

### Capa de ingesta DENUE lista (Fase 3)

**Estrategia primaria: ZIPs CSV oficiales** (descubierto durante implementación —
los endpoints API JSON `BuscarEntidad/SCIAN/...` están obsoletos). Cada entidad
es 1 request a `https://www.inegi.org.mx/contenidos/masiva/denue/denue_<cve>_csv.zip`,
~3-50 MB, decodificación LATIN1, filtrado por SCIAN objetivo, upsert idempotente.

- `src/core/heuristicas.py` — normaliza_nombre, hash_dedup, estrato→empleados,
  tipo_establecimiento_de_scian (heurísticas refinadas: "molino", "moderna",
  "union ganadera", "camara"), volumen_estimado_ton_mes, scian_desde_clee.
- `src/core/constantes.py` — taxonomías (8 SCIAN, 4 canales, 13 entidades, bbox MX).
- `src/ingestion/denue.py` — `descargar_zip_entidad`, `iter_csv_entidad` con
  filter SCIAN, throttling 60 req/min, retries con tenacity. También endpoints
  API JSON complementarios: `cuantificar`, `por_nombre`, `ficha`.
- `src/ingestion/denue_csv_parser.py` — fila CSV → dict de Establecimiento.
- `src/ingestion/denue_pipeline.py` — `descargar_entidad` orquesta filtro +
  upsert por lotes de 1,000 + `actualizar_geom` (PostGIS ST_MakePoint) +
  log en `denue_descargas_log` + compliance_log automático.
- `src/ingestion/cli.py` — `python -m src.ingestion.cli` con `--full`, `--smoke`,
  `--entidad`, `--scian`, `--cuantificar`, `--max-total`.
- Migración `04a9b1e3356b` — DROP UNIQUE de hash_dedup (mantiene índice).
  Razón: nombres genéricos sin coords colisionan; CLEE es la unicidad oficial.
- 16 tests nuevos (CSV parser, ZIP/CSV con MockTransport, pipeline upsert).

**Validación con data real:**
- Quintana Roo (smoke): 1,098 establecimientos en 7 s.
- **Descarga completa de las 13 entidades priorizadas: 124,432 establecimientos en ~4 min.**
- 100% con geom asignado por PostGIS.
- 35,480 (28.5%) con teléfono — el resto son target para enriquecimiento Fase 4.
- Idempotencia validada (re-corrida = 0 ins, N upd).
- **Audit run_all: aprobado, 0 errors.** 4 warnings esperados (hash colisiones 0.01%,
  sin contacto 71%, dirección sospechosa 14%, formato tel 1 caso).

### Universo final por entidad
| Entidad | Count |
|---|---:|
| México (15) | 33,899 |
| Puebla (21) | 18,174 |
| Oaxaca (20) | 16,971 |
| CDMX (09) | 14,563 |
| Veracruz (30) | 10,054 |
| Chiapas (07) | 6,694 |
| Hidalgo (13) | 6,507 |
| Tlaxcala (29) | 5,952 |
| Morelos (17) | 3,796 |
| Yucatán (31) | 2,959 |
| Tabasco (27) | 2,835 |
| Quintana Roo (23) | 1,098 |
| Campeche (04) | 930 |
| **TOTAL** | **124,432** |

### Universo final por canal
| Canal | Count |
|---|---:|
| Tortillerias | 111,410 (89.5%) |
| ForrajerasPecuario | 10,662 (8.6%) |
| AsociacionesAgropecuarias | 2,043 (1.6%) |
| AlimentoBalanceado | 317 (0.3%) |

**Caveat técnico:** EdoMex (15) viene en 2 ZIPs (`_1` + `_2`). El cliente
detecta esto via `ENTIDADES_ZIP_PARTIDO` y los itera transparentemente.

**110 tests totales pasan, ruff limpio.**

### Capa de auditoría lista (Fase 2)

- `src/core/constantes.py` — taxonomías inmutables (8 SCIAN objetivo, 4 canales, 13 entidades priorizadas, bbox MX, estados pipeline).
- `src/audit/models.py` — `Hallazgo` y `ReporteAuditoria` (Pydantic frozen).
- `src/audit/duplicates.py` — CLEE, hash_dedup, fuzzy nombre+dirección con rapidfuzz.
- `src/audit/completeness.py` — columnas críticas, % NULL por columna, sin contacto.
- `src/audit/geo_anomalies.py` — coords nulas/cero, fuera bbox MX, lat/lon invertidas, geom desync.
- `src/audit/scian.py` — SCIAN objetivo, canal coherente con SCIAN, canales no vacío, distribución info.
- `src/audit/contacto.py` — teléfono MX (con normalización +52), email, direcciones sospechosas, anio_alta razonable.
- `src/audit/runner.py` — `run_all()` orquesta 18 chequeos, `run_subset()` y `omitir`.
- `docs/auditoria/criterios_calidad.md` — política severidad: error / warning / info.
- `notebooks/02_auditoria_denue.ipynb` — visualización gradient_red sobre la tabla.
- **39 tests nuevos** (test_audit_*.py) — total **50 tests** pasan, ruff limpio.

### Google Cloud setup (2026-04-30)

- **Proyecto:** "My First Project" (`project-44fbe072-34f4-41e9-880`).
- **Trial:** $5,411 MXN (~$300 USD) por 90 días, vence 2026-07-30.
- **Places API (New):** habilitada.
- **API key:** "Maps Platform API Key" creada y restringida a **Places API (New)** únicamente. Sin restricción de IP por ahora (en Fase 4 agregamos IP de Render). Key persiste en `.env` (gitignored).
- **Budget alert:** "CRM-Granos-MX mensual" — $100 USD/mes, alertas al 50% / 90% / 100%, email a admin.
- **Tests funcionales:** 2 requests reales OK — Tortillerías CDMX (3 resultados), Forrajeras Toluca (2 resultados). Costo total ~$0.01 USD del free tier 10K Essentials.

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
