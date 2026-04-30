"""Modelos ORM declarativos SQLAlchemy 2.0 (estilo `Mapped[...]`).

Estos modelos REPLEJAN el schema ya aplicado en Postgres (ver `db/schema.sql` y
`migrations/versions/...baseline.py`). Cualquier cambio de schema futuro pasa
por una migración Alembic; estos modelos se actualizan después.

NO se usa `Base.metadata.create_all()` — ese path está reservado para tests.
En producción y desarrollo, el schema lo aplica Alembic.

Convenciones:
- `Mapped[...]` declara el tipo Python (puede ser nullable con `Optional`).
- `mapped_column(...)` declara opciones de columna SQL.
- Foreign keys con `ForeignKey("tabla.id")`.
- Timestamps con `server_default=text("NOW()")` para que Postgres los rellene.
"""

from __future__ import annotations

import datetime as dt

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# =============================================================================
# Catálogo PII — defensa LFPDPPP
# =============================================================================
class ColumnaPII(Base):
    __tablename__ = "_columnas_pii"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tabla: Mapped[str] = mapped_column(Text, nullable=False)
    columna: Mapped[str] = mapped_column(Text, nullable=False)
    base_legal: Mapped[str] = mapped_column(Text, nullable=False)
    finalidad: Mapped[str] = mapped_column(Text, nullable=False)
    retencion_meses: Mapped[int] = mapped_column(Integer, nullable=False)
    notas: Mapped[str | None] = mapped_column(Text)
    fecha_alta: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (UniqueConstraint("tabla", "columna", name="_columnas_pii_tabla_columna_key"),)


# =============================================================================
# Vendedores y usuarios (auth)
# =============================================================================
class Vendedor(Base):
    __tablename__ = "vendedores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)  # PII
    email: Mapped[str | None] = mapped_column(Text)  # PII
    telefono: Mapped[str | None] = mapped_column(Text)  # PII
    zona_asignada: Mapped[str | None] = mapped_column(Text)
    municipios_ids: Mapped[dict | None] = mapped_column(JSONB)
    canales_asignados: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::TEXT[]")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_alta: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    establecimientos: Mapped[list[Establecimiento]] = relationship(back_populates="vendedor")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)  # PII
    email: Mapped[str | None] = mapped_column(Text)  # PII
    rol: Mapped[str] = mapped_column(Text, nullable=False)
    vendedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vendedores.id", ondelete="SET NULL")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    ultimo_login: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    fecha_alta: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    fecha_actualizacion: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (CheckConstraint("rol IN ('admin','vendedor','jefe')", name="usuarios_rol_check"),)

    vendedor: Mapped[Vendedor | None] = relationship()


# =============================================================================
# Cadenas y establecimientos (núcleo del CRM)
# =============================================================================
class Cadena(Base):
    __tablename__ = "cadenas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre_grupo: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    nombre_grupo_norm: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    canal_principal: Mapped[str | None] = mapped_column(Text)
    sucursales_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    municipios: Mapped[dict | None] = mapped_column(JSONB)
    tipo: Mapped[str | None] = mapped_column(Text)
    contacto_central_nombre: Mapped[str | None] = mapped_column(Text)  # PII
    contacto_central_tel: Mapped[str | None] = mapped_column(Text)  # PII
    contacto_central_email: Mapped[str | None] = mapped_column(Text)  # PII
    volumen_estimado_ton_mes: Mapped[float | None] = mapped_column()
    prioridad_estrategica: Mapped[int | None] = mapped_column(SmallInteger)
    notas: Mapped[str | None] = mapped_column(Text)
    fecha_alta: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    fecha_actualizacion: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )


