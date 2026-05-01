"""Orquestador de auditoría — corre los chequeos y agrega resultados.

Uso típico:
    from src.audit.runner import run_all
    from src.core.db import SessionLocal

    with SessionLocal() as db:
        reporte = run_all(db, universo="establecimientos:full")
        print(reporte.resumen())
        if reporte.aprobado:
            print("✓ pasa")
        else:
            for h in reporte.errores:
                print(f"✗ {h.chequeo}: {h.total_problemas}/{h.total_evaluados}")
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from src.audit import completeness, contacto, duplicates, geo_anomalies, scian
from src.audit.models import Hallazgo, ReporteAuditoria
from src.core.models import Establecimiento

# Tipo: cada función toma session y devuelve Hallazgo o list[Hallazgo].
_Chequeo = Callable[[Session], Hallazgo | list[Hallazgo]]

# Registro central de chequeos — orden importa para legibilidad del reporte.
CHEQUEOS_DEFAULT: dict[str, _Chequeo] = {
    "duplicates.clee": duplicates.check_clee_duplicates,
    "duplicates.hash_dedup": duplicates.check_hash_duplicates,
    "duplicates.fuzzy": duplicates.check_fuzzy_duplicates,
    "completeness.columnas_criticas": completeness.check_columnas_criticas_pobladas,
    "completeness.pct_null": completeness.check_pct_null_por_columna,
    "completeness.sin_contacto": completeness.check_sin_contacto,
    "geo.coords_nulas": geo_anomalies.check_coords_nulas_o_cero,
    "geo.fuera_bbox_mx": geo_anomalies.check_fuera_bbox_mx,
    "geo.lat_lon_invertidas": geo_anomalies.check_lat_lon_invertidas,
    "geo.geom_vs_lat_lon": geo_anomalies.check_geom_coincide_lat_lon,
    "scian.fuera_objetivo": scian.check_scian_en_objetivo,
    "scian.canal_inconsistente": scian.check_canal_consistente_con_scian,
    "scian.canales_vacio": scian.check_canales_no_vacio,
    "scian.distribucion": scian.conteo_por_scian,
    "contacto.telefono_formato": contacto.check_telefono_formato_mx,
    "contacto.email_formato": contacto.check_email_formato,
    "contacto.direccion_sospechosa": contacto.check_direccion_sospechosa,
    "contacto.anio_alta_denue": contacto.check_anio_alta_denue_razonable,
}


def run_all(
    session: Session,
    *,
    universo: str = "establecimientos:full",
    omitir: set[str] | None = None,
) -> ReporteAuditoria:
    """Corre todos los chequeos default y agrega los hallazgos.

    `omitir`: nombres de chequeos a skip (ej. {"duplicates.fuzzy"} en universos chicos).
    """
    omitir = omitir or set()
    hallazgos: list[Hallazgo] = []

    for nombre, fn in CHEQUEOS_DEFAULT.items():
        if nombre in omitir:
            continue
        resultado = fn(session)
        if isinstance(resultado, list):
            hallazgos.extend(resultado)
        else:
            hallazgos.append(resultado)

    from sqlalchemy import func, select

    total = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()

    return ReporteAuditoria(
        universo=universo,
        total_registros=total,
        hallazgos=hallazgos,
    )


def run_subset(
    session: Session,
    chequeos: list[str],
    *,
    universo: str = "establecimientos:subset",
) -> ReporteAuditoria:
    """Corre solo los chequeos solicitados por nombre."""
    desconocidos = set(chequeos) - set(CHEQUEOS_DEFAULT)
    if desconocidos:
        raise ValueError(f"Chequeos no registrados: {desconocidos}")

    hallazgos: list[Hallazgo] = []
    for nombre in chequeos:
        resultado = CHEQUEOS_DEFAULT[nombre](session)
        if isinstance(resultado, list):
            hallazgos.extend(resultado)
        else:
            hallazgos.append(resultado)

    from sqlalchemy import func, select

    total = session.execute(
        select(func.count()).select_from(Establecimiento)
    ).scalar_one()

    return ReporteAuditoria(
        universo=universo,
        total_registros=total,
        hallazgos=hallazgos,
    )
