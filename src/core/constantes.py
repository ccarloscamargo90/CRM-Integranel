"""Constantes del proyecto — alcance, taxonomías y umbrales.

Cualquier código que se refiera a "los 8 SCIAN", "los 4 canales", "las 13
entidades priorizadas", o "el bbox de México" debe importar de aquí, no
hardcodear valores. Si un valor cambia (porque INEGI suelta SCIAN 2025 o
porque agregamos un cuarto canal), se cambia aquí y se propaga.
"""

from __future__ import annotations

from typing import Literal

# =============================================================================
# Canales de venta y subtipos
# =============================================================================

Canal = Literal[
    "Tortillerias",
    "AlimentoBalanceado",
    "ForrajerasPecuario",
    "AsociacionesAgropecuarias",
]

CANALES: tuple[Canal, ...] = (
    "Tortillerias",
    "AlimentoBalanceado",
    "ForrajerasPecuario",
    "AsociacionesAgropecuarias",
)

# Subtipos válidos de tipo_establecimiento por canal — ver CLAUDE.md §5.
SUBTIPOS_POR_CANAL: dict[Canal, tuple[str, ...]] = {
    "Tortillerias": (
        "tortilleria_tradicional",
        "tortilleria_moderna",
        "molino_nixtamal",
        "harinera_maiz",
        "harinera_trigo",
        "comercio_masa",
        "autoservicio",
        "desconocido",
    ),
    "AlimentoBalanceado": (
        "fabricante_industrial",
        "desconocido",
    ),
    "ForrajerasPecuario": (
        "forrajera_rural",
        "mayoreo_granos",
        "desconocido",
    ),
    "AsociacionesAgropecuarias": (
        "asociacion_ganadera_local",
        "union_ganadera_regional",
        "sociedad_produccion_rural",
        "camara",
        "desconocido",
    ),
}

# =============================================================================
# SCIAN objetivo — 8 códigos primarios
# =============================================================================

# Mapping SCIAN → (descripción, canal). Es la tabla maestra que usan
# audit/scian.py, ingestion/denue.py y enrichment/scoring.py.
SCIAN_OBJETIVO: dict[str, tuple[str, Canal]] = {
    "311830": ("Elaboración de tortillas de maíz y molienda de nixtamal", "Tortillerias"),
    "461160": ("Comercio al por menor de productos derivados de la masa", "Tortillerias"),
    "311212": ("Elaboración de harina de maíz", "Tortillerias"),
    "311211": ("Elaboración de harina de trigo", "Tortillerias"),
    "311110": ("Elaboración de alimentos para animales", "AlimentoBalanceado"),
    "434112": (
        "Comercio al por mayor de medicamentos veterinarios y alimentos para animales",
        "ForrajerasPecuario",
    ),
    "434225": (
        "Comercio al por mayor de semillas y granos alimenticios",
        "ForrajerasPecuario",
    ),
    "813110": (
        "Asociaciones, organizaciones y cámaras de productores",
        "AsociacionesAgropecuarias",
    ),
}

SCIAN_PRIMARIOS: frozenset[str] = frozenset(SCIAN_OBJETIVO.keys())

# SCIAN de cruce on-demand (Fase 5) — descartados de descarga primaria
# por volumen excesivo o relevancia marginal. Documentado en CLAUDE.md §5.
SCIAN_CRUCE_ONDEMAND: frozenset[str] = frozenset({
    "461110",  # Abarrotes menudeo (387K — ruido)
    "431110",  # Abarrotes mayoreo (marginal)
})


def canal_de_scian(scian: str) -> Canal | None:
    """Devuelve el canal asociado al SCIAN, o None si no es objetivo."""
    par = SCIAN_OBJETIVO.get(scian)
    return par[1] if par else None


# =============================================================================
# Entidades priorizadas (16 estados — centro-sureste + Bajío)
# =============================================================================

# Cve INEGI → nombre. Ver CLAUDE.md §5 para densidad por canal.
# Ampliado 2026-04-30: se agregan 01 (Aguascalientes), 11 (Guanajuato),
# 22 (Querétaro) por solicitud del operador (incluyen cadenas relevantes
# como La Oriental en QRO, ALPLI en GTO, etc.).
ENTIDADES_PRIORIZADAS: dict[str, str] = {
    "01": "Aguascalientes",
    "04": "Campeche",
    "07": "Chiapas",
    "09": "Ciudad de México",
    "11": "Guanajuato",
    "13": "Hidalgo",
    "15": "Estado de México",
    "17": "Morelos",
    "20": "Oaxaca",
    "21": "Puebla",
    "22": "Querétaro",
    "23": "Quintana Roo",
    "27": "Tabasco",
    "29": "Tlaxcala",
    "30": "Veracruz",
    "31": "Yucatán",
}

CVE_ENTIDADES_PRIORIZADAS: frozenset[str] = frozenset(ENTIDADES_PRIORIZADAS.keys())

# Todas las entidades MX (32) para validación universal de cves.
TODAS_ENTIDADES_MX: frozenset[str] = frozenset(
    f"{i:02d}" for i in range(1, 33)
)


# =============================================================================
# Geografía México — bbox para validar lat/lon
# =============================================================================

# Bounding box generoso de México continental + islas + península Yucatán.
# Usado en audit/geo_anomalies.py para flagear coords sospechosas.
BBOX_MX_LAT_MIN: float = 14.5
BBOX_MX_LAT_MAX: float = 32.7
BBOX_MX_LON_MIN: float = -118.4
BBOX_MX_LON_MAX: float = -86.7


def en_bbox_mx(lat: float, lon: float) -> bool:
    """True si (lat, lon) cae dentro del bbox de México."""
    return (
        BBOX_MX_LAT_MIN <= lat <= BBOX_MX_LAT_MAX
        and BBOX_MX_LON_MIN <= lon <= BBOX_MX_LON_MAX
    )


# =============================================================================
# Estados del pipeline comercial
# =============================================================================

EstadoPipeline = Literal[
    "no_contactado",
    "prospecto",
    "contactado",
    "visitado",
    "cotizado",
    "ganado",
    "perdido",
    "descartado",
    "pausado",
]

ESTADOS_PIPELINE: tuple[EstadoPipeline, ...] = (
    "no_contactado",
    "prospecto",
    "contactado",
    "visitado",
    "cotizado",
    "ganado",
    "perdido",
    "descartado",
    "pausado",
)

# Pipeline "abierto" = se sigue trabajando. "cerrado" = ya no se trabaja.
ESTADOS_ABIERTOS: frozenset[str] = frozenset(
    {"no_contactado", "prospecto", "contactado", "visitado", "cotizado", "pausado"}
)
ESTADOS_CERRADOS: frozenset[str] = frozenset({"ganado", "perdido", "descartado"})

# =============================================================================
# Segmentación A/B/C
# =============================================================================

SegmentoABC = Literal["A", "B", "C", "X"]

# A = top 20%, B = 20-60%, C = 60-100%, X = falta data clave
UMBRALES_ABC: dict[SegmentoABC, tuple[float, float]] = {
    "A": (80.0, 100.0),
    "B": (40.0, 80.0),
    "C": (0.0, 40.0),
}
