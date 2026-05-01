"""Detector de cadenas — agrupa establecimientos con nombre similar dentro
del mismo SCIAN.

Heurística simple, escalable:
1. Para cada SCIAN objetivo, leer (id, nombre_norm, municipio_codigo).
2. Bloque por SCIAN.
3. Dentro del bloque, agrupar por una **clave normalizada**:
   - Quitar palabras genéricas frecuentes (TORTILLERIA, MOLINO, LA, EL, DEL, etc.)
   - Si la "marca" residual aparece en ≥3 establecimientos → cadena.
4. Persistir en `cadenas` y vincular con `establecimientos.cadena_id`.

Esta heurística es deliberadamente conservadora — prefiere falsos negativos
(no agrupar) sobre falsos positivos (agrupar mal). El refinamiento con fuzzy
queda para Fase 6 cuando tengamos data real para validar.
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


def detectar_cadenas(session: Session, *, umbral: int = _UMBRAL_SUCURSALES) -> dict:
    """Recorre los SCIAN objetivo, agrupa por marca, persiste cadenas con ≥ `umbral` sucursales.

    Devuelve métricas {scian: {cadenas_creadas, sucursales_vinculadas}}.
    """
    metricas: dict[str, dict[str, int]] = {}
    cadenas_creadas_total = 0
    sucursales_vinculadas_total = 0

    for scian in sorted(SCIAN_PRIMARIOS):
        rows = session.execute(
            select(Establecimiento.id, Establecimiento.nombre, Establecimiento.nombre_norm)
            .where(Establecimiento.scian_codigo == scian)
        ).all()

        # Agrupar por marca
        grupos: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for r in rows:
            marca = _clave_marca(r.nombre_norm or "")
            if marca:
                grupos[marca].append((r.id, r.nombre))

        n_cadenas = 0
        n_vinculados = 0
        canal = canal_de_scian(scian)

        for marca, ests in grupos.items():
            if len(ests) < umbral:
                continue
            # Tomamos el nombre más frecuente como `nombre_grupo` legible
            nombre_grupo_legible = ests[0][1].strip().title()
            # Verificar si ya existe la cadena
            existente = session.execute(
                select(Cadena).where(Cadena.nombre_grupo_norm == marca)
            ).scalar_one_or_none()

            if existente:
                cadena = existente
            else:
                cadena = Cadena(
                    nombre_grupo=nombre_grupo_legible,
                    nombre_grupo_norm=marca,
                    canal_principal=canal,
                    sucursales_count=len(ests),
                    tipo="cadena_local",
                )
                session.add(cadena)
                session.flush()
                n_cadenas += 1

            # Vincular establecimientos a la cadena
            ids = [e[0] for e in ests]
            session.execute(
                text(
                    "UPDATE establecimientos SET cadena_id = :cid, grupo_marca = :gm "
                    "WHERE id = ANY(:ids)"
                ),
                {"cid": cadena.id, "gm": marca, "ids": ids},
            )
            cadena.sucursales_count = len(ests)
            n_vinculados += len(ests)

        metricas[scian] = {
            "cadenas_creadas": n_cadenas,
            "sucursales_vinculadas": n_vinculados,
        }
        cadenas_creadas_total += n_cadenas
        sucursales_vinculadas_total += n_vinculados

        logger.info(
            "SCIAN {scian}: {n_cad} cadenas nuevas, {n_suc} sucursales vinculadas",
            scian=scian,
            n_cad=n_cadenas,
            n_suc=n_vinculados,
        )

    return {
        "por_scian": metricas,
        "cadenas_creadas_total": cadenas_creadas_total,
        "sucursales_vinculadas_total": sucursales_vinculadas_total,
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
