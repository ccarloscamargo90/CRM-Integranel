"""Carga del Marco Geoestadístico INEGI y spatial join con establecimientos.

INEGI publica shapefiles oficiales del Marco Geoestadístico Nacional con
varias granularidades:

- AGEB urbano (`*_a.shp`)   — Áreas Geoestadísticas Básicas (~1 manzana o pueblo)
- AGEB rural (`*_ar.shp`)   — equivalente para zonas rurales
- Municipal (`*_m.shp`)     — polígonos de los ~2,500 municipios
- Estatal                   — polígonos de las 32 entidades

Catálogo: https://www.inegi.org.mx/temas/mg/

**Flujo operativo recomendado:**
1. Descargar el ZIP de Marco Geoestadístico de la entidad (50-200 MB).
2. Extraer y localizar el `.shp` (con sus archivos auxiliares `.shx`, `.dbf`,
   `.prj`).
3. Correr `python -m src.ingestion.cli --cargar-agebs <path-al-shp>` para
   importar a la tabla `agebs` con geometría PostGIS.
4. Correr `--asignar-agebs` para que cada `establecimientos.geom` herede el
   `cve_ageb` de su AGEB contenedora (spatial join `ST_Within`).

**Por qué no se automatiza la descarga:** los IDs de archivos INEGI cambian
y no hay un endpoint estable por entidad. El operador descarga del catálogo
oficial y le pasa la ruta al CLI.

Ver `data/seeds/README_marco_geoestadistico.md` para el procedimiento manual.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion

# Mapeo de columnas comunes en shapefiles INEGI Marco Geoestadístico.
# Pueden variar según versión; el loader detecta y usa lo que encuentra.
COLUMNAS_INEGI = {
    "cve_ageb": ("CVEGEO", "CVE_GEO", "CVEAGEB"),
    "cve_entidad": ("CVE_ENT", "CVEENT"),
    "cve_municipio": ("CVE_MUN", "CVEMUN"),
    "nombre_municipio": ("NOMGEO", "NOM_MUN"),
    "poblacion": ("POBTOT", "POB_TOT", "POBLACION"),
}


def _resolver_columna(gdf: gpd.GeoDataFrame, opciones: tuple[str, ...]) -> str | None:
    for op in opciones:
        if op in gdf.columns:
            return op
    return None


def cargar_shapefile_a_agebs(
    session: Session,
    shapefile_path: str | Path,
    *,
    cve_entidad: str | None = None,
    nivel: str = "ageb",
) -> dict[str, Any]:
    """Carga un shapefile INEGI a la tabla `agebs`.

    Soporta archivos AGEB urbanos/rurales y, opcionalmente, municipales.

    Devuelve métricas {filas_leidas, filas_insertadas, encoding, srid}.
    """
    path = Path(shapefile_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")

    logger.info("Leyendo shapefile {p}", p=path)
    # INEGI usa LCC México o WGS84 — geopandas detecta del .prj
    gdf = gpd.read_file(path)

    if gdf.empty:
        return {"filas_leidas": 0, "filas_insertadas": 0}

    # Reproyectar a SRID 4326 si está en otro sistema
    src_crs = str(gdf.crs) if gdf.crs else "?"
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        logger.info("Reproyectando de {a} a EPSG:4326", a=src_crs)
        gdf = gdf.to_crs(epsg=4326)

    col_cve = _resolver_columna(gdf, COLUMNAS_INEGI["cve_ageb"])
    col_ent = _resolver_columna(gdf, COLUMNAS_INEGI["cve_entidad"])
    col_mun = _resolver_columna(gdf, COLUMNAS_INEGI["cve_municipio"])
    col_nmu = _resolver_columna(gdf, COLUMNAS_INEGI["nombre_municipio"])
    col_pob = _resolver_columna(gdf, COLUMNAS_INEGI["poblacion"])

    if not col_cve or not col_ent:
        raise ValueError(
            f"Shapefile no tiene columnas esperables. Disponibles: {list(gdf.columns)}"
        )

    if cve_entidad:
        gdf = gdf[gdf[col_ent].astype(str).str.zfill(2) == cve_entidad].copy()

    insertados = 0
    for _, row in gdf.iterrows():
        cve_ageb_v = str(row[col_cve]).strip()
        cve_ent_v = str(row[col_ent]).zfill(2)
        cve_mun_v = str(row[col_mun]).zfill(3) if col_mun else "000"
        nom_mun_v = row[col_nmu] if col_nmu else None
        pob_v = int(row[col_pob]) if col_pob and row[col_pob] is not None else None
        geom_wkt = row.geometry.wkt if row.geometry is not None else None
        if not geom_wkt:
            continue

        # ST_Multi() del SQL adapta Polygon → MultiPolygon que pide el schema.
        session.execute(
            text(
                """
                INSERT INTO agebs (cve_ageb, cve_entidad, cve_municipio,
                                   nombre_municipio, poblacion_total, geom)
                VALUES (:cve_ageb, :cve_ent, :cve_mun, :nom_mun, :pob,
                        ST_Multi(ST_GeomFromText(:wkt, 4326)))
                ON CONFLICT (cve_ageb) DO UPDATE SET
                  cve_entidad = EXCLUDED.cve_entidad,
                  cve_municipio = EXCLUDED.cve_municipio,
                  nombre_municipio = EXCLUDED.nombre_municipio,
                  poblacion_total = EXCLUDED.poblacion_total,
                  geom = EXCLUDED.geom
                """
            ),
            {
                "cve_ageb": cve_ageb_v,
                "cve_ent": cve_ent_v,
                "cve_mun": cve_mun_v,
                "nom_mun": nom_mun_v,
                "pob": pob_v,
                "wkt": geom_wkt,
            },
        )
        insertados += 1
        if insertados % 1000 == 0:
            session.flush()

    session.commit()

    registrar_operacion(
        session=session,
        tipo_operacion="carga_marco_geoestadistico",
        finalidad=f"Cargar polígonos AGEB INEGI nivel={nivel} para spatial join con establecimientos",
        base_legal="Datos públicos oficiales INEGI Marco Geoestadístico Nacional",
        notas=f"shapefile={path.name} insertados={insertados} filtro_entidad={cve_entidad}",
    )
    session.commit()

    logger.info("AGEBs cargados: {n}", n=insertados)
    return {
        "filas_leidas": len(gdf),
        "filas_insertadas": insertados,
        "encoding_origen": src_crs,
    }


def asignar_ageb_a_establecimientos(session: Session) -> dict[str, Any]:
    """Spatial join: para cada establecimiento con geom, asigna `ageb`
    basado en el polígono AGEB que lo contiene.

    Sólo actualiza cuando ageb es NULL o cambió. Devuelve métricas.
    """
    res = session.execute(
        text(
            """
            UPDATE establecimientos e
               SET ageb = a.cve_ageb
              FROM agebs a
             WHERE e.geom IS NOT NULL
               AND ST_Within(e.geom, a.geom)
               AND (e.ageb IS NULL OR e.ageb != a.cve_ageb)
            """
        )
    )
    actualizados = res.rowcount or 0
    session.commit()

    n_total_con_geom = session.execute(
        text("SELECT COUNT(*) FROM establecimientos WHERE geom IS NOT NULL")
    ).scalar() or 0
    n_con_ageb = session.execute(
        text("SELECT COUNT(*) FROM establecimientos WHERE ageb IS NOT NULL")
    ).scalar() or 0

    registrar_operacion(
        session=session,
        tipo_operacion="spatial_join_agebs",
        finalidad="Asignar cve_ageb a cada establecimiento mediante ST_Within(geom, ageb_geom)",
        base_legal="Datos públicos oficiales INEGI",
        notas=f"actualizados={actualizados} con_ageb_total={n_con_ageb}/{n_total_con_geom}",
    )
    session.commit()

    logger.info(
        "Spatial join: {a} actualizados, {c}/{t} con AGEB",
        a=actualizados,
        c=n_con_ageb,
        t=n_total_con_geom,
    )
    return {
        "actualizados": actualizados,
        "establecimientos_con_ageb": n_con_ageb,
        "establecimientos_con_geom": n_total_con_geom,
        "total_agebs_en_db": session.execute(text("SELECT COUNT(*) FROM agebs")).scalar() or 0,
    }
