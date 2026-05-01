"""Cliente HTTP del DENUE — INEGI.

**Estrategia primaria (Fase 3+): descarga de ZIPs CSV oficiales** desde
`https://www.inegi.org.mx/contenidos/masiva/denue/denue_<cve>_csv.zip`. Esta
es la forma soportada para descargas masivas: 1 request por entidad, ~5-50 MB
por ZIP, ~3 s descarga + extracción. Mucho más eficiente que la API JSON.

Endpoints API JSON (complementarios, ver método correspondiente):
- `cuantificar(scian, area, estrato)` — conteo por entidad. **Gratis**.
- `por_nombre(palabra, cve_entidad, ...)` — búsqueda por keyword textual en
  nombre/razón social. Útil para descubrir SCIAN específicos.
- `ficha(clee)` — detalle de un establecimiento individual.

Endpoints API JSON OBSOLETOS (NO usar):
- `BuscarEntidad/SCIAN/.../...` y variantes — devuelven HTML de error o
  protocolo HTTP corrupto; el método `buscar_entidad_por_keyword` se conserva
  pero busca por palabra clave, NO por SCIAN.

Reglas comunes:
- Throttling: ≥1.1 s entre requests (60 req/min).
- Retries: 3 intentos con backoff exponencial ante 5xx, 429, timeouts.
- Logging: cada operación deja fila en `denue_descargas_log`.
"""

from __future__ import annotations

import csv
import io
import time
import zipfile
from collections.abc import Iterator
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import get_settings
from src.ingestion.denue_models import CuantificarItem, EstablecimientoDenueRaw

DENUE_BASE_URL = "https://www.inegi.org.mx/app/api/denue/v1/consulta"
DENUE_BULK_ZIP_URL_TPL = "https://www.inegi.org.mx/contenidos/masiva/denue/denue_{cve}_csv.zip"


class DenueError(Exception):
    """Error de cliente DENUE (red, formato, o respuesta inesperada)."""


