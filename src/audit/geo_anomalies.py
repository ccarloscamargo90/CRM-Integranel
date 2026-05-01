"""Detección de anomalías geográficas en `establecimientos`.

Cuatro chequeos:
1. `check_coords_nulas_o_cero` — coords (0, 0) o NULL → registro sin geo.
2. `check_fuera_bbox_mx` — coords fuera del bbox MX → error de captura.
3. `check_lat_lon_invertidas` — heurística: si lat parece longitud y viceversa.
4. `check_geom_vs_lat_lon` — la columna `geom` debe coincidir con (latitud, longitud).
"""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from src.audit.models import Hallazgo
from src.core.constantes import (
    BBOX_MX_LAT_MAX,
    BBOX_MX_LAT_MIN,
    BBOX_MX_LON_MAX,
    BBOX_MX_LON_MIN,
)
from src.core.models import Establecimiento


def check_coords_nulas_o_cero(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """Latitud o longitud nula, o (0, 0) literal — coordenadas inválidas."""
    cond = or_(
        Establecimiento.latitud.is_(None),
        Establecimiento.longitud.is_(None),
        and_(Establecimiento.latitud == 0.0, Establecimiento.longitud == 0.0),
    )
    total_evaluados = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()
    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond)
    ).scalar_one()
    ejemplos = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.latitud,
            Establecimiento.longitud,
        )
        .where(cond)
        .limit(max_ejemplos)
    ).all()

    return Hallazgo(
        chequeo="geo.coords_nulas_o_cero",
        severidad="warning",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle="Coords NULL o (0,0) — establecimiento sin geo, no aparecerá en mapa",
        ejemplos=[
            {"id": r[0], "nombre": r[1], "lat": r[2], "lon": r[3]}
            for r in ejemplos
        ],
    )


def check_fuera_bbox_mx(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """Coords fuera del bbox de México — error de captura o registro fuera de scope."""
    cond_dentro_bbox = and_(
        Establecimiento.latitud.between(BBOX_MX_LAT_MIN, BBOX_MX_LAT_MAX),
        Establecimiento.longitud.between(BBOX_MX_LON_MIN, BBOX_MX_LON_MAX),
    )
    cond_fuera = and_(
        Establecimiento.latitud.is_not(None),
        Establecimiento.longitud.is_not(None),
        ~cond_dentro_bbox,
    )

    total_evaluados = session.execute(
        select(func.count())
        .select_from(Establecimiento)
        .where(
            and_(
                Establecimiento.latitud.is_not(None),
                Establecimiento.longitud.is_not(None),
            )
        )
    ).scalar_one()
    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond_fuera)
    ).scalar_one()
    ejemplos = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.latitud,
            Establecimiento.longitud,
            Establecimiento.estado,
        )
        .where(cond_fuera)
        .limit(max_ejemplos)
    ).all()

    return Hallazgo(
        chequeo="geo.fuera_bbox_mx",
        severidad="error",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle=(
            f"Bbox MX: lat ∈ [{BBOX_MX_LAT_MIN}, {BBOX_MX_LAT_MAX}], "
            f"lon ∈ [{BBOX_MX_LON_MIN}, {BBOX_MX_LON_MAX}]"
        ),
        ejemplos=[
            {
                "id": r[0], "nombre": r[1], "lat": r[2], "lon": r[3], "estado": r[4]
            }
            for r in ejemplos
        ],
    )


def check_lat_lon_invertidas(session: Session, *, max_ejemplos: int = 10) -> Hallazgo:
    """Heurística: si latitud parece longitud (negativa o > 32) y longitud parece
    latitud (en rango lat MX), están invertidas.

    Ej.: lat=-99.13, lon=19.43 (lat=México, lon=México sería 19.43, -99.13).
    """
    # Latitud "parece longitud" si está en rango -118 a -86 (rango lon MX)
    # Longitud "parece latitud" si está en rango 14.5 a 32.7 (rango lat MX)
    cond = and_(
        Establecimiento.latitud.is_not(None),
        Establecimiento.longitud.is_not(None),
        Establecimiento.latitud.between(BBOX_MX_LON_MIN, BBOX_MX_LON_MAX),
        Establecimiento.longitud.between(BBOX_MX_LAT_MIN, BBOX_MX_LAT_MAX),
    )
    total_evaluados = session.execute(
        select(func.count())
        .select_from(Establecimiento)
        .where(
            and_(
                Establecimiento.latitud.is_not(None),
                Establecimiento.longitud.is_not(None),
            )
        )
    ).scalar_one()
    total_problemas = session.execute(
        select(func.count()).select_from(Establecimiento).where(cond)
    ).scalar_one()
    ejemplos = session.execute(
        select(
            Establecimiento.id,
            Establecimiento.nombre_norm,
            Establecimiento.latitud,
            Establecimiento.longitud,
        )
        .where(cond)
        .limit(max_ejemplos)
    ).all()

    return Hallazgo(
        chequeo="geo.lat_lon_invertidas",
        severidad="error",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle="Heurística: lat parece longitud y viceversa — error de captura",
        ejemplos=[
            {"id": r[0], "nombre": r[1], "lat": r[2], "lon": r[3]} for r in ejemplos
        ],
    )


def check_geom_coincide_lat_lon(
    session: Session, *, tolerancia_grados: float = 1e-5, max_ejemplos: int = 10
) -> Hallazgo:
    """`geom` debe ser POINT(longitud, latitud) en SRID 4326. Si difiere de
    las columnas (latitud, longitud), hay desincronización entre el insert
    y el campo derivado.

    Compara con tolerancia chica (1e-5 ≈ 1 metro) por errores de redondeo.
    """
    # ST_X(geom) = lon, ST_Y(geom) = lat
    sql = text(
        """
        SELECT id, nombre_norm, latitud, longitud,
               ST_Y(geom::geometry) AS geom_lat,
               ST_X(geom::geometry) AS geom_lon
        FROM establecimientos
        WHERE geom IS NOT NULL
          AND latitud IS NOT NULL
          AND longitud IS NOT NULL
          AND (
              ABS(ST_Y(geom::geometry) - latitud)  > :tol OR
              ABS(ST_X(geom::geometry) - longitud) > :tol
          )
        LIMIT :limite
    """
    )
    rows = session.execute(
        sql, {"tol": tolerancia_grados, "limite": max_ejemplos}
    ).all()

    sql_count = text(
        """
        SELECT COUNT(*)
        FROM establecimientos
        WHERE geom IS NOT NULL
          AND latitud IS NOT NULL
          AND longitud IS NOT NULL
          AND (
              ABS(ST_Y(geom::geometry) - latitud)  > :tol OR
              ABS(ST_X(geom::geometry) - longitud) > :tol
          )
    """
    )
    total_problemas = session.execute(sql_count, {"tol": tolerancia_grados}).scalar_one()

    sql_eval = text(
        "SELECT COUNT(*) FROM establecimientos WHERE geom IS NOT NULL"
    )
    total_evaluados = session.execute(sql_eval).scalar_one()

    return Hallazgo(
        chequeo="geo.geom_vs_lat_lon",
        severidad="warning",
        total_evaluados=total_evaluados,
        total_problemas=total_problemas,
        detalle=f"Tolerancia: {tolerancia_grados} grados (~1 m)",
        ejemplos=[
            {
                "id": r[0], "nombre": r[1],
                "lat": r[2], "lon": r[3],
                "geom_lat": float(r[4]), "geom_lon": float(r[5]),
            }
            for r in rows
        ],
    )