class Establecimiento(Base):
    __tablename__ = "establecimientos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Identidad
    clee: Mapped[str | None] = mapped_column(Text, unique=True)
    google_place_id: Mapped[str | None] = mapped_column(Text, unique=True)
    hash_dedup: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)  # PII
    nombre_norm: Mapped[str] = mapped_column(Text, nullable=False)
    razon_social: Mapped[str | None] = mapped_column(Text)  # PII
    rfc: Mapped[str | None] = mapped_column(Text)  # PII

    # Clasificación SCIAN + canales
    scian_codigo: Mapped[str] = mapped_column(Text, nullable=False)
    scian_descripcion: Mapped[str | None] = mapped_column(Text)
    canales: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::TEXT[]")
    )
    tipo_establecimiento: Mapped[str | None] = mapped_column(Text)
    relacion_comercial: Mapped[str | None] = mapped_column(Text)

    # Cadena
    cadena_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cadenas.id"))
    grupo_marca: Mapped[str | None] = mapped_column(Text)

    # Ubicación
    direccion: Mapped[str | None] = mapped_column(Text)
    tipo_vialidad: Mapped[str | None] = mapped_column(Text)
    nombre_vialidad: Mapped[str | None] = mapped_column(Text)
    numero_exterior: Mapped[str | None] = mapped_column(Text)
    numero_interior: Mapped[str | None] = mapped_column(Text)
    colonia: Mapped[str | None] = mapped_column(Text)
    cp: Mapped[str | None] = mapped_column(Text)
    municipio: Mapped[str | None] = mapped_column(Text)
    municipio_codigo: Mapped[str | None] = mapped_column(Text)
    localidad: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str | None] = mapped_column(Text)
    estado_codigo: Mapped[str | None] = mapped_column(Text)
    ageb: Mapped[str | None] = mapped_column(Text)
    manzana: Mapped[str | None] = mapped_column(Text)
    latitud: Mapped[float | None] = mapped_column()
    longitud: Mapped[float | None] = mapped_column()
    geom: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326))

    # Contacto (PII)
    telefono: Mapped[str | None] = mapped_column(Text)
    whatsapp: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    sitio_web: Mapped[str | None] = mapped_column(Text)
    facebook: Mapped[str | None] = mapped_column(Text)
    contacto_nombre: Mapped[str | None] = mapped_column(Text)
    contacto_puesto: Mapped[str | None] = mapped_column(Text)
    contacto_telefono: Mapped[str | None] = mapped_column(Text)
    contacto_email: Mapped[str | None] = mapped_column(Text)

    # Tamaño / potencial
    estrato_personal_denue: Mapped[str | None] = mapped_column(Text)
    empleados_est: Mapped[int | None] = mapped_column(Integer)
    volumen_estimado_ton_mes: Mapped[float | None] = mapped_column()
    anio_alta_denue: Mapped[int | None] = mapped_column(Integer)
    tipo_unidad: Mapped[str | None] = mapped_column(Text)

    # Riesgo
    riesgo_69b: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    riesgo_69b_fecha: Mapped[dt.date | None] = mapped_column(Date)

    # Pipeline
    segmento_abc: Mapped[str | None] = mapped_column(Text)
    score_prioridad: Mapped[float | None] = mapped_column()
    vendedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vendedores.id", ondelete="SET NULL")
    )
    zona_ruta: Mapped[str | None] = mapped_column(Text)
    estado_pipeline: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'no_contactado'")
    )
    ultimo_contacto: Mapped[dt.date | None] = mapped_column(Date)
    proximo_seguimiento: Mapped[dt.date | None] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Text)

    # Trazabilidad
    fuentes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::TEXT[]")
    )
    fecha_alta: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    fecha_actualizacion: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    # Relaciones
    vendedor: Mapped[Vendedor | None] = relationship(back_populates="establecimientos")
    cadena: Mapped[Cadena | None] = relationship()
    enriquecimiento: Mapped[EnriquecimientoGoogle | None] = relationship(
        back_populates="establecimiento", uselist=False
    )
    interacciones: Mapped[list[Interaccion]] = relationship(back_populates="establecimiento")

    __table_args__ = (
        CheckConstraint(
            "segmento_abc IN ('A','B','C','X')", name="establecimientos_segmento_abc_check"
        ),
        CheckConstraint(
            "estado_pipeline IN ('no_contactado','prospecto','contactado','visitado',"
            "'cotizado','ganado','perdido','descartado','pausado')",
            name="establecimientos_estado_pipeline_check",
        ),
        CheckConstraint(
            "relacion_comercial IN ('compra','vende','ambos')",
            name="establecimientos_relacion_comercial_check",
        ),
    )


class EnriquecimientoGoogle(Base):
    __tablename__ = "enriquecimiento_google"

    establecimiento_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    place_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    match_score: Mapped[float | None] = mapped_column()
    match_status: Mapped[str] = mapped_column(Text, nullable=False)
    google_display_name: Mapped[str | None] = mapped_column(Text)
    google_formatted_address: Mapped[str | None] = mapped_column(Text)
    google_types: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    google_business_status: Mapped[str | None] = mapped_column(Text)
    google_rating: Mapped[float | None] = mapped_column()
    google_user_rating_count: Mapped[int | None] = mapped_column(Integer)
    google_opening_hours: Mapped[dict | None] = mapped_column(JSONB)
    google_price_level: Mapped[str | None] = mapped_column(Text)
    google_phone: Mapped[str | None] = mapped_column(Text)  # PII
    google_website: Mapped[str | None] = mapped_column(Text)
    google_lat: Mapped[float | None] = mapped_column()
    google_lon: Mapped[float | None] = mapped_column()
    fecha_enriquecimiento: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    costo_estimado_usd: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=False, server_default=text("0")
    )

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="enriquecimiento")

    __table_args__ = (
        CheckConstraint(
            "match_status IN ('match','no_match','duda','manual')",
            name="enriquecimiento_google_match_status_check",
        ),
    )


