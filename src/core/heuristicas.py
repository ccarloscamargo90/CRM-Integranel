"""Heurísticas reutilizadas en ingestión y enrichment.

- `normaliza_nombre`: minúsculas + sin acentos + sin espacios extra. Para fuzzy + hash.
- `hash_dedup`: sha1 de (nombre_norm + cp + lat_round + lon_round).
- `estrato_a_empleados`: punto medio del rango DENUE.
- `ratio_volumen`: ton/mes por empleado, dependiente de canal+subtipo.
- `volumen_estimado_ton_mes`: aplica ratio.
- `tipo_establecimiento_de_scian`: subtipo natural del SCIAN dado.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from src.core.constantes import canal_de_scian

# =============================================================================
# Normalización y deduplicación
# =============================================================================

_RE_ESPACIOS = re.compile(r"\s+")
_RE_NO_ALFANUM = re.compile(r"[^\w\s]")


def normaliza_nombre(nombre: str | None) -> str:
    """Lowercase + sin acentos + sin signos + espacios colapsados.

    Para fuzzy matching y hash_dedup. Idempotente.

    >>> normaliza_nombre("Tortillería  La Esperanza, S.A. de C.V.")
    'tortilleria la esperanza s a de c v'
    """
    if not nombre:
        return ""
    s = nombre.strip().lower()
    # Quita acentos: NFD descompone, encoding ASCII drop ignora los combining marks.
    s = unicodedata.normalize("NFD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = _RE_NO_ALFANUM.sub(" ", s)
    s = _RE_ESPACIOS.sub(" ", s).strip()
    return s


def hash_dedup(
    nombre: str,
    cp: str | None,
    latitud: float | None,
    longitud: float | None,
    *,
    decimales_coord: int = 4,
) -> str:
    """sha1 hex de la tupla normalizada nombre+cp+lat_round+lon_round.

    `decimales_coord=4` redondea coords a ~10 m → tolerancia para que el mismo
    establecimiento capturado dos veces con lat/lon ligeramente distintas
    colisione en hash y dispare deduplicación.
    """
    nombre_norm = normaliza_nombre(nombre)
    cp_norm = (cp or "").strip()
    lat_str = f"{round(latitud, decimales_coord)}" if latitud is not None else ""
    lon_str = f"{round(longitud, decimales_coord)}" if longitud is not None else ""
    raw = f"{nombre_norm}|{cp_norm}|{lat_str}|{lon_str}"
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


# =============================================================================
# Estrato DENUE → empleados estimados
# =============================================================================

# Mapeo del campo `Estrato` del DENUE al punto medio del rango.
# El DENUE clasifica establecimientos por personal ocupado en estos 7 estratos.
_ESTRATO_EMPLEADOS = {
    "0 a 5 personas": 3,
    "6 a 10 personas": 8,
    "11 a 30 personas": 20,
    "31 a 50 personas": 40,
    "51 a 100 personas": 75,
    "101 a 250 personas": 175,
    "251 y más personas": 350,
}


def estrato_a_empleados(estrato: str | None) -> int | None:
    """Convierte el estrato textual del DENUE al punto medio del rango.
    Devuelve None si el estrato es desconocido (raro pero posible)."""
    if not estrato:
        return None
    return _ESTRATO_EMPLEADOS.get(estrato.strip())


# =============================================================================
# tipo_establecimiento por SCIAN
# =============================================================================

# Mapeo SCIAN → subtipo (ver `constantes.SUBTIPOS_POR_CANAL`).
# Para SCIAN ambiguos (ej. 311830 que incluye tortillerías y molinos) se usa
# 'desconocido' como default — un humano o un clasificador refinado lo separa
# en Fase 6 (scoring).
_SUBTIPO_DEFAULT_POR_SCIAN: dict[str, str] = {
    "311830": "tortilleria_tradicional",  # default; refinar si nombre contiene "molino"
    "461160": "comercio_masa",
    "311212": "harinera_maiz",
    "311211": "harinera_trigo",
    "311110": "fabricante_industrial",
    "434112": "forrajera_rural",
    "434225": "mayoreo_granos",
    "813110": "asociacion_ganadera_local",
}


def tipo_establecimiento_de_scian(scian: str, nombre: str | None = None) -> str:
    """Devuelve el subtipo natural del SCIAN; refina con el nombre si aplica.

    Ejemplos:
    - 311830 + nombre "Molino San Pedro" → 'molino_nixtamal'
    - 311830 + nombre "Tortillería La Higiénica" → 'tortilleria_tradicional'
    - 311830 + nombre con "moderna" o "mecanizada" → 'tortilleria_moderna'
    - 813110 + nombre "Unión Ganadera Regional ..." → 'union_ganadera_regional'
    """
    base = _SUBTIPO_DEFAULT_POR_SCIAN.get(scian, "desconocido")

    if not nombre:
        return base

    # Comparamos contra el nombre normalizado (sin acentos), porque el DENUE
    # puede traer el nombre con o sin tildes según captura.
    nombre_l = normaliza_nombre(nombre)

    # Refinamientos heurísticos por nombre
    if scian == "311830":
        if "molino" in nombre_l and "nixtam" in nombre_l:
            return "molino_nixtamal"
        if "molino" in nombre_l:
            return "molino_nixtamal"
        if "moderna" in nombre_l or "mecaniza" in nombre_l:
            return "tortilleria_moderna"
        if "harin" in nombre_l:
            return "harinera_maiz"
    elif scian == "813110":
        if "union" in nombre_l and "ganader" in nombre_l:
            return "union_ganadera_regional"
        if "sociedad" in nombre_l and "produccion" in nombre_l:
            return "sociedad_produccion_rural"
        if "camara" in nombre_l:
            return "camara"
    elif scian == "434112":
        if "mayor" in nombre_l or "distribuidora" in nombre_l:
            return "mayoreo_granos"

    return base


# =============================================================================
# Volumen estimado de masa / grano por mes
# =============================================================================

# Ratios ton/mes/empleado. Heurísticos iniciales — calibrar contra clientes reales en Fase 6.
_RATIO_TON_MES_POR_EMPLEADO: dict[str, float] = {
    # Tortillerías
    "tortilleria_tradicional": 1.8,
    "tortilleria_moderna": 2.5,
    "molino_nixtamal": 3.0,
    "harinera_maiz": 6.0,
    "harinera_trigo": 4.0,
    "comercio_masa": 2.0,
    "autoservicio": 5.0,
    # AlimentoBalanceado — escala industrial, mucho mayor
    "fabricante_industrial": 50.0,
    # ForrajerasPecuario
    "forrajera_rural": 4.0,
    "mayoreo_granos": 8.0,
    # AsociacionesAgropecuarias — proxy: la asociación misma representa muchos socios.
    # En Fase 6 con datos de socios reales, refinamos.
    "asociacion_ganadera_local": 15.0,
    "union_ganadera_regional": 40.0,
    "sociedad_produccion_rural": 10.0,
    "camara": 60.0,
    "desconocido": 2.0,
}


def volumen_estimado_ton_mes(
    tipo_establecimiento: str | None, empleados_est: int | None
) -> float | None:
    """Devuelve toneladas/mes estimadas en función del tipo y empleados.

    Devuelve None si falta cualquiera de los dos inputs.
    """
    if tipo_establecimiento is None or empleados_est is None:
        return None
    ratio = _RATIO_TON_MES_POR_EMPLEADO.get(tipo_establecimiento, 2.0)
    return round(empleados_est * ratio, 2)


# =============================================================================
# Canales asignados (incluye dualidad si aplica)
# =============================================================================


def canales_iniciales_de_scian(scian: str) -> list[str]:
    """Devuelve la lista inicial de canales[] al cargar desde DENUE.

    Por defecto, un canal único (el natural del SCIAN). La dualidad
    (granza, etc.) se infiere después en Fase 6 con scoring + reglas de negocio.
    """
    canal = canal_de_scian(scian)
    return [canal] if canal else []


# =============================================================================
# Extracción de SCIAN desde CLEE
# =============================================================================

# CLEE INEGI: 28 chars. Estructura: 2 entidad + 3 municipio + 6 SCIAN + 6 num + 6 ceros + 1 verificador
def scian_desde_clee(clee: str | None) -> str | None:
    """Extrae el SCIAN (6 dígitos) de un CLEE bien formado."""
    if not clee or len(clee) < 11:
        return None
    candidato = clee[5:11]
    if candidato.isdigit():
        return candidato
    return None
