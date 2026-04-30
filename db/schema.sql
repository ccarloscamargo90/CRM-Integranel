-- =====================================================================
-- CRM-Granos-MX — Schema baseline (referencia humana del DDL)
-- =====================================================================
-- Este archivo es REFERENCIA: muestra el estado del schema en lenguaje SQL
-- legible para humanos. La fuente de verdad operacional son las migraciones
-- Alembic en migrations/versions/.
--
-- NUNCA aplicar este archivo directamente a una DB de producción.
-- Para aplicar, usar `alembic upgrade head`.
--
-- Cualquier cambio futuro de schema:
--   1) genera migración con `alembic revision -m "descripcion"`
--   2) edita upgrade()/downgrade() en el archivo generado
--   3) aplica con `alembic upgrade head`
--   4) actualiza este archivo para que siga reflejando el estado real
-- =====================================================================

-- ---------------------------------------------------------------------
-- Extensiones
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- índice para búsqueda fuzzy nombre


-- ---------------------------------------------------------------------
-- Catálogo PII — defensa LFPDPPP
-- ---------------------------------------------------------------------
-- Cada columna que pueda contener datos personales SE REGISTRA aquí.
-- Si una columna no aparece, no se puede usar PII en ella.
-- Esta tabla se llena en la migración baseline con las columnas conocidas.
CREATE TABLE _columnas_pii (
    id                  SERIAL PRIMARY KEY,
    tabla               TEXT NOT NULL,
    columna             TEXT NOT NULL,
    base_legal          TEXT NOT NULL,
    finalidad           TEXT NOT NULL,
    retencion_meses     INTEGER NOT NULL,
    notas               TEXT,
    fecha_alta          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tabla, columna)
);


