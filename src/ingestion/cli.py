"""CLI de descarga DENUE.

Uso:
    # Smoke test — 1 entidad chica + 1 SCIAN, máx 50 registros
    python -m src.ingestion.cli --smoke

    # Descarga real — 1 entidad + 1 SCIAN
    python -m src.ingestion.cli --entidad 23 --scian 311830

    # Descarga completa (las 13 priorizadas × 8 SCIAN — toma ~5 horas)
    python -m src.ingestion.cli --full

    # Cuantificar (gratis, no descarga; útil para dimensionar)
    python -m src.ingestion.cli --cuantificar 311830
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CLI ingestión DENUE")
    parser.add_argument("--cuantificar", help="SCIAN para Cuantificar (no descarga)")
    parser.add_argument("--smoke", action="store_true", help="Descarga muy chica (50 registros)")
    parser.add_argument("--full", action="store_true", help="Descarga completa 13 entidades × 8 SCIAN")
    parser.add_argument("--entidad", action="append", help="Cve INEGI (repetible)")
    parser.add_argument("--scian", action="append", help="SCIAN (repetible)")
    parser.add_argument(
        "--max-total",
        type=int,
        default=None,
        help="Tope de registros por batch (safety net)",
    )
    args = parser.parse_args(argv)

    if args.cuantificar:
        return _cmd_cuantificar(args.cuantificar)

    if args.full:
        return _cmd_descarga(entidades=None, scians=None, max_total=args.max_total)

    if args.smoke:
        return _cmd_descarga(entidades=None, scians=None, max_total=None, smoke=True)

    if args.entidad or args.scian:
        # Validación
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
