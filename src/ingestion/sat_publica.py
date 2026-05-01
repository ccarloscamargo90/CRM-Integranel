"""Cliente de descarga del Listado 69-B del SAT.

Fuente oficial: http://omawww.sat.gob.mx/cifras_sat/Documents/Listado_Completo_69-B.csv

Estructura del CSV (encoding latin-1 / windows-1252):
- Línea 1: aviso legal (multi-línea entre comillas).
- Línea 2: título "Listado completo de contribuyentes (Artículo 69-B del CFF)".
- Línea 3: headers: No, RFC, Nombre del Contribuyente, **Situación del contribuyente**, ...
- Líneas 4+: registros.

Estatus posibles en la columna "Situación":
- "Definitivo"          → confirmado en lista negra (riesgo alto)
- "Presunto"            → bajo investigación
- "Desvirtuado"         → limpió su nombre (NO se considera riesgo)
- "Sentencia Favorable" → ganó sentencia (NO se considera riesgo)

Este cliente sólo descarga + parsea. El cruce con `establecimientos.rfc` y la
actualización de `riesgo_69b` viven en `src/enrichment/cruzar_69b.py`.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import time
from collections.abc import Iterator
from typing import Any

import httpx
from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion
from src.core.models import SatLista69B

SAT_69B_URL = "http://omawww.sat.gob.mx/cifras_sat/Documents/Listado_Completo_69-B.csv"

ESTATUS_RIESGO = {"Definitivo", "Presunto"}
ESTATUS_LIMPIO = {"Desvirtuado", "Sentencia Favorable"}


class SatError(Exception):
    pass


def descargar_csv() -> bytes:
    """Descarga el CSV oficial del SAT. ~5 MB."""
    t0 = time.monotonic()
    with httpx.Client(
        timeout=120.0,
        headers={"User-Agent": "CRM-Granos-MX/0.1 (operacion@intergranel.mx)"},
    ) as cli:
        resp = cli.get(SAT_69B_URL)
    if resp.status_code != 200:
        raise SatError(f"SAT 69-B HTTP {resp.status_code}")
    elapsed = time.monotonic() - t0
    logger.info(
        "SAT 69-B descargado: {b} bytes en {s:.1f}s",
        b=len(resp.content),
        s=elapsed,
    )
    return resp.content


def iter_registros(csv_bytes: bytes) -> Iterator[dict[str, str]]:
    """Itera filas del CSV. Las primeras 2 líneas (aviso + título) se ignoran;
    headers vienen desde la línea 3.

    Devuelve dicts con claves: No, RFC, Nombre, Situacion, fecha_publicacion.
    """
    text_stream = io.StringIO(csv_bytes.decode("latin-1"))
    # Salta las 2 primeras filas (aviso legal y título)
    next(text_stream)
    next(text_stream)
    reader = csv.DictReader(text_stream)
    for row in reader:
        rfc = (row.get("RFC") or "").strip().upper()
        if not rfc:
            continue
        nombre = (row.get("Nombre del Contribuyente") or "").strip()
        situacion = (row.get("Situación del contribuyente") or "").strip()
        # La fecha de publicación más reciente es la del estatus actual.
        # Tomamos la primera fecha disponible en orden de prioridad.
        fecha_pub = None
        for col in (
            "Publicación DOF definitivos",
            "Publicación DOF desvirtuados",
            "Publicación DOF sentencia favorable",
            "Publicación DOF presuntos",
        ):
            valor = (row.get(col) or "").strip()
            if valor:
                fecha_pub = valor
                break
        yield {
            "rfc": rfc,
            "nombre": nombre,
            "situacion": situacion,
            "fecha_publicacion": fecha_pub,
        }


def _parse_fecha(s: str | None) -> dt.date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def upsert_lista_69b(
    session: Session, registros: list[dict[str, Any]]
) -> tuple[int, int]:
    """UPSERT por (rfc, fecha_publicacion). Devuelve (insertados, actualizados)."""
    if not registros:
        return 0, 0
    # Filtrar duplicados dentro del mismo batch (el CSV puede repetir RFC con
    # mismo fecha si tiene varios estados — solo conservamos el primero)
    seen = set()
    deduped = []
    for r in registros:
        key = (r["rfc"], r["fecha_publicacion_dof"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    stmt = pg_insert(SatLista69B).values(deduped)
    upsert = stmt.on_conflict_do_update(
        index_elements=["rfc", "fecha_publicacion_dof"],
        set_={
            "razon_social": stmt.excluded.razon_social,
            "estatus": stmt.excluded.estatus,
        },
    )
    session.execute(upsert)
    session.flush()
    return len(deduped), 0  # SAT no distingue ins vs upd, todo cuenta como ins


def descargar_y_persistir(session: Session) -> dict:
    """Pipeline completo: descarga CSV, parsea, hace upsert.

    Devuelve métricas {filas_recibidas, registros_persistidos, por_estatus}.
    """
    t0 = time.monotonic()
    csv_bytes = descargar_csv()

    registros = []
    por_estatus: dict[str, int] = {}
    for r in iter_registros(csv_bytes):
        por_estatus[r["situacion"]] = por_estatus.get(r["situacion"], 0) + 1
        registros.append(
            {
                "rfc": r["rfc"],
                "razon_social": r["nombre"],
                "estatus": r["situacion"],
                "fecha_publicacion_dof": _parse_fecha(r["fecha_publicacion"]),
            }
        )

    # Upsert en lotes de 5000
    persistidos = 0
    for i in range(0, len(registros), 5000):
        batch = registros[i : i + 5000]
        ins, _ = upsert_lista_69b(session, batch)
        persistidos += ins
        session.commit()

    # Compliance log
    registrar_operacion(
        session=session,
        tipo_operacion="descarga_sat_69b",
        finalidad="Cruce mensual con Listado 69-B SAT para excluir contribuyentes en lista negra",
        base_legal="Información pública oficial del SAT publicada en DOF (Art. 69-B CFF)",
        notas=f"recibidos={len(registros)} persistidos={persistidos} por_estatus={por_estatus}",
    )
    session.commit()

    return {
        "filas_recibidas": len(registros),
        "registros_persistidos": persistidos,
        "por_estatus": por_estatus,
        "duracion_seg": round(time.monotonic() - t0, 2),
    }
