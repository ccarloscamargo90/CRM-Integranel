"""Parser de filas CSV de los ZIPs masivos del DENUE → dict de Establecimiento.

Las columnas CSV difieren del JSON de la API (más campos, snake_case sin tildes,
encoding LATIN1 ya decodificado por el cliente). Mapeo:

CSV col          → schema                     notas
-----------      ----------------------       -----
id               (no se usa)                  id interno DENUE, distinto al nuestro
clee             clee                         UNIQUE
nom_estab        nombre                       — ya viene en LATIN1 decodificado
raz_social       razon_social
codigo_act       scian_codigo
nombre_act       scian_descripcion
per_ocu          estrato_personal_denue       formato "0 a 5 personas" (igual API)
tipo_vial        tipo_vialidad
nom_vial         nombre_vialidad
numero_ext       numero_exterior
numero_int       numero_interior
nomb_asent       colonia
cod_postal       cp
cve_ent          estado_codigo
entidad          estado
cve_mun          municipio_codigo
municipio        (no almacenado por separado)
ageb             ageb
manzana          manzana
telefono         telefono
correo_e         email
www              sitio_web
tipo_unidad      tipo_unidad
latitud, longitud → latitud, longitud
fecha_alta       anio_alta_denue              "2010-07" → 2010
"""

from __future__ import annotations

from typing import Any

from src.core.constantes import ENTIDADES_PRIORIZADAS
from src.core.heuristicas import (
    canales_iniciales_de_scian,
    estrato_a_empleados,
    hash_dedup,
    normaliza_nombre,
    tipo_establecimiento_de_scian,
    volumen_estimado_ton_mes,
)


class CsvParseError(ValueError):
    pass


def _strip_or_none(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s if s else None


def _float_or_none(s: str | None) -> float | None:
    if not s or not s.strip():
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _anio_de_fecha_alta(fecha_alta: str | None) -> int | None:
    """fecha_alta DENUE viene como '2010-07' (YYYY-MM). Devolvemos int."""
    if not fecha_alta:
        return None
    parte = fecha_alta.split("-")[0].strip()
    try:
        return int(parte)
    except ValueError:
        return None


def csv_row_to_establecimiento_dict(row: dict[str, str]) -> dict[str, Any]:
    """Mapea una fila del CSV oficial DENUE al dict de Establecimiento.

    Levanta `CsvParseError` si faltan campos mínimos (clee + nom_estab + codigo_act).
    """
    clee = _strip_or_none(row.get("clee"))
    nombre = _strip_or_none(row.get("nom_estab")) or _strip_or_none(row.get("raz_social"))
    scian = _strip_or_none(row.get("codigo_act"))

    if not clee:
        raise CsvParseError("Falta clee")
    if not nombre:
        raise CsvParseError(f"Falta nom_estab y raz_social en CLEE {clee}")
    if not scian:
        raise CsvParseError(f"Falta codigo_act en CLEE {clee}")

    cp = _strip_or_none(row.get("cod_postal"))
    lat = _float_or_none(row.get("latitud"))
    lon = _float_or_none(row.get("longitud"))

    estrato = _strip_or_none(row.get("per_ocu"))
    empleados = estrato_a_empleados(estrato)
    tipo_est = tipo_establecimiento_de_scian(scian, nombre)
    volumen = volumen_estimado_ton_mes(tipo_est, empleados)

    cve_ent = _strip_or_none(row.get("cve_ent"))
    estado_nombre = _strip_or_none(row.get("entidad")) or ENTIDADES_PRIORIZADAS.get(cve_ent or "", "")

    direccion_partes = [
        _strip_or_none(row.get("tipo_vial")),
        _strip_or_none(row.get("nom_vial")),
        _strip_or_none(row.get("numero_ext")),
        _strip_or_none(row.get("nomb_asent")),
    ]
    direccion = " ".join(p for p in direccion_partes if p) or None

    return {
        # Identidad
        "clee": clee,
        "hash_dedup": hash_dedup(nombre, cp, lat, lon),
        "nombre": nombre,
        "nombre_norm": normaliza_nombre(nombre),
        "razon_social": _strip_or_none(row.get("raz_social")),
        # SCIAN + canales
        "scian_codigo": scian,
        "scian_descripcion": _strip_or_none(row.get("nombre_act")),
        "canales": canales_iniciales_de_scian(scian),
        "tipo_establecimiento": tipo_est,
        # Ubicación
        "direccion": direccion,
        "tipo_vialidad": _strip_or_none(row.get("tipo_vial")),
        "nombre_vialidad": _strip_or_none(row.get("nom_vial")),
        "numero_exterior": _strip_or_none(row.get("numero_ext")),
        "numero_interior": _strip_or_none(row.get("numero_int")),
        "colonia": _strip_or_none(row.get("nomb_asent")),
        "cp": cp,
        "municipio_codigo": _strip_or_none(row.get("cve_mun")),
        "estado": estado_nombre or None,
        "estado_codigo": cve_ent,
        "ageb": _strip_or_none(row.get("ageb")),
        "manzana": _strip_or_none(row.get("manzana")),
        "latitud": lat,
        "longitud": lon,
        # Contacto
        "telefono": _strip_or_none(row.get("telefono")),
        "email": _strip_or_none(row.get("correo_e")),
        "sitio_web": _strip_or_none(row.get("www")),
        # Tamaño
        "estrato_personal_denue": estrato,
        "empleados_est": empleados,
        "volumen_estimado_ton_mes": volumen,
        "tipo_unidad": _strip_or_none(row.get("tipo_unidad")),
        "anio_alta_denue": _anio_de_fecha_alta(_strip_or_none(row.get("fecha_alta"))),
        # Trazabilidad
        "fuentes": ["DENUE_CSV"],
    }