-- ---------------------------------------------------------------------
-- Vendedores
-- ---------------------------------------------------------------------
CREATE TABLE vendedores (
    id                  BIGSERIAL PRIMARY KEY,
    codigo              TEXT UNIQUE NOT NULL,
    nombre              TEXT NOT NULL,                    -- PII (PF empleado)
    email               TEXT,                              -- PII
    telefono            TEXT,                              -- PII
    zona_asignada       TEXT,
    municipios_ids      JSONB,                             -- ["015014","015106",...] (cve INEGI)
    canales_asignados   TEXT[] DEFAULT ARRAY[]::TEXT[],    -- subset de los 4 canales
    activo              BOOLEAN NOT NULL DEFAULT true,
    fecha_alta          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_vendedores_codigo ON vendedores(codigo);
CREATE INDEX idx_vendedores_municipios ON vendedores USING gin(municipios_ids);


-- ---------------------------------------------------------------------
-- Usuarios (auth)
-- ---------------------------------------------------------------------
-- Roles:
--   admin     = control total (CRUD vendedores, asignación, usuarios, exportes con PII)
--   vendedor  = solo ve y edita SUS prospectos asignados
--   jefe      = solo lectura, ve todo el pipeline sin modificar
CREATE TABLE usuarios (
    id                  BIGSERIAL PRIMARY KEY,
    username            TEXT UNIQUE NOT NULL,
    password_hash       TEXT NOT NULL,
    nombre              TEXT NOT NULL,                    -- PII
    email               TEXT,                              -- PII
    rol                 TEXT NOT NULL CHECK (rol IN ('admin','vendedor','jefe')),
    vendedor_id         BIGINT REFERENCES vendedores(id) ON DELETE SET NULL,
    activo              BOOLEAN NOT NULL DEFAULT true,
    ultimo_login        TIMESTAMPTZ,
    fecha_alta          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_usuarios_vendedor ON usuarios(vendedor_id);


-- ---------------------------------------------------------------------
-- Cadenas / grupos comerciales (sucursales de la misma marca)
-- ---------------------------------------------------------------------
CREATE TABLE cadenas (
    id                       BIGSERIAL PRIMARY KEY,
    nombre_grupo             TEXT UNIQUE NOT NULL,
    nombre_grupo_norm        TEXT UNIQUE NOT NULL,         -- minúsculas + sin acentos
    canal_principal          TEXT,                          -- canal donde tiene más sucursales
    sucursales_count         INTEGER NOT NULL DEFAULT 0,
    municipios               JSONB,
    tipo                     TEXT,                          -- cadena_local | regional | nacional | franquicia
    contacto_central_nombre  TEXT,                          -- PII
    contacto_central_tel     TEXT,                          -- PII
    contacto_central_email   TEXT,                          -- PII
    volumen_estimado_ton_mes REAL,
    prioridad_estrategica    SMALLINT,                      -- 1=alta .. 5=baja
    notas                    TEXT,
    fecha_alta               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------
-- Establecimientos — tabla central
-- ---------------------------------------------------------------------
CREATE TABLE establecimientos (
    id                          BIGSERIAL PRIMARY KEY,

    -- Identidad
    clee                        TEXT UNIQUE,                          -- DENUE
    google_place_id             TEXT UNIQUE,
    hash_dedup                  TEXT UNIQUE NOT NULL,                 -- sha1(nombre_norm+cp+lat_round+lon_round)
    nombre                      TEXT NOT NULL,                        -- PII (puede contener nombre de PF)
    nombre_norm                 TEXT NOT NULL,
    razon_social                TEXT,                                  -- PII
    rfc                         TEXT,                                  -- PII

    -- Clasificación SCIAN + canales
    scian_codigo                TEXT NOT NULL,
    scian_descripcion           TEXT,
    canales                     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
        -- valores válidos: 'Tortillerias', 'AlimentoBalanceado', 'ForrajerasPecuario', 'AsociacionesAgropecuarias'
        -- un establecimiento puede pertenecer a varios canales si la operación lo justifica
    tipo_establecimiento        TEXT,
        -- subtipos válidos por canal — ver CLAUDE.md §5
    relacion_comercial          TEXT CHECK (relacion_comercial IN ('compra','vende','ambos')),

    -- Cadena
    cadena_id                   BIGINT REFERENCES cadenas(id),
    grupo_marca                 TEXT,                                 -- denormalizado para query rápido

    -- Ubicación
    direccion                   TEXT,
    tipo_vialidad               TEXT,
    nombre_vialidad             TEXT,
    numero_exterior             TEXT,
    numero_interior             TEXT,
    colonia                     TEXT,
    cp                          TEXT,
    municipio                   TEXT,
    municipio_codigo            TEXT,                                 -- 3 dígitos INEGI dentro de la entidad
    localidad                   TEXT,
    estado                      TEXT,
    estado_codigo               TEXT,                                 -- 2 dígitos INEGI
    ageb                        TEXT,
    manzana                     TEXT,
    latitud                     DOUBLE PRECISION,
    longitud                    DOUBLE PRECISION,
    geom                        geometry(Point, 4326),

    -- Contacto (toda esta sección es PII)
    telefono                    TEXT,                                 -- PII
    whatsapp                    TEXT,                                 -- PII
    email                       TEXT,                                 -- PII
    sitio_web                   TEXT,
    facebook                    TEXT,
    contacto_nombre             TEXT,                                 -- PII
    contacto_puesto             TEXT,
    contacto_telefono           TEXT,                                 -- PII
    contacto_email              TEXT,                                 -- PII

    -- Tamaño / potencial
    estrato_personal_denue      TEXT,                                 -- "0 a 5 personas", etc.
    empleados_est               INTEGER,                              -- punto medio del rango
    volumen_estimado_ton_mes    REAL,                                 -- derivado de tipo + estrato
    anio_alta_denue             INTEGER,
    tipo_unidad                 TEXT,                                 -- "Fijo" | "Semifijo"

    -- Riesgo fiscal
    riesgo_69b                  BOOLEAN NOT NULL DEFAULT false,
    riesgo_69b_fecha            DATE,

    -- Pipeline comercial
    segmento_abc                TEXT CHECK (segmento_abc IN ('A','B','C','X')),
    score_prioridad             REAL,
    vendedor_id                 BIGINT REFERENCES vendedores(id) ON DELETE SET NULL,
    zona_ruta                   TEXT,
    estado_pipeline             TEXT NOT NULL DEFAULT 'no_contactado'
        CHECK (estado_pipeline IN
            ('no_contactado','prospecto','contactado','visitado',
             'cotizado','ganado','perdido','descartado','pausado')),
    ultimo_contacto             DATE,
    proximo_seguimiento         DATE,
    notas                       TEXT,

    -- Trazabilidad y metadata
    fuentes                     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
        -- ['DENUE_API', 'Google_Places', 'Manual', 'CONAFAB', ...]
    fecha_alta                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_est_municipio          ON establecimientos(municipio);
CREATE INDEX idx_est_municipio_codigo   ON establecimientos(municipio_codigo);
CREATE INDEX idx_est_estado_codigo      ON establecimientos(estado_codigo);
CREATE INDEX idx_est_cadena             ON establecimientos(cadena_id);
CREATE INDEX idx_est_segmento           ON establecimientos(segmento_abc);
CREATE INDEX idx_est_vendedor           ON establecimientos(vendedor_id);
CREATE INDEX idx_est_pipeline           ON establecimientos(estado_pipeline);
CREATE INDEX idx_est_scian              ON establecimientos(scian_codigo);
CREATE INDEX idx_est_canales            ON establecimientos USING gin(canales);
CREATE INDEX idx_est_fuentes            ON establecimientos USING gin(fuentes);
CREATE INDEX idx_est_geom               ON establecimientos USING gist(geom);
CREATE INDEX idx_est_nombre_trgm        ON establecimientos USING gin(nombre_norm gin_trgm_ops);
CREATE INDEX idx_est_riesgo_69b         ON establecimientos(riesgo_69b) WHERE riesgo_69b = true;


-- ---------------------------------------------------------------------
-- Enriquecimiento Google Places
-- ---------------------------------------------------------------------
CREATE TABLE enriquecimiento_google (
    establecimiento_id          BIGINT PRIMARY KEY REFERENCES establecimientos(id) ON DELETE CASCADE,
    place_id                    TEXT UNIQUE NOT NULL,
    match_score                 REAL,                                 -- 0-100 fuzzy + distancia
    match_status                TEXT NOT NULL CHECK (match_status IN ('match','no_match','duda','manual')),
    google_display_name         TEXT,
    google_formatted_address    TEXT,
    google_types                TEXT[],
    google_business_status      TEXT,                                 -- OPERATIONAL | CLOSED_TEMPORARILY | CLOSED_PERMANENTLY
    google_rating               REAL,
    google_user_rating_count    INTEGER,
    google_opening_hours        JSONB,
    google_price_level          TEXT,                                 -- PRICE_LEVEL_FREE..PRICE_LEVEL_VERY_EXPENSIVE
    google_phone                TEXT,                                  -- PII
    google_website              TEXT,
    google_lat                  DOUBLE PRECISION,
    google_lon                  DOUBLE PRECISION,
    fecha_enriquecimiento       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    costo_estimado_usd          NUMERIC(8,4) NOT NULL DEFAULT 0
);
CREATE INDEX idx_enriq_status ON enriquecimiento_google(match_status);


-- ---------------------------------------------------------------------
-- Interacciones — bitácora comercial
-- ---------------------------------------------------------------------
CREATE TABLE interacciones (
    id                          BIGSERIAL PRIMARY KEY,
    establecimiento_id          BIGINT NOT NULL REFERENCES establecimientos(id) ON DELETE CASCADE,
    vendedor_id                 BIGINT REFERENCES vendedores(id),
    usuario_id                  BIGINT REFERENCES usuarios(id),
    fecha                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tipo                        TEXT NOT NULL CHECK (tipo IN
        ('visita','llamada','email','whatsapp','cotizacion','pedido','muestra','seguimiento')),
    canal_contacto              TEXT,                                  -- 'email','tel','whatsapp','presencial'
    resultado                   TEXT,
    volumen_cotizado_ton        REAL,
    precio_cotizado_mxn_ton     REAL,
    siguiente_paso              TEXT,
    siguiente_paso_fecha        DATE,
    contacto_persona            TEXT,                                  -- PII (con quién hablaste)
    duracion_min                SMALLINT,
    temperatura_despues         TEXT,                                  -- 'frio'|'tibio'|'caliente'
    notas                       TEXT
);
CREATE INDEX idx_int_est        ON interacciones(establecimiento_id);
CREATE INDEX idx_int_fecha      ON interacciones(fecha DESC);
CREATE INDEX idx_int_vendedor   ON interacciones(vendedor_id);


-- ---------------------------------------------------------------------
-- Cambios de etapa del pipeline (histórico — la auditoría del legacy
-- detectó que NO existía y era un punto ciego operacional)
-- ---------------------------------------------------------------------
CREATE TABLE pipeline_etapas_historial (
    id                          BIGSERIAL PRIMARY KEY,
    establecimiento_id          BIGINT NOT NULL REFERENCES establecimientos(id) ON DELETE CASCADE,
    usuario_id                  BIGINT REFERENCES usuarios(id),
    etapa_anterior              TEXT NOT NULL,
    etapa_nueva                 TEXT NOT NULL,
    motivo                      TEXT,
    fecha                       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_hist_est_fecha ON pipeline_etapas_historial(establecimiento_id, fecha DESC);


-- ---------------------------------------------------------------------
-- Logs de fuentes externas
-- ---------------------------------------------------------------------
CREATE TABLE denue_descargas_log (
    id                          BIGSERIAL PRIMARY KEY,
    fuente                      TEXT NOT NULL,                        -- 'denue_cuantificar','denue_ficha','denue_buscar_entidad','denue_nombre'
    endpoint_url                TEXT,
    parametros                  JSONB,
    status_http                 INTEGER,
    bytes_recibidos             INTEGER,
    filas_recibidas             INTEGER,
    filas_insertadas            INTEGER,
    filas_actualizadas          INTEGER,
    filas_descartadas           INTEGER,
    duracion_ms                 INTEGER,
    notas                       TEXT,
    fecha                       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_denue_log_fecha ON denue_descargas_log(fecha DESC);


CREATE TABLE google_places_log (
    id                          BIGSERIAL PRIMARY KEY,
    establecimiento_id          BIGINT REFERENCES establecimientos(id) ON DELETE SET NULL,
    metodo                      TEXT NOT NULL,                        -- 'text_search','place_details','autocomplete'
    sku                         TEXT,                                  -- 'Essentials','Pro','Enterprise'
    field_mask                  TEXT,
    status_http                 INTEGER,
    bytes_recibidos             INTEGER,
    place_id_devuelto           TEXT,
    costo_estimado_usd          NUMERIC(8,4) NOT NULL DEFAULT 0,
    cache_hit                   BOOLEAN NOT NULL DEFAULT false,
    fecha                       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_gplaces_log_fecha ON google_places_log(fecha DESC);


-- ---------------------------------------------------------------------
-- SAT Listado 69-B (cruce mensual obligatorio)
-- ---------------------------------------------------------------------
CREATE TABLE sat_lista_69b (
    id                          BIGSERIAL PRIMARY KEY,
    rfc                         TEXT NOT NULL,                         -- PII
    razon_social                TEXT,                                  -- PII
    estatus                     TEXT,                                  -- 'definitivo','presunto','desvirtuado','sentencia'
    fecha_publicacion_dof       DATE,
    fecha_descarga              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(rfc, fecha_publicacion_dof)
);
CREATE INDEX idx_sat69b_rfc ON sat_lista_69b(rfc);


-- ---------------------------------------------------------------------
-- AGEBs (Marco Geoestadístico) y indicadores derivados
-- ---------------------------------------------------------------------
CREATE TABLE agebs (
    id                          BIGSERIAL PRIMARY KEY,
    cve_ageb                    TEXT UNIQUE NOT NULL,                 -- 13 chars: estado(2)+mun(3)+loc(4)+ageb(4)
    cve_entidad                 TEXT NOT NULL,
    cve_municipio               TEXT NOT NULL,
    nombre_municipio            TEXT,
    geom                        geometry(MultiPolygon, 4326) NOT NULL,
    poblacion_total             INTEGER,
    nse_estimado                TEXT,                                  -- 'A','B+','B','C+','C','C-','D+','D','E'
    fecha_carga                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agebs_geom ON agebs USING gist(geom);
CREATE INDEX idx_agebs_entidad ON agebs(cve_entidad);


CREATE TABLE indicadores_geograficos (
    id                          BIGSERIAL PRIMARY KEY,
    nivel                       TEXT NOT NULL CHECK (nivel IN ('entidad','municipio','ageb')),
    cve                         TEXT NOT NULL,
    indicador                   TEXT NOT NULL,                         -- 'consumo_tortilla_kg_per_capita_anio', 'produccion_maiz_grano_ton', etc.
    valor                       NUMERIC,
    unidad                      TEXT,
    fuente                      TEXT NOT NULL,                         -- 'INEGI_ENIGH','SIAP','CONAGUA',...
    anio                        SMALLINT,
    fecha_carga                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(nivel, cve, indicador, anio)
);
CREATE INDEX idx_indic_cve ON indicadores_geograficos(cve);


-- ---------------------------------------------------------------------
-- compliance_log — toda operación que toca PII
-- ---------------------------------------------------------------------
CREATE TABLE compliance_log (
    id                          BIGSERIAL PRIMARY KEY,
    fecha                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    usuario_id                  BIGINT REFERENCES usuarios(id),
    tipo_operacion              TEXT NOT NULL,
        -- 'descarga_denue','enriquecimiento_google','exportacion_csv','contacto_comercial',
        -- 'arco_acceso','arco_rectificacion','arco_cancelacion','arco_oposicion'
    establecimiento_id          BIGINT REFERENCES establecimientos(id) ON DELETE SET NULL,
    columnas_pii_tocadas        TEXT[],                                -- subset de _columnas_pii
    finalidad                   TEXT NOT NULL,
    base_legal                  TEXT NOT NULL,
    arco_solicitud_id           TEXT,                                  -- ID externo de la solicitud ARCO si aplica
    arco_plazo_dias_habiles     SMALLINT,                              -- 20 default
    notas                       TEXT
);
CREATE INDEX idx_compliance_fecha ON compliance_log(fecha DESC);
CREATE INDEX idx_compliance_usuario ON compliance_log(usuario_id);
CREATE INDEX idx_compliance_arco ON compliance_log(arco_solicitud_id) WHERE arco_solicitud_id IS NOT NULL;


-- =====================================================================
-- VISTAS
-- =====================================================================

CREATE VIEW vw_establecimientos_resumen AS
SELECT
    e.id,
    e.clee,
    e.nombre,
    e.scian_codigo,
    e.canales,
    e.tipo_establecimiento,
    e.relacion_comercial,
    e.estado,
    e.estado_codigo,
    e.municipio,
    e.municipio_codigo,
    e.colonia,
    e.cp,
    e.estrato_personal_denue,
    e.empleados_est,
    e.volumen_estimado_ton_mes,
    e.segmento_abc,
    e.score_prioridad,
    e.estado_pipeline,
    v.nombre AS vendedor,
    e.zona_ruta,
    e.telefono,
    e.email,
    e.sitio_web,
    e.riesgo_69b,
    eg.google_rating,
    eg.google_user_rating_count,
    e.ultimo_contacto,
    e.proximo_seguimiento,
    e.latitud,
    e.longitud,
    c.nombre_grupo AS cadena
FROM establecimientos e
LEFT JOIN vendedores v          ON e.vendedor_id = v.id
LEFT JOIN cadenas c             ON e.cadena_id   = c.id
LEFT JOIN enriquecimiento_google eg ON eg.establecimiento_id = e.id;


CREATE VIEW vw_pipeline_vendedor AS
SELECT
    v.id                                          AS vendedor_id,
    v.nombre                                      AS vendedor,
    v.zona_asignada,
    COUNT(e.id)                                   AS cartera_total,
    SUM(CASE WHEN e.segmento_abc='A' THEN 1 ELSE 0 END) AS cuentas_a,
    SUM(CASE WHEN e.segmento_abc='B' THEN 1 ELSE 0 END) AS cuentas_b,
    SUM(CASE WHEN e.segmento_abc='C' THEN 1 ELSE 0 END) AS cuentas_c,
    SUM(CASE WHEN e.estado_pipeline='no_contactado' THEN 1 ELSE 0 END) AS no_contactados,
    SUM(CASE WHEN e.estado_pipeline='visitado'      THEN 1 ELSE 0 END) AS visitados,
    SUM(CASE WHEN e.estado_pipeline='cotizado'      THEN 1 ELSE 0 END) AS cotizados,
    SUM(CASE WHEN e.estado_pipeline='ganado'        THEN 1 ELSE 0 END) AS ganados,
    SUM(e.volumen_estimado_ton_mes)               AS potencial_ton_mes
FROM vendedores v
LEFT JOIN establecimientos e ON e.vendedor_id = v.id
WHERE v.activo = true
GROUP BY v.id;


CREATE VIEW vw_cobertura_municipio AS
SELECT
    estado_codigo,
    estado,
    municipio_codigo,
    municipio,
    canal,
    COUNT(*)                                       AS total,
    SUM(CASE WHEN segmento_abc='A' THEN 1 ELSE 0 END) AS seg_a,
    SUM(CASE WHEN segmento_abc='B' THEN 1 ELSE 0 END) AS seg_b,
    SUM(CASE WHEN segmento_abc='C' THEN 1 ELSE 0 END) AS seg_c,
    SUM(CASE WHEN estado_pipeline='no_contactado' THEN 1 ELSE 0 END) AS pendientes,
    SUM(empleados_est)                             AS empleados_total_est,
    SUM(volumen_estimado_ton_mes)                  AS volumen_total_ton_mes_est
FROM establecimientos, unnest(canales) AS canal
WHERE municipio_codigo IS NOT NULL
GROUP BY estado_codigo, estado, municipio_codigo, municipio, canal;


CREATE VIEW vw_canales_resumen AS
SELECT
    canal,
    COUNT(*)                                       AS total,
    COUNT(*) FILTER (WHERE segmento_abc = 'A')     AS seg_a,
    COUNT(*) FILTER (WHERE segmento_abc = 'B')     AS seg_b,
    COUNT(*) FILTER (WHERE segmento_abc = 'C')     AS seg_c,
    COUNT(*) FILTER (WHERE estado_pipeline='ganado') AS ganados,
    COUNT(*) FILTER (WHERE telefono IS NOT NULL)   AS con_telefono,
    SUM(volumen_estimado_ton_mes)                  AS volumen_total_ton_mes_est
FROM establecimientos, unnest(canales) AS canal
GROUP BY canal;
