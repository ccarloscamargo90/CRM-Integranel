"""Pipeline de enriquecimiento Google Places — D3.B (~$25 USD).

Estrategia:
1. **Selección de candidatos** según D3.B:
   - Todos los AlimentoBalanceado (317)
   - Todas las Asociaciones agropecuarias (2,043)
   - Una muestra de top-decil de Tortillerías ordenada por volumen estimado
   - Sucursales de cadenas detectadas (≥3 establecimientos)
2. **Para cada candidato**: text_search + (si match) place_details + upsert
   en `enriquecimiento_google` y refresh teléfono en `establecimientos` si vacío.
3. **Cache**: si ya tiene `enriquecimiento_google` con match_status='match', skip.
4. **Circuit breaker**: el cliente PlacesClient aborta si excede MONTHLY_BUDGET_USD.

Devuelve métricas: matches, no_matches, gasto_total_usd.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion
from src.core.models import EnriquecimientoGoogle, Establecimiento
from src.enrichment.matching import enriquecer_establecimiento
from src.ingestion.places_api import BudgetExceededError, PlacesClient


@dataclass
class ResumenEnriquecimiento:
    matches: int = 0
    no_matches: int = 0
    skips_cache: int = 0
    errores: int = 0
    gasto_total_usd: float = 0.0
    duracion_seg: float = 0.0
    establecimientos_evaluados: list[int] = field(default_factory=list)
    primer_error: str | None = None


def _ya_enriquecido(session: Session, est_id: int) -> bool:
    """True si ya hay un row de enriquecimiento_google (cualquier match_status).

    Skipea tanto matches (no re-pagar por place_details que ya tenemos) como
    no_matches (no re-intentar contra Google si ya determinamos que no hay
    coincidencia razonable). Para forzar re-intento, borrar la fila de
    enriquecimiento_google manualmente.
    """
    stmt = select(EnriquecimientoGoogle).where(
        EnriquecimientoGoogle.establecimiento_id == est_id
    )
    return session.execute(stmt).scalar_one_or_none() is not None


def seleccionar_candidatos_d3b(
    session: Session,
    *,
    max_tortillerias: int = 0,
    max_cadenas: int = 300,
    solo_priorizados: bool = True,
) -> list[Establecimiento]:
    """Selección D3.B priorizada: ~3,000 establecimientos para ~$15 USD.

    Orden de prioridad:
    1. Todos los AlimentoBalanceado (317).
    2. Todas las AsociacionesAgropecuarias (2,043).
    3. Sucursales de las top `max_cadenas` cadenas más grandes.
    4. Top `max_tortillerias` tortillerías por volumen estimado.

    Las cadenas chicas (≤2 sucursales) y la mayoría de tortillerías se
    enriquecen on-demand cuando un vendedor las necesite (Fase 8 endpoint).
    """
    todos: list[Establecimiento] = []
    seen_ids: set[int] = set()

    def _add(rows: list[Establecimiento]) -> None:
        for r in rows:
            if r.id not in seen_ids:
                todos.append(r)
                seen_ids.add(r.id)

    base_filter = []
    if solo_priorizados:
        from src.core.constantes import CVE_ENTIDADES_PRIORIZADAS

        base_filter.append(Establecimiento.estado_codigo.in_(CVE_ENTIDADES_PRIORIZADAS))

    # 1. CADENAS PRIMERO (corporativas + locales). Si el job se interrumpe,
    # al menos las cadenas (que son los clientes corporativos de mayor valor)
    # quedan procesadas.
    from src.core.models import Cadena

    top_cadenas_ids = session.execute(
        select(Cadena.id)
        .where(Cadena.tipo.in_(["cadena_corporativa", "cadena_local"]))
        .order_by(Cadena.sucursales_count.desc())
        .limit(max_cadenas)
    ).scalars().all()
    if top_cadenas_ids:
        rows = session.execute(
            select(Establecimiento)
            .where(Establecimiento.cadena_id.in_(top_cadenas_ids), *base_filter)
        ).scalars().all()
        _add(list(rows))
        logger.info(
            "Candidatos top {tc} cadenas (corporativas+locales): {n} sucursales",
            tc=max_cadenas, n=len(rows),
        )

    # 2. AlimentoBalanceado (clientes industriales — Bachoco, Purina, etc.)
    rows = session.execute(
        select(Establecimiento)
        .where(Establecimiento.canales.any("AlimentoBalanceado"), *base_filter)
    ).scalars().all()
    _add(list(rows))
    logger.info("Candidatos AlimentoBalanceado: {n}", n=len(rows))

    # 3. AsociacionesAgropecuarias (volumen alto pero match rate bajo)
    rows = session.execute(
        select(Establecimiento)
        .where(Establecimiento.canales.any("AsociacionesAgropecuarias"), *base_filter)
    ).scalars().all()
    _add(list(rows))
    logger.info("Candidatos Asociaciones: {n}", n=len(rows))

    # 4. Top tortillerías por volumen
    rows = session.execute(
        select(Establecimiento)
        .where(
            Establecimiento.canales.any("Tortillerias"),
            Establecimiento.volumen_estimado_ton_mes.is_not(None),
            *base_filter,
        )
        .order_by(Establecimiento.volumen_estimado_ton_mes.desc())
        .limit(max_tortillerias)
    ).scalars().all()
    _add(list(rows))
    logger.info("Candidatos Tortillerias top-volumen: {n}", n=len(rows))

    logger.info("Total candidatos D3.B (deduplicados): {n}", n=len(todos))
    return todos


def run_enriquecimiento(
    session: Session,
    *,
    candidatos: list[Establecimiento] | None = None,
    max_total: int | None = None,
    commit_cada: int = 50,
) -> ResumenEnriquecimiento:
    """Corre enriquecimiento para `candidatos` (o D3.B default)."""
    if candidatos is None:
        candidatos = seleccionar_candidatos_d3b(session)

    if max_total is not None:
        candidatos = candidatos[:max_total]

    res = ResumenEnriquecimiento()
    inicio = time.monotonic()

    with PlacesClient(session=session) as cli:
        gasto_inicio = cli.gasto_mes_actual()
        logger.info("Inicio enriquecimiento. Gasto del mes (antes): ${g:.4f} USD", g=gasto_inicio)

        for i, est in enumerate(candidatos, start=1):
            res.establecimientos_evaluados.append(est.id)

            if _ya_enriquecido(session, est.id):
                res.skips_cache += 1
                continue

            try:
                enriq = enriquecer_establecimiento(session, cli, est)
                if enriq.match_status == "match":
                    res.matches += 1
                else:
                    res.no_matches += 1
            except BudgetExceededError as e:
                logger.warning("Budget exceeded — paro enriquecimiento: {e}", e=e)
                res.primer_error = str(e)
                session.rollback()
                break
            except Exception as e:
                res.errores += 1
                if not res.primer_error:
                    res.primer_error = f"{type(e).__name__}: {e}"
                logger.warning("Error enriqueciendo {id}: {e}", id=est.id, e=e)
                # Rollback para evitar PendingRollbackError en siguientes flushes
                try:
                    session.rollback()
                except Exception:
                    pass

            if i % commit_cada == 0:
                session.commit()
                logger.info(
                    "Progreso: {i}/{total} — matches={m} no_match={n} skips={s} err={e}",
                    i=i, total=len(candidatos),
                    m=res.matches, n=res.no_matches, s=res.skips_cache, e=res.errores,
                )

        gasto_fin = cli.gasto_mes_actual()
        res.gasto_total_usd = round(gasto_fin - gasto_inicio, 4)

    res.duracion_seg = round(time.monotonic() - inicio, 2)

    # Compliance log
    if res.matches + res.no_matches > 0:
        registrar_operacion(
            session=session,
            tipo_operacion="enriquecimiento_google",
            finalidad=(
                "Enriquecer prospectos D3.B con datos verificados Google Places "
                "(rating, horarios, teléfono actualizado, sitio web). "
                "Estrategia: AlimentoBalanceado + Asociaciones + cadenas + top tortillerías"
            ),
            base_legal="Fuente de acceso público (Google Places API oficial, ToS aceptados)",
            columnas_tocadas=["telefono", "google_phone"],
            notas=(
                f"matches={res.matches} no_match={res.no_matches} "
                f"skips_cache={res.skips_cache} errores={res.errores} "
                f"gasto_usd={res.gasto_total_usd}"
            ),
        )

    session.commit()
    return res
