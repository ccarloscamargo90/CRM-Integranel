"""Detector de cadenas — dos estrategias en orden de confianza.

**Estrategia 1 (alta confianza): razón social compartida.**
Si dos o más establecimientos comparten `raz_social` no nula, son **la misma
empresa legal**. Esto identifica cadenas reales como BACHOCO, PURINA,
INDUSTRIAS DEL MAÍZ PUEBLA, MOLINERA DE MÉXICO. Solo ~4% del DENUE tiene
razón social, pero entre ellos están los clientes corporativos.

**Estrategia 2 (baja confianza, fallback): marca residual del nombre.**
Para los ~96% sin razón social, agrupa por "marca" tras quitar palabras
genéricas. Útil para detectar tortillerías locales con varias sucursales,
pero produce falsos positivos: "La Lupita" / "La Guadalupana" son nombres
muy comunes con dueños distintos. NO se usa por defecto; queda como
opción explícita (`incluir_marca_residual=True`).

`detectar_cadenas` ejecuta solo estrategia 1 por defecto (precisión > recall).
"""

from __future__ import annotations

import re
from collections import defaultdict

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from src.core.constantes import SCIAN_PRIMARIOS, canal_de_scian
from src.core.models import Cadena, Establecimiento

# Palabras "ruidosas" que no aportan a la marca. Si el nombre tras quitarlas
# queda vacío, es un negocio genérico sin cadena.
_PALABRAS_GENERICAS = frozenset(
    {
        # Tipo de establecimiento
        "tortilleria", "tortilla", "tortillas",
        "molino", "molinos", "nixtamal",
        "harinera", "harineria",
        "abarrotes", "abarrotera", "abarrotero",
        "comercio", "expendio",
        "forrajera", "forraje", "forrajes", "alimentos",
        "asociacion", "asociaciones", "union", "uniones",
        "ganadera", "ganaderia", "ganaderos",
        "productores", "productor", "produccion", "rural",
        "sociedad", "camara",
        "agropecuaria", "agropecuario",
        # Verbos / acciones (DENUE describe establecimiento sin marca con esto)
        "elaboracion", "venta", "comercializacion", "fabricacion",
        "preparacion", "molienda", "distribucion",
        "hechas", "hecho", "elaborada", "elaborado",
        "totopos", "totopo", "comal", "dulceria", "dulces",
        "mano", "maquina", "maquinaria", "mecanizada",
        "maiz", "trigo", "harina", "masa",
        # Conectores
        "la", "el", "los", "las",
        "de", "del", "y", "para", "con",
        "san", "santa", "santo", "sin", "nombre",
        # Generales
        "mx", "sa", "cv", "rl", "srl",
        "sucursal", "sucursales",
    }
)

# Regex para detectar nombres que son descripción de actividad (no marca real).
# Ejemplos: "ELABORACION DE TORTILLAS SIN NOMBRE", "VENTA DE TORTILLAS"
_RE_NOMBRES_GENERICOS = re.compile(
    r"\b(sin\s+nombre|elaboracion|venta\s+de|comercializacion|fabricacion|"
    r"preparacion|molienda)\b",
    re.IGNORECASE,
)

_RE_TOKENS = re.compile(r"[a-z0-9]+")
_UMBRAL_SUCURSALES = 3


def _es_nombre_descriptivo(nombre_norm: str) -> bool:
    """True si el nombre es claramente una descripción genérica (no marca real)."""
    return bool(_RE_NOMBRES_GENERICOS.search(nombre_norm))


def _clave_marca(nombre_norm: str) -> str | None:
    """Devuelve la 'marca' tras quitar palabras genéricas. None si queda vacío
    o si el nombre es claramente descriptivo (no marca)."""
    if _es_nombre_descriptivo(nombre_norm):
        return None
    tokens = _RE_TOKENS.findall(nombre_norm)
    significativos = [t for t in tokens if t not in _PALABRAS_GENERICAS and len(t) >= 3]
    if not significativos:
        return None
    # Requiere al menos 1 token significativo para ser "marca"; preferimos cadenas
    # con mínimo 1 palabra distintiva. Casos como "lupita" solo son válidos.
    return " ".join(significativos)


def _normaliza_razon_social(raz: str | None) -> str | None:
    """Normaliza la razón social: lowercase, sin acentos, espacios colapsados.
    Usa la misma normalización del nombre para que comparaciones sean estables.
    """
    if not raz or not raz.strip():
        return None
    from src.core.heuristicas import normaliza_nombre

    return normaliza_nombre(raz)


