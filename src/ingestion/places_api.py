"""Cliente Google Places API (New) — Text Search + Place Details.

API oficial: https://developers.google.com/maps/documentation/places/web-service

Reglas de uso:
- **Siempre** usar `X-Goog-FieldMask` con la mínima cantidad de campos para
  pagar el SKU más barato. Sin FieldMask, Google factura como Enterprise.
- **Cache** todas las respuestas en `google_places_log` para no pagar 2× la
  misma query.
- **Circuit breaker**: antes de cada call comprueba `MONTHLY_BUDGET_USD`. Si
  el gasto del mes lo excede, levanta `BudgetExceededError`.

SKUs y costo (vigentes a abril 2026, tarifas USD):
- **Essentials** (gratis hasta 10,000 calls/mes): `places.id`, `displayName`,
  `formattedAddress`, `location`, `types`. Costo después: $0.005/call.
- **Pro** (gratis hasta 5,000 calls/mes): `rating`, `userRatingCount`,
  `regularOpeningHours`, `priceLevel`, `nationalPhoneNumber`, `websiteUri`,
  `businessStatus`. Costo después: $0.018/call.
- **Enterprise**: fotos, reseñas individuales. Costo: $0.022/call. NO usar
  por LFPDPPP (reseñas con autor son PII de terceros).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import get_settings
from src.core.models import GooglePlacesLog

PLACES_BASE_URL = "https://places.googleapis.com/v1"

# Costo USD por call después del free tier mensual (estimado para circuit breaker).
# Tarifas oficiales en https://developers.google.com/maps/billing-and-pricing/pricing
COSTO_ESSENTIALS_USD = 0.005
COSTO_PRO_USD = 0.018
COSTO_ENTERPRISE_USD = 0.022

# FieldMasks predefinidas
FIELDMASK_TEXT_SEARCH_ESSENTIALS = "places.id,places.displayName,places.formattedAddress,places.location,places.types"
FIELDMASK_PLACE_DETAILS_PRO = (
    "id,displayName,formattedAddress,location,types,businessStatus,"
    "rating,userRatingCount,regularOpeningHours,priceLevel,"
    "nationalPhoneNumber,websiteUri"
)


class PlacesError(Exception):
    """Error genérico del cliente Places."""


class BudgetExceededError(PlacesError):
    """Gasto mensual excedió `MONTHLY_BUDGET_USD`. No se hicieron más calls."""


def _gasto_mes_actual_usd(session: Session) -> float:
    """Suma `costo_estimado_usd` de `google_places_log` desde el inicio del mes."""
    import datetime as dt

    inicio_mes = dt.datetime.now(dt.UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    resultado = session.execute(
        select(func.coalesce(func.sum(GooglePlacesLog.costo_estimado_usd), 0))
        .where(GooglePlacesLog.fecha >= inicio_mes)
    ).scalar_one()
    return float(resultado)


class PlacesClient:
    """Cliente sincrónico para Google Places API (New).

    Uso:
        with PlacesClient(session=db) as cli:
            results = cli.text_search(
                "Tortillería La Esperanza Centro Querétaro",
                lat=20.59, lon=-100.39,
            )
    """

    # 100 ms entre requests = 600/min. Google permite ~10 req/s para usuario individual.
    _MIN_INTERVALO_SEG = 0.1

    def __init__(self, *, session: Session | None = None, timeout: float = 30.0):
        self._settings = get_settings()
        self._api_key = self._settings.GOOGLE_PLACES_API_KEY
        if not self._api_key:
            raise PlacesError(
                "GOOGLE_PLACES_API_KEY no está configurada en .env"
            )
        self._budget_usd = self._settings.MONTHLY_BUDGET_USD
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "CRM-Granos-MX/0.1 (operacion@intergranel.mx)"},
        )
        self._session = session
        self._ultimo_request_ts = 0.0

    def __enter__(self) -> PlacesClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ---------- Helpers ----------

    def _throttle(self) -> None:
        ahora = time.monotonic()
        delta = ahora - self._ultimo_request_ts
        if delta < self._MIN_INTERVALO_SEG:
            time.sleep(self._MIN_INTERVALO_SEG - delta)
        self._ultimo_request_ts = time.monotonic()

    def _check_budget(self, costo_estimado_usd: float) -> None:
        """Si el gasto del mes + esta llamada excede el budget, aborta."""
        if self._session is None:
            return  # sin sesión no hay tracking
        gasto_actual = _gasto_mes_actual_usd(self._session)
        if gasto_actual + costo_estimado_usd > self._budget_usd:
            raise BudgetExceededError(
                f"Gasto del mes ${gasto_actual:.2f} + esta call ${costo_estimado_usd:.4f} "
                f"excede MONTHLY_BUDGET_USD={self._budget_usd}"
            )

    def _registrar_log(
        self,
        *,
        metodo: str,
        sku: str,
        field_mask: str,
        status_http: int,
        bytes_recibidos: int,
        place_id_devuelto: str | None,
        costo_estimado_usd: float,
        cache_hit: bool = False,
        establecimiento_id: int | None = None,
    ) -> None:
        if self._session is None:
            return
        log = GooglePlacesLog(
            establecimiento_id=establecimiento_id,
            metodo=metodo,
            sku=sku,
            field_mask=field_mask,
            status_http=status_http,
            bytes_recibidos=bytes_recibidos,
            place_id_devuelto=place_id_devuelto,
            costo_estimado_usd=costo_estimado_usd,
            cache_hit=cache_hit,
        )
        self._session.add(log)
        self._session.flush()

    @retry(
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)
        ),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _post_json(
        self, url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[Any, int, int]:
        self._throttle()
        resp = self._client.post(url, json=body, headers=headers)
        if resp.status_code >= 500 or resp.status_code == 429:
            resp.raise_for_status()
        if resp.status_code == 403:
            raise PlacesError(f"403 Forbidden — verifica restricciones de API key: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise PlacesError(f"Places HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json(), resp.status_code, len(resp.content)

    @retry(
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)
        ),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get_json(self, url: str, headers: dict[str, str]) -> tuple[Any, int, int]:
        self._throttle()
        resp = self._client.get(url, headers=headers)
        if resp.status_code >= 500 or resp.status_code == 429:
            resp.raise_for_status()
        if resp.status_code >= 400:
            raise PlacesError(f"Places HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json(), resp.status_code, len(resp.content)

    # ---------- Endpoints ----------

    def text_search(
        self,
        query: str,
        *,
        lat: float | None = None,
        lon: float | None = None,
        radius_m: int = 5000,
        page_size: int = 5,
        field_mask: str = FIELDMASK_TEXT_SEARCH_ESSENTIALS,
        establecimiento_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """POST `/places:searchText`. Devuelve lista de candidatos.

        Si `lat`/`lon` se proveen, sesga la búsqueda con `locationBias` (radio 5 km).
        """
        sku = "Pro" if "rating" in field_mask else "Essentials"
        costo = COSTO_PRO_USD if sku == "Pro" else COSTO_ESSENTIALS_USD
        self._check_budget(costo)

        url = f"{PLACES_BASE_URL}/places:searchText"
        body: dict[str, Any] = {
            "textQuery": query,
            "languageCode": "es",
            "regionCode": "MX",
            "pageSize": page_size,
        }
        if lat is not None and lon is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": radius_m,
                }
            }

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }

        try:
            data, status, bytes_recibidos = self._post_json(url, body, headers)
        except Exception as e:
            self._registrar_log(
                metodo="text_search",
                sku=sku,
                field_mask=field_mask,
                status_http=0,
                bytes_recibidos=0,
                place_id_devuelto=None,
                costo_estimado_usd=0,
                establecimiento_id=establecimiento_id,
            )
            raise PlacesError(f"text_search falló: {e}") from e

        places = data.get("places", []) if isinstance(data, dict) else []

        primer_id = places[0].get("id") if places else None
        self._registrar_log(
            metodo="text_search",
            sku=sku,
            field_mask=field_mask,
            status_http=status,
            bytes_recibidos=bytes_recibidos,
            place_id_devuelto=primer_id,
            costo_estimado_usd=costo,
            establecimiento_id=establecimiento_id,
        )
        return places

    def place_details(
        self,
        place_id: str,
        *,
        field_mask: str = FIELDMASK_PLACE_DETAILS_PRO,
        establecimiento_id: int | None = None,
    ) -> dict[str, Any]:
        """GET `/places/{place_id}`. Devuelve detalle completo (Pro fields)."""
        sku = "Pro"
        costo = COSTO_PRO_USD
        self._check_budget(costo)

        url = f"{PLACES_BASE_URL}/places/{place_id}"
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }

        try:
            data, status, bytes_recibidos = self._get_json(url, headers)
        except Exception as e:
            self._registrar_log(
                metodo="place_details",
                sku=sku,
                field_mask=field_mask,
                status_http=0,
                bytes_recibidos=0,
                place_id_devuelto=place_id,
                costo_estimado_usd=0,
                establecimiento_id=establecimiento_id,
            )
            raise PlacesError(f"place_details falló: {e}") from e

        self._registrar_log(
            metodo="place_details",
            sku=sku,
            field_mask=field_mask,
            status_http=status,
            bytes_recibidos=bytes_recibidos,
            place_id_devuelto=place_id,
            costo_estimado_usd=costo,
            establecimiento_id=establecimiento_id,
        )
        return data if isinstance(data, dict) else {}

    def gasto_mes_actual(self) -> float:
        """Devuelve gasto USD acumulado este mes (consultando `google_places_log`)."""
        if self._session is None:
            return 0.0
        return _gasto_mes_actual_usd(self._session)
