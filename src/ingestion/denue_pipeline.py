"""Pipeline DENUE — descarga ZIP por entidad, filtra SCIAN objetivo, upsert.

Para cada `cve_entidad`:
1. Cliente DENUE descarga el ZIP CSV oficial (1 request, ~3-50 MB).
2. Parser CSV convierte cada fila → dict de Establecimiento, filtra a SCIAN objetivo.
3. Upsert por CLEE en lotes de 1,000: INSERT ... ON CONFLICT (clee) DO UPDATE
   preservando campos manuales (vendedor_id, estado_pipeline, notas, etc.).
4. Tras cada entidad: UPDATE PostGIS para llenar `geom` desde (lat, lon).
5. Fila en `denue_descargas_log` con métricas.
6. Fila en `compliance_log` (descarga_denue) con base legal LFPDPPP.

Idempotente: re-correr no duplica ni pisa campos manuales.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import Boolean, literal_column, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion
from src.core.constantes import ENTIDADES_PRIORIZADAS, SCIAN_PRIMARIOS
from src.core.models import DenueDescargaLog, Establecimiento
from src.ingestion.denue import DenueClient
from src.ingestion.denue_csv_parser import CsvParseError, csv_row_to_establecimiento_dict


@dataclass
class ResumenBatch:
    """Métricas de descarga de una entidad (todos los SCIAN objetivo)."""

    cve_entidad: str
    filas_csv_total: int = 0  # filas del CSV completo (todas las industrias)
    filas_recibidas: int = 0  # filas filtradas a SCIAN objetivo
    filas_insertadas: int = 0
    filas_actualizadas: int = 0
    filas_descartadas: int = 0
    duracion_seg: float = 0.0
    error: str | None = None


@dataclass
class ResumenDescarga:
    """Métricas agregadas de una corrida completa."""

    batches: list[ResumenBatch] = field(default_factory=list)
    fecha_inicio: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    fecha_fin: dt.datetime | None = None

    @property
    def total_recibidos(self) -> int:
        return sum(b.filas_recibidas for b in self.batches)

    @property
    def total_insertados(self) -> int:
        return sum(b.filas_insertadas for b in self.batches)

    @property
    def total_actualizados(self) -> int:
        return sum(b.filas_actualizadas for b in self.batches)

    @property
    def total_descartados(self) -> int:
        return sum(b.filas_descartadas for b in self.batches)

    @property
    def n_errores(self) -> int:
        return sum(1 for b in self.batches if b.error)


# Columnas que el DENUE puede actualizar en cada refresh. Si el operador
# editó manualmente algo (notas, vendedor_id, estado_pipeline, contacto
# capturado en visita), eso NO se pisa.
_COLUMNAS_DENUE = (
    "nombre",
    "nombre_norm",
    "razon_social",
    "scian_codigo",
    "scian_descripcion",
    "tipo_establecimiento",
    "direccion",
    "tipo_vialidad",
    "nombre_vialidad",
    "numero_exterior",
    "numero_interior",
    "colonia",
    "cp",
    "municipio_codigo",
    "localidad",
    "estado",
    "estado_codigo",
    "latitud",
    "longitud",
    "estrato_personal_denue",
    "empleados_est",
    "volumen_estimado_ton_mes",
    "tipo_unidad",
)


def upsert_batch(session: Session, registros: list[dict[str, Any]]) -> tuple[int, int]:
    """UPSERT por CLEE. Devuelve (insertados, actualizados).

    Nota: PostgreSQL no devuelve directamente cuántas filas fueron insertadas
    vs actualizadas en un único INSERT ON CONFLICT. Para distinguirlas
    explotamos `xmax`: en INSERT puro, xmax = 0; en UPDATE, xmax > 0.
    """
    if not registros:
        return 0, 0

    stmt = pg_insert(Establecimiento).values(registros)

    set_dict = {col: getattr(stmt.excluded, col) for col in _COLUMNAS_DENUE}
    set_dict["fecha_actualizacion"] = text("NOW()")
    # `fuentes` es un array — lo unimos para que si ya tenía 'Manual' o
    # 'Google_Places', se preserve junto con 'DENUE_API'.
    set_dict["fuentes"] = text("array(SELECT DISTINCT unnest(establecimientos.fuentes || EXCLUDED.fuentes))")

    inserted_col = literal_column("(xmax = 0)", type_=Boolean()).label("inserted")
    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=["clee"],
        set_=set_dict,
    ).returning(Establecimiento.id, inserted_col)

    rows = session.execute(upsert_stmt).mappings().all()
    insertados = sum(1 for r in rows if r["inserted"])
    actualizados = sum(1 for r in rows if not r["inserted"])
    return insertados, actualizados


def actualizar_geom(session: Session) -> int:
    """Rellena `geom` con ST_MakePoint(lon, lat) donde está NULL pero hay coords.

    Devuelve cuántas filas se actualizaron.
    """
    sql = text(
        """
        UPDATE establecimientos
           SET geom = ST_SetSRID(ST_MakePoint(longitud, latitud), 4326)
         WHERE geom IS NULL
           AND latitud IS NOT NULL
           AND longitud IS NOT NULL
        """
    )
    result = session.execute(sql)
    return result.rowcount or 0


_LOTE_UPSERT = 1000


def descargar_entidad(
    session: Session,
    cli: DenueClient,
    cve_entidad: str,
    *,
    scians: set[str] | None = None,
    max_total: int | None = None,
) -> ResumenBatch:
    """Descarga el ZIP de la entidad, filtra por SCIAN objetivo, upsert.

    `scians`: set de SCIAN a conservar. Default: los 8 SCIAN objetivo (SCIAN_PRIMARIOS).
    `max_total`: tope de filas filtradas a procesar (safety net para tests).
    """
    inicio = time.monotonic()
    res = ResumenBatch(cve_entidad=cve_entidad)
    scians = scians if scians is not None else set(SCIAN_PRIMARIOS)

    try:
        buffer: list[dict[str, Any]] = []
        for row in cli.iter_csv_entidad(cve_entidad, scian_filter=scians):
            res.filas_csv_total += 1
            res.filas_recibidas += 1
            try:
                buffer.append(csv_row_to_establecimiento_dict(row))
            except CsvParseError as e:
                res.filas_descartadas += 1
                logger.warning("CSV parse skip: {err}", err=e)
                continue

            if max_total is not None and res.filas_recibidas >= max_total:
                break

            if len(buffer) >= _LOTE_UPSERT:
                ins, upd = upsert_batch(session, buffer)
                res.filas_insertadas += ins
                res.filas_actualizadas += upd
                buffer.clear()

        if buffer:
            ins, upd = upsert_batch(session, buffer)
            res.filas_insertadas += ins
            res.filas_actualizadas += upd

        actualizar_geom(session)

    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"
        logger.exception("Descarga entidad {cve} falló", cve=cve_entidad)

    res.duracion_seg = round(time.monotonic() - inicio, 2)

    log = DenueDescargaLog(
        fuente="denue_zip_csv",
        endpoint_url=f"denue_{cve_entidad}_csv.zip",
        parametros={
            "cve_entidad": cve_entidad,
            "scians": sorted(scians) if scians else None,
            "max_total": max_total,
        },
        status_http=200 if not res.error else 500,
        bytes_recibidos=None,
        filas_recibidas=res.filas_recibidas,
        filas_insertadas=res.filas_insertadas,
        filas_actualizadas=res.filas_actualizadas,
        filas_descartadas=res.filas_descartadas,
        duracion_ms=int(res.duracion_seg * 1000),
        notas=res.error,
    )
    session.add(log)

    if res.filas_recibidas > 0 and not res.error:
        registrar_operacion(
            session=session,
            tipo_operacion="descarga_denue",
            finalidad=f"Censo DENUE entidad={cve_entidad}, SCIAN={sorted(scians) if scians else 'todos'}",
            base_legal="Fuente de acceso público (DENUE INEGI, datos abiertos)",
            columnas_tocadas=["nombre", "razon_social", "telefono", "email"],
            notas=(
                f"csv_total={res.filas_csv_total} filtrados={res.filas_recibidas} "
                f"ins={res.filas_insertadas} upd={res.filas_actualizadas} "
                f"desc={res.filas_descartadas}"
            ),
        )

    return res


def run_descarga(
    session: Session,
    *,
    entidades: list[str] | None = None,
    scians: list[str] | None = None,
    max_total_por_batch: int | None = None,
    commit_por_batch: bool = True,
) -> ResumenDescarga:
    """Corrida completa o subset.

    `entidades` default = las 13 priorizadas.
    `scians` default = los 8 primarios (filtra dentro del CSV).
    `max_total_por_batch`: safety net para tests / smoke.
    `commit_por_batch=True`: commitea tras cada entidad — tolerancia a fallos.
    """
    entidades = entidades or sorted(ENTIDADES_PRIORIZADAS.keys())
    scians_filter = set(scians) if scians else set(SCIAN_PRIMARIOS)

    resumen = ResumenDescarga()
    logger.info(
        "Inicio descarga DENUE bulk: {n} entidades, filtro {n_sci} SCIAN",
        n=len(entidades),
        n_sci=len(scians_filter),
    )

    with DenueClient() as cli:
        for ent in entidades:
            logger.info("Entidad {ent}", ent=ent)
            res = descargar_entidad(
                session,
                cli,
                ent,
                scians=scians_filter,
                max_total=max_total_por_batch,
            )
            resumen.batches.append(res)

            if commit_por_batch:
                if res.error:
                    session.rollback()
                else:
                    session.commit()

            logger.info(
                "  → csv_total={csv} filtrados={recibidos} ins={ins} upd={upd} desc={desc} {dur}s {err}",
                csv=res.filas_csv_total,
                recibidos=res.filas_recibidas,
                ins=res.filas_insertadas,
                upd=res.filas_actualizadas,
                desc=res.filas_descartadas,
                dur=res.duracion_seg,
                err=f"ERR={res.error}" if res.error else "",
            )

    resumen.fecha_fin = dt.datetime.now(dt.UTC)
    return resumen