def detectar_cadenas(
    session: Session,
    *,
    umbral: int = _UMBRAL_SUCURSALES,
    incluir_marca_residual: bool = False,
) -> dict:
    """Detecta cadenas con dos estrategias.

    1. Por **razón social compartida** (alta confianza). Default ON.
    2. Por **marca residual del nombre** (baja confianza, opcional).

    `umbral`: mínimo de sucursales para considerarse cadena.
    `incluir_marca_residual`: si True, agrega cadenas heurísticas (con
    `tipo='heuristica'`); útil para descubrimiento amplio pero ruidoso.

    Devuelve métricas agregadas.
    """
    n_cadenas_razon = 0
    n_vinculados_razon = 0
    n_cadenas_marca = 0
    n_vinculados_marca = 0
    metricas_por_scian: dict[str, dict[str, int]] = {}

    # ---------- Estrategia 1: razón social ----------
    rows = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.razon_social,
            Establecimiento.nombre,
            Establecimiento.scian_codigo,
        ).where(
            Establecimiento.scian_codigo.in_(SCIAN_PRIMARIOS),
            Establecimiento.razon_social.is_not(None),
            Establecimiento.razon_social != "",
        )
    ).all()

    grupos_razon: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for r in rows:
        clave = _normaliza_razon_social(r.razon_social)
        if clave:
            grupos_razon[clave].append((r.id, r.nombre, r.scian_codigo))

    for clave, ests in grupos_razon.items():
        if len(ests) < umbral:
            continue
        # SCIAN dominante del grupo determina el canal
        from collections import Counter

        scian_dominante = Counter(e[2] for e in ests).most_common(1)[0][0]
        canal = canal_de_scian(scian_dominante)
        # Razón social legible del primer establecimiento (suele ser representativa)
        razon_legible = next(
            (e[1] for e in ests if e[1]),
            ests[0][1] or clave,
        )
        # `nombre_grupo` = razón social formatted; `nombre_grupo_norm` = clave normalizada
        existente = session.execute(
            select(Cadena).where(Cadena.nombre_grupo_norm == clave)
        ).scalar_one_or_none()
        if existente:
            cadena = existente
            cadena.tipo = "cadena_corporativa"
            cadena.canal_principal = canal
        else:
            cadena = Cadena(
                nombre_grupo=razon_legible.strip().title()[:200],
                nombre_grupo_norm=clave,
                canal_principal=canal,
                sucursales_count=len(ests),
                tipo="cadena_corporativa",
            )
            session.add(cadena)
            session.flush()
            n_cadenas_razon += 1

        ids = [e[0] for e in ests]
        session.execute(
            text(
                "UPDATE establecimientos SET cadena_id = :cid, grupo_marca = :gm "
                "WHERE id = ANY(:ids)"
            ),
            {"cid": cadena.id, "gm": clave, "ids": ids},
        )
        cadena.sucursales_count = len(ests)
        n_vinculados_razon += len(ests)

        # Métricas por SCIAN dominante
        metricas_por_scian.setdefault(scian_dominante, {"corporativas": 0, "heuristicas": 0})
        metricas_por_scian[scian_dominante]["corporativas"] += 1

    logger.info(
        "Estrategia razón social: {c} cadenas corporativas, {v} sucursales",
        c=n_cadenas_razon, v=n_vinculados_razon,
    )

    # ---------- Estrategia 2 (opcional): marca residual ----------
    if incluir_marca_residual:
        for scian in sorted(SCIAN_PRIMARIOS):
            rows = session.execute(
                select(
                    Establecimiento.id,
                    Establecimiento.nombre,
                    Establecimiento.nombre_norm,
                ).where(
                    Establecimiento.scian_codigo == scian,
                    Establecimiento.cadena_id.is_(None),  # solo los no vinculados aún
                )
            ).all()

            grupos: dict[str, list[tuple[int, str]]] = defaultdict(list)
            for r in rows:
                marca = _clave_marca(r.nombre_norm or "")
                if marca:
                    grupos[marca].append((r.id, r.nombre))

            canal = canal_de_scian(scian)
            for marca, ests in grupos.items():
                if len(ests) < umbral:
                    continue
                nombre_legible = ests[0][1].strip().title()
                existente = session.execute(
                    select(Cadena).where(Cadena.nombre_grupo_norm == marca)
                ).scalar_one_or_none()
                if existente:
                    cadena = existente
                else:
                    cadena = Cadena(
                        nombre_grupo=nombre_legible[:200],
                        nombre_grupo_norm=marca,
                        canal_principal=canal,
                        sucursales_count=len(ests),
                        tipo="heuristica",
                    )
                    session.add(cadena)
                    session.flush()
                    n_cadenas_marca += 1

                ids = [e[0] for e in ests]
                session.execute(
                    text(
                        "UPDATE establecimientos SET cadena_id = :cid, grupo_marca = :gm "
                        "WHERE id = ANY(:ids) AND cadena_id IS NULL"
                    ),
                    {"cid": cadena.id, "gm": marca, "ids": ids},
                )
                cadena.sucursales_count = len(ests)
                n_vinculados_marca += len(ests)

                metricas_por_scian.setdefault(scian, {"corporativas": 0, "heuristicas": 0})
                metricas_por_scian[scian]["heuristicas"] += 1

        logger.info(
            "Estrategia marca residual: {c} cadenas heurísticas, {v} sucursales",
            c=n_cadenas_marca, v=n_vinculados_marca,
        )

    return {
        "cadenas_corporativas": n_cadenas_razon,
        "sucursales_corporativas": n_vinculados_razon,
        "cadenas_heuristicas": n_cadenas_marca,
        "sucursales_heuristicas": n_vinculados_marca,
        "por_scian": metricas_por_scian,
    }


def listar_top_cadenas(session: Session, *, top: int = 20) -> list[dict]:
    """Lista las cadenas con más sucursales para revisión."""
    rows = session.execute(
        text(
            """
            SELECT c.nombre_grupo, c.nombre_grupo_norm, c.canal_principal,
                   COUNT(e.id) AS n_sucursales,
                   COUNT(DISTINCT e.estado_codigo) AS n_estados
            FROM cadenas c
            JOIN establecimientos e ON e.cadena_id = c.id
            GROUP BY c.id, c.nombre_grupo, c.nombre_grupo_norm, c.canal_principal
            ORDER BY n_sucursales DESC
            LIMIT :top
        """
        ),
        {"top": top},
    ).all()
    return [
        {
            "nombre_grupo": r.nombre_grupo,
            "marca_norm": r.nombre_grupo_norm,
            "canal": r.canal_principal,
            "n_sucursales": r.n_sucursales,
            "n_estados": r.n_estados,
        }
        for r in rows
    ]
