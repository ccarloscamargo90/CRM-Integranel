"""Mapeo de respuesta DENUE → modelo `Establecimiento` del schema.

Toma un `EstablecimientoDenueRaw` y devuelve un dict listo para hacer
`session.add(Establecimiento(**dict))` o un upsert SQL.

Decisiones de diseño:
- `nombre` se toma de `Nombre`; si está vacío, se intenta `Razon_social`.
- `nombre_norm` se calcula con `heuristicas.normaliza_nombre`.
- `hash_dedup` se calcula incluso cuando lat/lon faltan (con None coords).
- `geom` NO se asigna aquí — se rellena con un UPDATE PostGIS tras el insert
  (`ST_SetSRID(ST_MakePoint(lon, lat), 4326)`). Hacerlo aquí requiere un
  binding extra y complica los tests; preferimos un helper SQL.
- `canales` se inicializa con el canal natural del SCIAN.
- `tipo_establecimiento` se infiere de SCIAN + nombre (refinamiento heurístico).
- `volumen_estimado_ton_mes` se calcula con empleados + ratio del subtipo.
- `fuentes` se setea a `["DENUE_API"]`.
"""

from __future__ import annotations

from typing import Any

from src.core.constantes import ENTIDADES_PRIORIZADAS, TODAS_ENTIDADES_MX
from src.core.heuristicas import (
    canales_iniciales_de_scian,
    estrato_a_empleados,
    hash_dedup,
    normaliza_nombre,
    scian_desde_clee,
    tipo_establecimiento_de_scian,
    volumen_estimado_ton_mes,
)
from src.ingestion.denue_models import EstablecimientoDenueRaw

# Tabla de nombres oficiales de entidades por cve INEGI — incluye las 32.
# Para cves no priorizadas usamos un nombre generic — se llena con el catálogo
# completo INEGI cuando carguemos el Marco Geoestadístico (Fase 5.3).
_NOMBRES_ENTIDADES_PARCIAL: dict[str, str] = dict(ENTIDADES_PRIORIZADAS)


class ParseError(ValueError):
    """El registro DENUE no se puede mapear a Establecimiento."""


def to_establecimiento_dict(raw: EstablecimientoDenueRaw) -> dict[str, Any]:
    """Convierte la respuesta cruda DENUE en un dict para el modelo Establecimiento.

    Levanta `ParseError` si el registro no tiene los campos mínimos
    (`CLEE` + nombre + SCIAN extraíble).
    """
    if not raw.CLEE:
        raise ParseError("CLEE faltante")

    nombre = (raw.Nombre or raw.Razon_social or "").strip()
    if not nombre:
        raise ParseError(f"Nombre y Razon_social vacíos en CLEE {raw.CLEE}")

    scian = scian_desde_clee(raw.CLEE)
    if not scian:
        raise ParseError(f"No se pudo extraer SCIAN del CLEE {raw.CLEE}")

    cve_entidad = raw.cve_entidad
    cve_municipio = raw.cve_municipio
    estado_nombre = _NOMBRES_ENTIDADES_PARCIAL.get(cve_entidad or "", "")

    nombre_norm = normaliza_nombre(nombre)
    cp = (raw.CP or "").strip() or None
    lat = raw.lat_float
    lon = raw.lon_float

    empleados = estrato_a_empleados(raw.Estrato)
    tipo_est = tipo_establecimiento_de_scian(scian, nombre)
    volumen = volumen_estimado_ton_mes(tipo_est, empleados)

    direccion_partes = [
        raw.Tipo_vialidad,
        raw.Calle,
        raw.Num_Exterior,
        raw.Colonia,
    ]
    direccion = " ".join(p for p in direccion_partes if p) or None

    return {
        # Identidad
        "clee": raw.CLEE,
        "hash_dedup": hash_dedup(nombre, cp, lat, lon),
        "nombre": nombre,
        "nombre_norm": nombre_norm,
        "razon_social": (raw.Razon_social or "").strip() or None,
        # SCIAN + canal
        "scian_codigo": scian,
        "scian_descripcion": (raw.Clase_actividad or "").strip() or None,
        "canales": canales_iniciales_de_scian(scian),
        "tipo_establecimiento": tipo_est,
        # Ubicación
        "direccion": direccion,
        "tipo_vialidad": (raw.Tipo_vialidad or "").strip() or None,
        "nombre_vialidad": (raw.Calle or "").strip() or None,
        "numero_exterior": (raw.Num_Exterior or "").strip() or None,
        "numero_interior": (raw.Num_Interior or "").strip() or None,
        "colonia": (raw.Colonia or "").strip() or None,
        "cp": cp,
        "municipio_codigo": cve_municipio,
        "localidad": (raw.Ubicacion or "").strip() or None,
        "estado": estado_nombre or None,
        "estado_codigo": cve_entidad,
        "latitud": lat,
        "longitud": lon,
        # Contacto
        "telefono": (raw.Telefono or "").strip() or None,
        "email": (raw.Correo_e or "").strip() or None,
        "sitio_web": (raw.Sitio_internet or "").strip() or None,
        # Tamaño
        "estrato_personal_denue": (raw.Estrato or "").strip() or None,
        "empleados_est": empleados,
        "volumen_estimado_ton_mes": volumen,
        "tipo_unidad": (raw.Tipo or "").strip() or None,
        # Trazabilidad
        "fuentes": ["DENUE_API"],
    }


def es_entidad_priorizada(cve: str | None) -> bool:
    return cve in ENTIDADES_PRIORIZADAS


def es_entidad_valida_mx(cve: str | None) -> bool:
    return cve in TODAS_ENTIDADES_MX
