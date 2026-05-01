"""CLI de ingestión y enriquecimiento.

Uso:
    # Descarga DENUE
    python -m src.ingestion.cli --smoke                      # Campeche, 100 filas
    python -m src.ingestion.cli --entidad 23                 # 1 entidad
    python -m src.ingestion.cli --full                       # 13 entidades, ~4 min
    python -m src.ingestion.cli --cuantificar 311830         # gratis

    # Detección de cadenas
    python -m src.ingestion.cli --detectar-cadenas

    # Enriquecimiento Google Places (D3.B, ~$25 USD)
    python -m src.ingestion.cli --enriquecer                 # selección D3.B completa
    python -m src.ingestion.cli --enriquecer --max-total 10  # smoke ~$0.18

    # Reporte de gasto Google Places del mes
    python -m src.ingestion.cli --gasto
"""

from __future__ import annotations

import argparse
import sys

from src.core.constantes import (
    CVE_ENTIDADES_PRIORIZADAS,
    SCIAN_PRIMARIOS,
)
from src.core.db import SessionLocal
from src.core.logging import setup_logging
from src.ingestion.denue import DenueClient
from src.ingestion.denue_pipeline import run_descarga


def _cmd_cuantificar(scian: str) -> int:
    setup_logging()
    with DenueClient() as cli:
        totales = cli.cuantificar(scian, area="0", estrato="0")
    if not totales:
        print(f"Sin resultados para SCIAN {scian}")
        return 1
    total_mx = sum(totales.values())
    total_priorizados = sum(v for k, v in totales.items() if k in CVE_ENTIDADES_PRIORIZADAS)
    print(f"\nSCIAN {scian}")
    print(f"  Total nacional       : {total_mx:>10,}")
    print(f"  En 13 priorizadas    : {total_priorizados:>10,}")
    print("\nPor entidad priorizada:")
    for ent in sorted(CVE_ENTIDADES_PRIORIZADAS, key=lambda e: -totales.get(e, 0)):
        v = totales.get(ent, 0)
        print(f"  {ent}  {v:>10,}")
    return 0


def _cmd_descarga(
    *,
    entidades: list[str] | None,
    scians: list[str] | None,
    max_total: int | None,
    smoke: bool = False,
) -> int:
    setup_logging()
    if smoke:
        # Smoke: 1 entidad chica (Campeche, ~3.8 MB ZIP), todos los SCIAN objetivo,
        # tope 100 filas para terminar rápido.
        entidades = ["04"]
        scians = None
        max_total = 100

    with SessionLocal() as session:
        resumen = run_descarga(
            session,
            entidades=entidades,
            scians=scians,
            max_total_por_batch=max_total,
        )

    print("\n=== Resumen de descarga ===")
    print(f"Total recibidos    : {resumen.total_recibidos:,}")
    print(f"Total insertados   : {resumen.total_insertados:,}")
    print(f"Total actualizados : {resumen.total_actualizados:,}")
    print(f"Total descartados  : {resumen.total_descartados:,}")
    print(f"Batches con error  : {resumen.n_errores}")
    print(f"Duración total     : {(resumen.fecha_fin - resumen.fecha_inicio).total_seconds():.1f}s")

    if resumen.n_errores > 0:
        print("\nErrores:")
        for b in resumen.batches:
            if b.error:
                print(f"  entidad {b.cve_entidad} → {b.error}")
        return 2
    return 0


def _cmd_detectar_cadenas(*, incluir_marca: bool = False) -> int:
    setup_logging()
    from src.enrichment.cadenas import detectar_cadenas, listar_top_cadenas

    with SessionLocal() as session:
        metricas = detectar_cadenas(session, incluir_marca_residual=incluir_marca)
        session.commit()

        print("\n=== Resumen ===")
        print(f"Cadenas corporativas (por razón social):  {metricas['cadenas_corporativas']:,}")
        print(f"  Sucursales vinculadas:                  {metricas['sucursales_corporativas']:,}")
        print(f"Cadenas locales (mismo mun+nombre):       {metricas['cadenas_locales']:,}")
        print(f"  Sucursales vinculadas:                  {metricas['sucursales_locales']:,}")
        if incluir_marca:
            print(f"Cadenas heurísticas (por marca):          {metricas['cadenas_heuristicas']:,}")
            print(f"  Sucursales vinculadas:                  {metricas['sucursales_heuristicas']:,}")

        print("\n=== Top 20 cadenas ===")
        for c in listar_top_cadenas(session, top=20):
            print(
                f"  {c['n_sucursales']:>4} suc  {c['n_estados']} edos  | "
                f"{(c['canal'] or '?'):<25} | {c['nombre_grupo'][:50]}"
            )
    return 0


