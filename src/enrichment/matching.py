"""Matcher DENUE↔Google Places.

Estrategia:
1. Construir query: `nombre + colonia + municipio + estado` del DENUE.
2. Text Search con `locationBias` centrado en (lat, lon) DENUE, radio 1 km.
3. Score cada candidato:
   - Distancia geográfica (penaliza si > 200 m)
   - Fuzzy match nombre vs `displayName.text` (rapidfuzz token_sort)
   - Tipo coincide (si Google devuelve types relevantes)
4. Mejor score >= umbral → match. Si no, no_match.
5. Para el match: place_details (Pro) y persistir en `enriquecimiento_google`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from loguru import logger
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from src.core.heuristicas import normaliza_nombre
from src.core.models import EnriquecimientoGoogle, Establecimiento
from src.ingestion.places_api import PlacesClient

UMBRAL_MATCH_SCORE = 70.0  # 0-100, mínimo para considerar match real
UMBRAL_DISTANCIA_M = 200.0  # más allá de esto, descartamos aunque nombre coincida


@dataclass
class CandidatoEvaluado:
    place_id: str
    display_name: str
    score: float
    distancia_m: float | None
    raw: dict[str, Any]


_RADIO_TIERRA_M = 6371000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos puntos (lat, lon) en grados."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _RADIO_TIERRA_M * c


def evaluar_candidatos(
    establecimiento: Establecimiento, candidatos: list[dict[str, Any]]
) -> list[CandidatoEvaluado]:
    """Score cada candidato Google contra el establecimiento DENUE.

    Score 0-100:
    - 80% peso fuzzy nombre (rapidfuzz token_sort)
    - 20% peso proximidad (100 si <50m, 50 si <200m, 0 si >200m)
    """
    nombre_denue_norm = establecimiento.nombre_norm
    lat_denue = establecimiento.latitud
    lon_denue = establecimiento.longitud

    evaluados: list[CandidatoEvaluado] = []
    for c in candidatos:
        place_id = c.get("id", "")
        display = (c.get("displayName") or {}).get("text", "")
        if not place_id or not display:
            continue

        nombre_g_norm = normaliza_nombre(display)
        score_nombre = fuzz.token_sort_ratio(nombre_denue_norm, nombre_g_norm)

        # Proximidad
        distancia_m: float | None = None
        if lat_denue is not None and lon_denue is not None:
            loc = c.get("location") or {}
            lat_g = loc.get("latitude")
            lon_g = loc.get("longitude")
            if lat_g is not None and lon_g is not None:
                distancia_m = _haversine_m(lat_denue, lon_denue, lat_g, lon_g)

        if distancia_m is None:
            score_prox = 50  # sin coords, neutro
        elif distancia_m < 50:
            score_prox = 100
        elif distancia_m < 200:
            score_prox = 70
        elif distancia_m < 500:
            score_prox = 30
        else:
            score_prox = 0

        score_total = round(0.8 * score_nombre + 0.2 * score_prox, 2)

        evaluados.append(
            CandidatoEvaluado(
                place_id=place_id,
                display_name=display,
                score=score_total,
                distancia_m=distancia_m,
                raw=c,
            )
        )

    evaluados.sort(key=lambda c: c.score, reverse=True)
    return evaluados


def construir_query(est: Establecimiento) -> str:
    """Query para Text Search: nombre + colonia + municipio + estado."""
    partes = [est.nombre]
    if est.colonia:
        partes.append(est.colonia)
    if est.estado:
        partes.append(est.estado)
    return " ".join(partes)


def enriquecer_establecimiento(
    session: Session,
    cli: PlacesClient,
    est: Establecimiento,
    *,
    page_size: int = 5,
    pedir_detalle: bool = True,
) -> EnriquecimientoGoogle:
    """Match DENUE↔Google + (opcional) place_details + upsert a enriquecimiento_google.

    Devuelve el registro de enriquecimiento (con match_status='match', 'no_match' o 'duda').
    """
    query = construir_query(est)
    candidatos = cli.text_search(
        query,
        lat=est.latitud,
        lon=est.longitud,
        radius_m=1000,
        page_size=page_size,
        establecimiento_id=est.id,
    )

    if not candidatos:
        return _persistir_no_match(session, est, motivo="sin candidatos")

    evaluados = evaluar_candidatos(est, candidatos)
    mejor = evaluados[0]

    # Decisión: match si score >= umbral Y distancia <= 200m (si tenemos coords)
    es_match = mejor.score >= UMBRAL_MATCH_SCORE and (
        mejor.distancia_m is None or mejor.distancia_m <= UMBRAL_DISTANCIA_M
    )

    if not es_match:
        return _persistir_no_match(
            session,
            est,
            motivo=f"mejor score={mejor.score}, dist={mejor.distancia_m}m",
            place_id_candidato=mejor.place_id,
            score=mejor.score,
        )

    # Match razonable: opcionalmente pedir detalle (Pro fields)
    detalle: dict[str, Any] | None = None
    if pedir_detalle:
        try:
            detalle = cli.place_details(mejor.place_id, establecimiento_id=est.id)
        except Exception as e:
            logger.warning("place_details falló para {pid}: {e}", pid=mejor.place_id, e=e)
            detalle = mejor.raw  # fallback al essentials

    return _persistir_match(session, est, mejor, detalle or mejor.raw)


def _persistir_match(
    session: Session,
    est: Establecimiento,
    candidato: CandidatoEvaluado,
    detalle: dict[str, Any],
) -> EnriquecimientoGoogle:
    enriq = session.get(EnriquecimientoGoogle, est.id)
    if enriq is None:
        enriq = EnriquecimientoGoogle(establecimiento_id=est.id, place_id=candidato.place_id)
        session.add(enriq)

    loc = detalle.get("location") or {}
    enriq.place_id = candidato.place_id
    enriq.match_score = candidato.score
    enriq.match_status = "match"
    enriq.google_display_name = (detalle.get("displayName") or {}).get("text")
    enriq.google_formatted_address = detalle.get("formattedAddress")
    enriq.google_types = detalle.get("types")
    enriq.google_business_status = detalle.get("businessStatus")
    enriq.google_rating = detalle.get("rating")
    enriq.google_user_rating_count = detalle.get("userRatingCount")
    enriq.google_opening_hours = detalle.get("regularOpeningHours")
    enriq.google_price_level = detalle.get("priceLevel")
    enriq.google_phone = detalle.get("nationalPhoneNumber")
    enriq.google_website = detalle.get("websiteUri")
    enriq.google_lat = loc.get("latitude")
    enriq.google_lon = loc.get("longitude")
    session.flush()

    # Actualizar campos derivados en establecimientos: place_id + fuente + telefono
    # si DENUE no tenía. NO sobrescribir teléfono manual.
    if est.google_place_id != candidato.place_id:
        est.google_place_id = candidato.place_id
    if "Google_Places" not in (est.fuentes or []):
        est.fuentes = list(est.fuentes or []) + ["Google_Places"]
    if not est.telefono and enriq.google_phone:
        est.telefono = enriq.google_phone

    return enriq


def _persistir_no_match(
    session: Session,
    est: Establecimiento,
    *,
    motivo: str,
    place_id_candidato: str | None = None,
    score: float | None = None,
) -> EnriquecimientoGoogle:
    enriq = session.get(EnriquecimientoGoogle, est.id)
    if enriq is None:
        # Necesita un place_id distinto, usamos sufijo no-match único
        enriq = EnriquecimientoGoogle(
            establecimiento_id=est.id,
            place_id=place_id_candidato or f"no_match_{est.id}",
            match_status="no_match",
        )
        session.add(enriq)
    enriq.match_score = score
    enriq.match_status = "no_match"
    enriq.google_display_name = motivo[:200] if motivo else None
    session.flush()
    return enriq
