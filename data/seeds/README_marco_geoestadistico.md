# Marco Geoestadístico INEGI — guía operativa

INEGI publica shapefiles oficiales con polígonos AGEB / municipales /
estatales. Esos polígonos no se versionan en este repo (pesan 50-200 MB
por entidad, ~3 GB todo el país). Esta guía explica cómo descargar
manualmente los que necesites y cargarlos a la tabla `agebs`.

## 1. Descarga (manual)

1. Ve al catálogo oficial: <https://www.inegi.org.mx/temas/mg/>
2. Selecciona la entidad y haz clic en **"Áreas Geoestadísticas Básicas (AGEB) urbanas y rurales"** (o municipal, según necesites).
3. Descarga el ZIP. Guárdalo en `data/raw/marco_geoestadistico/<cve_entidad>/`.

> Tip: para el caso de uso de Intergranel, AGEB urbano cubre las cabeceras
> municipales donde están las tortillerías de ciudad; AGEB rural cubre
> los pueblos donde están las forrajeras y asociaciones ganaderas.

## 2. Extracción

```bash
cd data/raw/marco_geoestadistico/22  # ejemplo: Querétaro
unzip <archivo>.zip
ls *.shp        # localiza el shapefile principal
```

El archivo importante es `*_a.shp` (AGEB urbano) o `*_ar.shp` (AGEB rural).
Los archivos `.shx`, `.dbf`, `.prj` deben quedar en la misma carpeta.

## 3. Carga a Postgres

```bash
python -m src.ingestion.cli --cargar-agebs data/raw/marco_geoestadistico/22/conjunto_de_datos/22a.shp
```

El loader:
- Detecta el sistema de coordenadas (LCC México o similar) desde el `.prj`
  y reproyecta a EPSG:4326 (WGS84) si es necesario.
- Detecta columnas comunes (`CVEGEO`, `CVE_ENT`, `CVE_MUN`, `POBTOT`, etc.).
- Hace UPSERT por `cve_ageb` — re-correr no duplica.
- Registra la operación en `compliance_log`.

Tiempo típico: 30-90 segundos por entidad chica, 3-5 min para EdoMex.

## 4. Spatial join con establecimientos

```bash
python -m src.ingestion.cli --asignar-agebs
```

PostGIS ejecuta `ST_Within(establecimientos.geom, agebs.geom)` y actualiza
`establecimientos.ageb` con el `cve_ageb` del polígono que contiene cada
establecimiento. Idempotente y rápido (~10 segundos para 136K
establecimientos si los índices GIST están creados).

## 5. Validación

```sql
-- Cobertura: cuántos establecimientos quedaron con AGEB asignada
SELECT estado_codigo, estado,
       COUNT(*) AS total,
       COUNT(ageb) AS con_ageb,
       ROUND(100.0 * COUNT(ageb) / COUNT(*), 1) AS pct
FROM establecimientos
WHERE estado_codigo IN ('22','11','01')  -- estados ya cargados
GROUP BY estado_codigo, estado
ORDER BY pct DESC;
```

Si la cobertura es baja (<90%), revisar:
- ¿Las coords del establecimiento están dentro de los polígonos AGEB?
  Algunos prospectos tienen coordenadas (0, 0) o fuera del bbox.
- ¿El sistema de coordenadas se reproyectó correctamente? Comprobar con:
  `SELECT ST_SRID(geom) FROM establecimientos LIMIT 1;` debe devolver `4326`.

## 6. Refresh

INEGI actualiza el Marco Geoestadístico anualmente. Para refrescar:
1. Re-descarga el ZIP de la nueva versión.
2. Re-corre `--cargar-agebs <path>` (UPSERT actualiza geometría y población).
3. Re-corre `--asignar-agebs` (spatial join queda al día).