# =============================================================================
# Interacciones e histórico de etapas
# =============================================================================
class Interaccion(Base):
    __tablename__ = "interacciones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    establecimiento_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("establecimientos.id", ondelete="CASCADE"), nullable=False
    )
    vendedor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("vendedores.id"))
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuarios.id"))
    fecha: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    canal_contacto: Mapped[str | None] = mapped_column(Text)
    resultado: Mapped[str | None] = mapped_column(Text)
    volumen_cotizado_ton: Mapped[float | None] = mapped_column()
    precio_cotizado_mxn_ton: Mapped[float | None] = mapped_column()
    siguiente_paso: Mapped[str | None] = mapped_column(Text)
    siguiente_paso_fecha: Mapped[dt.date | None] = mapped_column(Date)
    contacto_persona: Mapped[str | None] = mapped_column(Text)  # PII
    duracion_min: Mapped[int | None] = mapped_column(SmallInteger)
    temperatura_despues: Mapped[str | None] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="interacciones")

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('visita','llamada','email','whatsapp','cotizacion','pedido','muestra','seguimiento')",
            name="interacciones_tipo_check",
        ),
    )


class PipelineEtapaHistorial(Base):
    __tablename__ = "pipeline_etapas_historial"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    establecimiento_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("establecimientos.id", ondelete="CASCADE"), nullable=False
    )
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuarios.id"))
    etapa_anterior: Mapped[str] = mapped_column(Text, nullable=False)
    etapa_nueva: Mapped[str] = mapped_column(Text, nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )


# =============================================================================
# Logs de fuentes externas
# =============================================================================
class DenueDescargaLog(Base):
    __tablename__ = "denue_descargas_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fuente: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(Text)
    parametros: Mapped[dict | None] = mapped_column(JSONB)
    status_http: Mapped[int | None] = mapped_column(Integer)
    bytes_recibidos: Mapped[int | None] = mapped_column(Integer)
    filas_recibidas: Mapped[int | None] = mapped_column(Integer)
    filas_insertadas: Mapped[int | None] = mapped_column(Integer)
    filas_actualizadas: Mapped[int | None] = mapped_column(Integer)
    filas_descartadas: Mapped[int | None] = mapped_column(Integer)
    duracion_ms: Mapped[int | None] = mapped_column(Integer)
    notas: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )


class GooglePlacesLog(Base):
    __tablename__ = "google_places_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    establecimiento_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("establecimientos.id", ondelete="SET NULL")
    )
    metodo: Mapped[str] = mapped_column(Text, nullable=False)
    sku: Mapped[str | None] = mapped_column(Text)
    field_mask: Mapped[str | None] = mapped_column(Text)
    status_http: Mapped[int | None] = mapped_column(Integer)
    bytes_recibidos: Mapped[int | None] = mapped_column(Integer)
    place_id_devuelto: Mapped[str | None] = mapped_column(Text)
    costo_estimado_usd: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=False, server_default=text("0")
    )
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fecha: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )


# =============================================================================
# SAT, AGEBs, indicadores
# =============================================================================
class SatLista69B(Base):
    __tablename__ = "sat_lista_69b"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rfc: Mapped[str] = mapped_column(Text, nullable=False)  # PII
    razon_social: Mapped[str | None] = mapped_column(Text)  # PII
    estatus: Mapped[str | None] = mapped_column(Text)
    fecha_publicacion_dof: Mapped[dt.date | None] = mapped_column(Date)
    fecha_descarga: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("rfc", "fecha_publicacion_dof", name="sat_lista_69b_rfc_fecha_key"),
    )


class Ageb(Base):
    __tablename__ = "agebs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cve_ageb: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    cve_entidad: Mapped[str] = mapped_column(Text, nullable=False)
    cve_municipio: Mapped[str] = mapped_column(Text, nullable=False)
    nombre_municipio: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False
    )
    poblacion_total: Mapped[int | None] = mapped_column(Integer)
    nse_estimado: Mapped[str | None] = mapped_column(Text)
    fecha_carga: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )


class IndicadorGeografico(Base):
    __tablename__ = "indicadores_geograficos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nivel: Mapped[str] = mapped_column(Text, nullable=False)
    cve: Mapped[str] = mapped_column(Text, nullable=False)
    indicador: Mapped[str] = mapped_column(Text, nullable=False)
    valor: Mapped[float | None] = mapped_column(Numeric)
    unidad: Mapped[str | None] = mapped_column(Text)
    fuente: Mapped[str] = mapped_column(Text, nullable=False)
    anio: Mapped[int | None] = mapped_column(SmallInteger)
    fecha_carga: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("nivel", "cve", "indicador", "anio", name="indicadores_geo_unique"),
        CheckConstraint("nivel IN ('entidad','municipio','ageb')", name="indicadores_nivel_check"),
    )


# =============================================================================
# Compliance log
# =============================================================================
class ComplianceLog(Base):
    __tablename__ = "compliance_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fecha: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuarios.id"))
    tipo_operacion: Mapped[str] = mapped_column(Text, nullable=False)
    establecimiento_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("establecimientos.id", ondelete="SET NULL")
    )
    columnas_pii_tocadas: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    finalidad: Mapped[str] = mapped_column(Text, nullable=False)
    base_legal: Mapped[str] = mapped_column(Text, nullable=False)
    arco_solicitud_id: Mapped[str | None] = mapped_column(Text)
    arco_plazo_dias_habiles: Mapped[int | None] = mapped_column(SmallInteger)
    notas: Mapped[str | None] = mapped_column(Text)