class DenueClient:
    """Cliente sincrónico para la API DENUE.

    Uso:
        with DenueClient() as cli:
            total = cli.cuantificar("311830", "0", "0")
            for batch in cli.iter_buscar_entidad("311830", "23", batch_size=2000):
                ...
    """

    # 60 req/min = 1 req/s. Margen = 1.1s entre requests para no rozar el límite.
    _MIN_INTERVALO_SEG = 1.1

    def __init__(self, *, timeout: float = 30.0):
        self._settings = get_settings()
        self._token = self._settings.INEGI_DENUE_TOKEN
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "CRM-Granos-MX/0.1 (operacion@intergranel.mx)"},
        )
        self._ultimo_request_ts = 0.0

    def __enter__(self) -> DenueClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ---------- Helpers ----------

    def _throttle(self) -> None:
        """Mantiene ≥1.1s entre requests para respetar 60 req/min."""
        ahora = time.monotonic()
        delta = ahora - self._ultimo_request_ts
        if delta < self._MIN_INTERVALO_SEG:
            time.sleep(self._MIN_INTERVALO_SEG - delta)
        self._ultimo_request_ts = time.monotonic()

    @retry(
        retry=retry_if_exception_type(
            (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.HTTPStatusError,
            )
        ),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get_json(self, url: str) -> Any:
        """GET con throttle + retry + parse JSON. Levanta para 4xx/5xx."""
        self._throttle()
        t0 = time.monotonic()
        resp = self._client.get(url)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        # 5xx y 429 → retry; 4xx fatal
        if resp.status_code >= 500 or resp.status_code == 429:
            logger.warning(
                "DENUE {status} en {dur}ms — reintentando", status=resp.status_code, dur=elapsed_ms
            )
            resp.raise_for_status()
        if resp.status_code >= 400:
            raise DenueError(
                f"DENUE {resp.status_code} para {self._safe_url(url)}: {resp.text[:200]}"
            )

        # Si la respuesta es HTML (la URL anterior obsoleta devolvía página de error
        # con HTTP 200), abortamos.
        ctype = resp.headers.get("content-type", "")
        if "html" in ctype.lower():
            raise DenueError(
                f"DENUE devolvió HTML — endpoint quizá obsoleto: {self._safe_url(url)}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise DenueError(f"Respuesta no-JSON desde {self._safe_url(url)}") from e

        logger.debug(
            "DENUE OK {dur}ms {bytes}B — {url}",
            dur=elapsed_ms,
            bytes=len(resp.content),
            url=self._safe_url(url),
        )
        return data

    def _safe_url(self, url: str) -> str:
        """Oculta el token al loguear URLs."""
        if self._token in url:
            return url.replace(self._token, "***")
        return url

    # ---------- Endpoints ----------

    def cuantificar(self, scian: str, area: str = "0", estrato: str = "0") -> dict[str, int]:
        """Conteo por entidad para un SCIAN. `area="0"` = todo MX.

        Devuelve {cve_entidad: total}.
        """
        url = f"{DENUE_BASE_URL}/Cuantificar/{scian}/{area}/{estrato}/{self._token}"
        data = self._get_json(url)
        if not isinstance(data, list):
            return {}
        return {
            CuantificarItem.model_validate(item).AG: CuantificarItem.model_validate(item).total_int
            for item in data
        }

    # ---------- Descarga masiva ZIP CSV ----------

    def descargar_zip_entidad(self, cve_entidad: str) -> bytes:
        """Descarga el ZIP CSV oficial de una entidad y devuelve los bytes crudos.

        Tamaños típicos: 3-50 MB. URL pública, sin token (es bulk download).
        """
        url = DENUE_BULK_ZIP_URL_TPL.format(cve=cve_entidad)
        self._throttle()
        t0 = time.monotonic()
        # Timeout generoso — los ZIPs grandes (CDMX) pueden tomar >30s.
        resp = self._client.get(url, timeout=180.0)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if resp.status_code != 200:
            raise DenueError(f"DENUE bulk ZIP HTTP {resp.status_code} para entidad {cve_entidad}")

        ctype = resp.headers.get("content-type", "")
        if "zip" not in ctype.lower():
            raise DenueError(f"DENUE bulk no devolvió ZIP — content-type: {ctype}")

        logger.debug(
            "ZIP entidad {cve} descargado: {bytes} bytes en {ms} ms",
            cve=cve_entidad,
            bytes=len(resp.content),
            ms=elapsed_ms,
        )
        return resp.content

    def iter_csv_entidad(
        self, cve_entidad: str, *, scian_filter: set[str] | None = None
    ) -> Iterator[dict[str, str]]:
        """Descarga el ZIP de la entidad, descomprime, y itera filas filtradas por SCIAN.

        El CSV viene en LATIN1 con headers oficiales del DENUE. Si `scian_filter` se
        provee, solo emite filas con `codigo_act` en el set.
        """
        zip_bytes = self.descargar_zip_entidad(cve_entidad)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_name = next(
                (n for n in zf.namelist() if n.lower().endswith(".csv") and "denue_inegi" in n),
                None,
            )
            if csv_name is None:
                raise DenueError(
                    f"ZIP de entidad {cve_entidad} no contiene CSV denue_inegi_*"
                )
            with zf.open(csv_name) as raw:
                # Decode LATIN1 → str. Los CSV de INEGI usan windows-1252 / latin-1.
                text_stream = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                reader = csv.DictReader(text_stream)
                for row in reader:
                    if scian_filter is not None and row.get("codigo_act", "") not in scian_filter:
                        continue
                    yield row

    # ---------- API JSON complementaria ----------

    def por_nombre(
        self,
        palabra: str,
        cve_entidad: str,
        registro_inicial: int = 1,
        registro_final: int = 100,
    ) -> list[EstablecimientoDenueRaw]:
        """Búsqueda por palabra clave en nombre/razón social en una entidad."""
        url = (
            f"{DENUE_BASE_URL}/Nombre/{palabra}/{cve_entidad}"
            f"/{registro_inicial}/{registro_final}/{self._token}"
        )
        data = self._get_json(url)
        if not isinstance(data, list):
            return []
        return [EstablecimientoDenueRaw.model_validate(item) for item in data]

    def ficha(self, clee: str) -> EstablecimientoDenueRaw | None:
        """Detalle de un establecimiento por CLEE."""
        url = f"{DENUE_BASE_URL}/Ficha/{clee}/{self._token}"
        data = self._get_json(url)
        if not data:
            return None
        # Ficha devuelve un objeto, no array
        if isinstance(data, list):
            return EstablecimientoDenueRaw.model_validate(data[0]) if data else None
        return EstablecimientoDenueRaw.model_validate(data)