def _cmd_enriquecer(*, max_total: int | None) -> int:
    setup_logging()
    from src.enrichment.places_pipeline import run_enriquecimiento

    with SessionLocal() as session:
        resumen = run_enriquecimiento(session, max_total=max_total)

    print("\n=== Resumen enriquecimiento Google Places ===")
    print(f"Establecimientos evaluados : {len(resumen.establecimientos_evaluados):,}")
    print(f"Matches                    : {resumen.matches:,}")
    print(f"No matches                 : {resumen.no_matches:,}")
    print(f"Skips por cache            : {resumen.skips_cache:,}")
    print(f"Errores                    : {resumen.errores:,}")
    print(f"Gasto USD esta corrida     : ${resumen.gasto_total_usd:.4f}")
    print(f"Duración                   : {resumen.duracion_seg:.1f}s")
    if resumen.primer_error:
        print(f"Primer error               : {resumen.primer_error}")
    return 0 if resumen.errores == 0 else 2


def _cmd_cargar_agebs(shp_path: str, cve_entidad: str | None = None) -> int:
    setup_logging()
    from src.ingestion.marco_geoestadistico import cargar_shapefile_a_agebs

    with SessionLocal() as session:
        m = cargar_shapefile_a_agebs(session, shp_path, cve_entidad=cve_entidad)
    print("\n=== AGEBs cargados ===")
    print(f"Filas leídas:      {m.get('filas_leidas',0):,}")
    print(f"Filas insertadas:  {m.get('filas_insertadas',0):,}")
    print(f"Encoding origen:   {m.get('encoding_origen','?')}")
    return 0


def _cmd_asignar_agebs() -> int:
    setup_logging()
    from src.ingestion.marco_geoestadistico import asignar_ageb_a_establecimientos

    with SessionLocal() as session:
        m = asignar_ageb_a_establecimientos(session)
    print("\n=== Spatial join establecimientos ↔ AGEBs ===")
    print(f"AGEBs en DB:                 {m['total_agebs_en_db']:,}")
    print(f"Establecimientos con geom:   {m['establecimientos_con_geom']:,}")
    print(f"  → asignados a AGEB:        {m['establecimientos_con_ageb']:,}")
    print(f"  → actualizados esta corrida:{m['actualizados']:,}")
    return 0


def _cmd_cargar_indicadores() -> int:
    setup_logging()
    from src.ingestion.inegi_indicadores import cargar_desde_seed

    with SessionLocal() as session:
        m = cargar_desde_seed(session)

    print("\n=== Indicadores geográficos cargados ===")
    print(f"Total upserteados: {m['upserteados']:,}")
    print("Por indicador:")
    for ind, n in sorted(m["por_indicador"].items(), key=lambda x: -x[1]):
        print(f"  {ind:<45} {n:>3}")
    return 0


def _cmd_descargar_69b() -> int:
    setup_logging()
    from src.ingestion.sat_publica import descargar_y_persistir

    with SessionLocal() as session:
        m = descargar_y_persistir(session)

    print("\n=== SAT Listado 69-B descargado ===")
    print(f"Filas recibidas:         {m['filas_recibidas']:,}")
    print(f"Registros persistidos:   {m['registros_persistidos']:,}")
    print(f"Duración:                {m['duracion_seg']}s")
    print("Por estatus:")
    for est, n in sorted(m["por_estatus"].items(), key=lambda x: -x[1]):
        print(f"  {est:<25} {n:>5,}")
    return 0


def _cmd_cruzar_69b() -> int:
    setup_logging()
    from src.enrichment.cruzar_69b import cruzar_riesgo_69b

    with SessionLocal() as session:
        m = cruzar_riesgo_69b(session)

    print("\n=== Cruce 69-B ===")
    print(f"Establecimientos con RFC:    {m['total_con_rfc']:,}")
    print(f"Establecimientos con razón:  {m['total_con_razon']:,}")
    print(f"Lista 69-B en DB:            {m['total_lista_69b']:,}")
    print(f"  → marcados por RFC exacto: {m['marcados_por_rfc']:,}")
    print(f"  → marcados por razón:      {m['marcados_por_razon']:,}")
    print(f"  → TOTAL marcados riesgo:   {m['marcados_riesgo']:,}")
    print(f"  → limpiados (ya no riesgo):{m['limpiados']:,}")
    return 0


