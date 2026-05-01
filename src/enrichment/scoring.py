"""Algoritmo de scoring de prospectos — Fase 6.

Devuelve un score 0-100 por establecimiento con dispatch por canal.

Diseño:
- Cada componente del score es una función pura `(contexto) -> float`.
- Pesos por canal viven en `PESOS_POR_CANAL` (ajustables sin tocar código).
- Bonificaciones (cadenas, etiquetas CONAFAB, etc.) suman puntos extra.
- Riesgo 69-B desactiva el score (segmento_abc = 'X').

Inputs por establecimiento:
- `Establecimiento` (canales, tipo, empleados_est, anio_alta_denue, etiquetas, etc.)
- `EnriquecimientoGoogle` opcional (rating, user_rating_count)
- Indicador `pct_pobreza` por entidad (proxy capacidad de compra)
- `Cadena` opcional (sucursales_count, tipo)

Output:
- `score_prioridad`: 0-100 (puede exceder con bonificaciones, lo capamos a 100)
- `segmento_abc`: A (top 20%), B (20-60%), C (resto), X (incompleto)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion


@dataclass
class ContextoScoring:
    """Datos cacheados para no consultar DB por cada establecimiento."""
    pct_pobreza_por_entidad: dict[str, float]  # {cve_ent: pct}


# =============================================================================
# Pesos por canal (suman 100 base; bonificaciones se aplican aparte)
# =============================================================================
PESOS_POR_CANAL: dict[str, dict[str, float]] = {
    "Tortillerias": {
        "tamano": 20,
        "antiguedad": 10,
        "volumen_google": 25,
        "pobreza_inv": 10,        # mayor capacidad de compra → +score
        "contacto": 10,
        "consumo_per_capita": 10, # entidad de alto consumo tortilla → +score
        "cadena": 15,             # tener cadena_id → +score
    },
    "AlimentoBalanceado": {
        "tamano": 35,             # escala industrial domina
        "antiguedad": 10,
        "volumen_google": 5,      # B2B casi sin reviews
        "contacto": 15,
        "cadena": 10,
        "produccion_maiz": 25,    # entidad con producción alta → cliente regional
    },
    "ForrajerasPecuario": {
        "tamano": 25,
        "antiguedad": 10,
        "volumen_google": 15,     # rurales visibles en Maps
        "contacto": 15,
        "produccion_maiz": 15,    # zonas productoras compran insumo
        "cadena": 10,
        "pobreza_inv": 10,
    },
    "AsociacionesAgropecuarias": {
        "tamano": 15,
        "antiguedad": 5,
        "volumen_google": 5,
        "contacto": 15,
        "produccion_maiz": 25,    # asociaciones en zonas de producción
        "cadena": 5,
        "pobreza_inv": 5,
        "presencia_estatal": 25,  # cámara con presencia multi-estado
    },
}

# Bonificaciones por etiqueta (suman al score base)
BONUS_ETIQUETAS: dict[str, int] = {
    "CONAFAB": 15,
    "PECUARIO_GRANDE": 10,
    "HARINERO_INDUSTRIAL": 10,
}


def _normalizar_pct(valor: float, max_v: float, min_v: float = 0) -> float:
    """Convierte un valor a 0-100 lineal contra el rango (min_v, max_v)."""
    if max_v == min_v:
        return 50.0
    pct = (valor - min_v) / (max_v - min_v) * 100
    return max(0.0, min(100.0, pct))


def _puntaje_tamano(empleados_est: int | None) -> float:
    """0-100 según punto medio empleados DENUE. Cap a 100 en estrato top."""
    if empleados_est is None:
        return 0
    # Empleados van de 3 a 350. Logaritmo para suavizar la cola larga.
    return _normalizar_pct(math.log10(max(empleados_est, 1) + 1), math.log10(351))


def _puntaje_antiguedad(anio_alta_denue: int | None, anio_actual: int = 2026) -> float:
    """Mayor antigüedad → mayor puntaje (negocio establecido)."""
    if anio_alta_denue is None:
        return 0
    anios = max(0, anio_actual - anio_alta_denue)
    if anios >= 10:
        return 100
    if anios >= 5:
        return 70
    if anios >= 2:
        return 40
    return 20


def _puntaje_volumen_google(
    rating: float | None, user_rating_count: int | None
) -> float:
    """rating × log(reviews), normalizado a 0-100.

    Rating de 5.0 con 1000+ reviews → 100. Sin reviews → 0.
    """
    if rating is None or user_rating_count is None or user_rating_count == 0:
        return 0
    # Bonus si rating ≥ 4.0
    base_rating = (rating / 5.0) * 100  # 0-100
    log_rev = math.log10(user_rating_count + 1) / math.log10(1001)  # 0-1
    return base_rating * log_rev


def _puntaje_pobreza_inversa(pct_pobreza: float | None) -> float:
    """Menor pobreza → mayor capacidad compra → mayor score.

    Rango pobreza MX: 24% (CDMX/AGS) - 67% (Chiapas).
    """
    if pct_pobreza is None:
        return 50
    # Invertimos: 24% pobreza → score 100, 67% pobreza → score 0
    return max(0, min(100, (67 - pct_pobreza) / (67 - 24) * 100))


def _puntaje_contacto(est: Any) -> float:
    """Tener teléfono Y dirección Y email/web aporta."""
    score = 0
    if est.telefono:
        score += 40
    if est.direccion:
        score += 30
    if est.email or est.sitio_web:
        score += 30
    return score


def _puntaje_cadena(cadena_sucursales: int | None) -> float:
    """Cadena con más sucursales → más valor estratégico."""
    if cadena_sucursales is None or cadena_sucursales <= 1:
        return 0
    if cadena_sucursales >= 50:
        return 100
    if cadena_sucursales >= 20:
        return 70
    if cadena_sucursales >= 10:
        return 50
    if cadena_sucursales >= 3:
        return 30
    return 0


# Producción nacional aprox 21M ton — usamos para normalizar
_PRODUCCION_MAIZ_MAX = 1_750_000


def _puntaje_produccion_maiz(prod_ton: float | None) -> float:
    if prod_ton is None or prod_ton <= 0:
        return 0
    return _normalizar_pct(math.log10(prod_ton), math.log10(_PRODUCCION_MAIZ_MAX))


def _puntaje_consumo(consumo_kg: float | None) -> float:
    if consumo_kg is None:
        return 50
    # Rango 67-92 kg observado
    return _normalizar_pct(consumo_kg, 92, 67)


def _puntaje_presencia_estatal(n_estados_cadena: int | None) -> float:
    """Para Asociaciones: una cámara con presencia en 13+ estados es nacional."""
    if n_estados_cadena is None or n_estados_cadena <= 1:
        return 0
    return min(100, n_estados_cadena * 10)


def calcular_score_individual(
    est: Any,
    enriq: Any | None,
    cadena: Any | None,
    contexto: ContextoScoring,
    indicadores_entidad: dict[str, float],
) -> tuple[float, str | None]:
    """Devuelve (score 0-100, motivo_si_descartado).

    `indicadores_entidad` esperado: {pct_pobreza, consumo_tortilla_kg_per_capita_anio,
    produccion_maiz_grano_blanco_ton}.
    """
    # 1) Riesgo 69-B descalifica
    if est.riesgo_69b:
        return 0.0, "riesgo_69b"

    # 2) Determinar canal principal (primero del array `canales`)
    canales = est.canales or []
    if not canales:
        return 0.0, "sin_canal"
    canal = canales[0]

    pesos = PESOS_POR_CANAL.get(canal)
    if pesos is None:
        return 0.0, f"canal_desconocido_{canal}"

    # 3) Calcular cada componente y aplicar peso
    componentes = {
        "tamano": _puntaje_tamano(est.empleados_est),
        "antiguedad": _puntaje_antiguedad(est.anio_alta_denue),
        "volumen_google": _puntaje_volumen_google(
            enriq.google_rating if enriq else None,
            enriq.google_user_rating_count if enriq else None,
        ),
        "contacto": _puntaje_contacto(est),
        "cadena": _puntaje_cadena(cadena.sucursales_count if cadena else None),
        "pobreza_inv": _puntaje_pobreza_inversa(indicadores_entidad.get("pct_pobreza")),
        "consumo_per_capita": _puntaje_consumo(
            indicadores_entidad.get("consumo_tortilla_kg_per_capita_anio")
        ),
        "produccion_maiz": _puntaje_produccion_maiz(
            indicadores_entidad.get("produccion_maiz_grano_blanco_ton")
        ),
        "presencia_estatal": 0,  # se calcula con queries adicionales si se requiere
    }

    score = sum(pesos.get(k, 0) * componentes[k] / 100 for k in pesos)

    # 4) Bonificaciones por etiquetas
    for et in (est.etiquetas or []):
        score += BONUS_ETIQUETAS.get(et, 0)

    return min(100.0, round(score, 2)), None


def _construir_contexto(session: Session) -> ContextoScoring:
    rows = session.execute(
        text(
            "SELECT cve, valor FROM indicadores_geograficos "
            "WHERE nivel='entidad' AND indicador='pct_pobreza'"
        )
    ).all()
    pct = {r.cve: float(r.valor) for r in rows}
    return ContextoScoring(pct_pobreza_por_entidad=pct)


def _indicadores_por_entidad(session: Session) -> dict[str, dict[str, float]]:
    """Devuelve {cve_ent: {indicador: valor}}."""
    rows = session.execute(
        text(
            "SELECT cve, indicador, valor FROM indicadores_geograficos "
            "WHERE nivel='entidad'"
        )
    ).all()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        out.setdefault(r.cve, {})[r.indicador] = float(r.valor)
    return out


def calcular_scores_universo(session: Session, *, batch_size: int = 1000) -> dict[str, Any]:
    """Calcula score_prioridad y segmento_abc para todos los establecimientos.

    Carga en memoria los indicadores por entidad (rápido, son pocos).
    Itera establecimientos en batches con sus enriquecimientos y cadenas.
    """
    indicadores = _indicadores_por_entidad(session)
    contexto = _construir_contexto(session)

    n_total = session.execute(text("SELECT COUNT(*) FROM establecimientos")).scalar() or 0
    logger.info("Calculando score para {n} establecimientos", n=n_total)

    actualizados = 0
    descartados = 0
    distribucion: dict[str, int] = {"A": 0, "B": 0, "C": 0, "X": 0}

    # Cargamos todo a la vez con join. Para 136K filas es viable.
    rows = session.execute(
        text(
            """
            SELECT e.id, e.canales, e.estado_codigo, e.empleados_est,
                   e.anio_alta_denue, e.telefono, e.direccion, e.email,
                   e.sitio_web, e.etiquetas, e.riesgo_69b,
                   eg.google_rating, eg.google_user_rating_count,
                   c.sucursales_count
            FROM establecimientos e
            LEFT JOIN enriquecimiento_google eg
              ON eg.establecimiento_id = e.id AND eg.match_status = 'match'
            LEFT JOIN cadenas c ON c.id = e.cadena_id
            """
        )
    ).all()

    # Para asignar segmento ABC, necesitamos el universo completo de scores.
    # Calculamos scores primero, luego percentiles.
    scores_por_id: dict[int, tuple[float, str | None]] = {}

    class _Est:
        """Adaptador para presentar Row como objeto con atributos."""
        def __init__(self, r):
            self.id = r.id
            self.canales = r.canales
            self.empleados_est = r.empleados_est
            self.anio_alta_denue = r.anio_alta_denue
            self.telefono = r.telefono
            self.direccion = r.direccion
            self.email = r.email
            self.sitio_web = r.sitio_web
            self.etiquetas = r.etiquetas
            self.riesgo_69b = r.riesgo_69b

    class _Enriq:
        def __init__(self, rating, count):
            self.google_rating = rating
            self.google_user_rating_count = count

    class _Cadena:
        def __init__(self, sucursales_count):
            self.sucursales_count = sucursales_count

    for r in rows:
        est_obj = _Est(r)
        enriq_obj = _Enriq(r.google_rating, r.google_user_rating_count) if r.google_rating else None
        cadena_obj = _Cadena(r.sucursales_count) if r.sucursales_count else None
        ind_ent = indicadores.get(r.estado_codigo, {})
        score, motivo = calcular_score_individual(est_obj, enriq_obj, cadena_obj, contexto, ind_ent)
        scores_por_id[r.id] = (score, motivo)

    # Calcular percentiles para asignar A/B/C/X
    scores_validos = [s for s, m in scores_por_id.values() if m is None and s > 0]
    if scores_validos:
        scores_validos.sort()
        p20 = scores_validos[int(len(scores_validos) * 0.40)]   # bottom 40% = C
        p60 = scores_validos[int(len(scores_validos) * 0.80)]   # next 40% = B; top 20% = A
    else:
        p20, p60 = 0, 0

    # Persistir resultados en batches
    batch: list[dict[str, Any]] = []
    for est_id, (score, motivo) in scores_por_id.items():
        if motivo is not None:
            seg = "X"
            descartados += 1
        elif score >= p60:
            seg = "A"
        elif score >= p20:
            seg = "B"
        else:
            seg = "C"
        distribucion[seg] = distribucion.get(seg, 0) + 1

        batch.append({"id": est_id, "score": score, "seg": seg})
        if len(batch) >= batch_size:
            session.execute(
                text(
                    "UPDATE establecimientos SET score_prioridad=:score, segmento_abc=:seg "
                    "WHERE id=:id"
                ),
                batch,
            )
            actualizados += len(batch)
            batch = []
            session.commit()

    if batch:
        session.execute(
            text(
                "UPDATE establecimientos SET score_prioridad=:score, segmento_abc=:seg "
                "WHERE id=:id"
            ),
            batch,
        )
        actualizados += len(batch)
        session.commit()

    registrar_operacion(
        session=session,
        tipo_operacion="calcular_scores_prospectos",
        finalidad="Calcular score 0-100 y segmento A/B/C por establecimiento para priorización comercial",
        base_legal="Datos públicos (DENUE, Google Places API, INEGI Indicadores) procesados internamente",
        notas=f"actualizados={actualizados} descartados_x={descartados} dist={distribucion}",
    )
    session.commit()

    return {
        "actualizados": actualizados,
        "descartados_x": descartados,
        "distribucion_abc": distribucion,
        "umbral_p20": round(p20, 2),
        "umbral_p60": round(p60, 2),
    }


def asignar_vendedores_por_municipio(session: Session) -> dict[str, Any]:
    """Asigna `establecimientos.vendedor_id` según `vendedores.municipios_ids`.

    Estrategia: para cada vendedor activo, asigna todos los establecimientos
    de los municipios listados en su `municipios_ids` JSONB que NO tengan
    vendedor o cuyo vendedor sea inactivo. Preserva asignaciones manuales
    (no sobrescribe si ya hay vendedor activo asignado).
    """
    res = session.execute(
        text(
            """
            UPDATE establecimientos e
               SET vendedor_id = sub.vendedor_id
              FROM (
                SELECT v.id AS vendedor_id, m.codigo AS municipio_codigo,
                       e.estado_codigo
                  FROM vendedores v,
                       jsonb_array_elements_text(v.municipios_ids) AS m(codigo)
                       LEFT JOIN establecimientos e ON true
                 WHERE v.activo = true
              ) sub
             WHERE e.municipio_codigo = sub.municipio_codigo
               AND (e.vendedor_id IS NULL OR
                    e.vendedor_id NOT IN (SELECT id FROM vendedores WHERE activo = true))
            """
        )
    )
    asignados = res.rowcount or 0
    session.commit()

    n_con_vendedor = session.execute(
        text(
            "SELECT COUNT(*) FROM establecimientos "
            "WHERE vendedor_id IS NOT NULL"
        )
    ).scalar() or 0
    n_total = session.execute(text("SELECT COUNT(*) FROM establecimientos")).scalar() or 0

    return {
        "asignados_esta_corrida": asignados,
        "establecimientos_con_vendedor": n_con_vendedor,
        "total_establecimientos": n_total,
    }