def _cmd_gasto() -> int:
    setup_logging()
    from src.ingestion.places_api import _gasto_mes_actual_usd

    with SessionLocal() as session:
        gasto = _gasto_mes_actual_usd(session)
        from src.core.config import get_settings

        budget = get_settings().MONTHLY_BUDGET_USD
        print(f"Gasto Google Places este mes: ${gasto:.4f} USD")
        print(f"Presupuesto MONTHLY_BUDGET_USD: ${budget:.2f} USD")
        print(f"Disponible: ${budget - gasto:.4f} USD ({100*(1-gasto/budget):.1f}%)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CLI ingestión + enriquecimiento")
    # Ingesta DENUE
    parser.add_argument("--cuantificar", help="SCIAN para Cuantificar (no descarga)")
    parser.add_argument("--smoke", action="store_true", help="Descarga muy chica (50 registros)")
    parser.add_argument("--full", action="store_true", help="Descarga completa 13 entidades")
    parser.add_argument("--entidad", action="append", help="Cve INEGI (repetible)")
    parser.add_argument("--scian", action="append", help="SCIAN (repetible)")

    # Enriquecimiento
    parser.add_argument("--enriquecer", action="store_true", help="Enriquecimiento D3.B con Google Places")
    parser.add_argument("--detectar-cadenas", action="store_true", help="Detectar cadenas por razón social")
    parser.add_argument("--incluir-marca", action="store_true", help="También usar heurística de marca residual (ruidosa)")
    parser.add_argument("--descargar-69b", action="store_true", help="Descarga Lista 69-B SAT y persiste en DB")
    parser.add_argument("--cruzar-69b", action="store_true", help="Cruce establecimientos.rfc vs lista 69-B SAT")
    parser.add_argument("--cargar-indicadores", action="store_true", help="Carga indicadores geográficos desde seed YAML")
    parser.add_argument("--cargar-agebs", help="Path a shapefile INEGI Marco Geoestadístico para cargar")
    parser.add_argument("--cve-entidad", help="Filtra carga AGEB a una entidad (ej. 22)")
    parser.add_argument("--asignar-agebs", action="store_true", help="Spatial join establecimientos ↔ agebs")
    parser.add_argument("--gasto", action="store_true", help="Reporta gasto del mes en Google Places")

    parser.add_argument(
        "--max-total",
        type=int,
        default=None,
        help="Tope de registros (descarga o enriquecimiento)",
    )
    args = parser.parse_args(argv)

    if args.cuantificar:
        return _cmd_cuantificar(args.cuantificar)
    if args.gasto:
        return _cmd_gasto()
    if args.descargar_69b:
        return _cmd_descargar_69b()
    if args.cruzar_69b:
        return _cmd_cruzar_69b()
    if args.cargar_indicadores:
        return _cmd_cargar_indicadores()
    if args.cargar_agebs:
        return _cmd_cargar_agebs(args.cargar_agebs, cve_entidad=args.cve_entidad)
    if args.asignar_agebs:
        return _cmd_asignar_agebs()
    if args.detectar_cadenas:
        return _cmd_detectar_cadenas(incluir_marca=args.incluir_marca)
    if args.enriquecer:
        return _cmd_enriquecer(max_total=args.max_total)
    if args.full:
        return _cmd_descarga(entidades=None, scians=None, max_total=args.max_total)
    if args.smoke:
        return _cmd_descarga(entidades=None, scians=None, max_total=None, smoke=True)
    if args.entidad or args.scian:
        ent = args.entidad or sorted(CVE_ENTIDADES_PRIORIZADAS)
        sci = args.scian or sorted(SCIAN_PRIMARIOS)
        invalidas = set(ent) - CVE_ENTIDADES_PRIORIZADAS
        if invalidas:
            print(f"⚠️  Entidades fuera de las 13 priorizadas: {invalidas}", file=sys.stderr)
        return _cmd_descarga(entidades=ent, scians=sci, max_total=args.max_total)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
