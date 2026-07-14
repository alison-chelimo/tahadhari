"""Client for the Open-Meteo forecast API (https://open-meteo.com/en/docs) -- a free,
no-API-key REST/JSON weather API queried per lat/lon coordinate. Unlike ICPAC's WFS
layers, Open-Meteo has no notion of a "layer" or feature geometry: every call is scoped
to one point, so callers must already know which coordinates they care about (see
ai_layer/services/location_weather.py, which resolves a user's coordinates via
GoogleMapsClient.geocode() first)."""

import logging

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings
from ..schemas import WeatherResult

logger = logging.getLogger("ai_layer.clients.open_meteo_client")


class OpenMeteoError(Exception):
    pass


class OpenMeteoConnectionError(OpenMeteoError):
    pass


class OpenMeteoTimeoutError(OpenMeteoError):
    pass


class OpenMeteoServerError(OpenMeteoError):
    """5xx -- retryable."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"{status_code}: {body}")
        self.status_code = status_code
        self.body = body


class OpenMeteoClientError(OpenMeteoError):
    """4xx -- NOT retried, fail fast/loud. Open-Meteo reports bad params (e.g. an
    out-of-range latitude) as HTTP 400 with a JSON {"error": true, "reason": "..."}
    body, so this is reached via the normal status-code branch, unlike Google Maps'
    Geocoding API which encodes errors in a 200 response."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"{status_code}: {body}")
        self.status_code = status_code
        self.body = body


_RETRYABLE = (OpenMeteoConnectionError, OpenMeteoTimeoutError, OpenMeteoServerError)


class OpenMeteoClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        settings = get_settings()
        self._base_url = (base_url or settings.open_meteo_base_url).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.open_meteo_timeout_seconds
        self._max_retries = max_retries if max_retries is not None else settings.open_meteo_max_retries
        self._client = http_client or httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        self._owns_client = http_client is None

    async def __aenter__(self) -> "OpenMeteoClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _do_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        logger.debug("HTTP %s %s params=%s", method, path, kwargs.get("params"))
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            logger.debug("HTTP %s %s timed out: %s", method, path, exc)
            raise OpenMeteoTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.debug("HTTP %s %s connection error: %s", method, path, exc)
            raise OpenMeteoConnectionError(str(exc)) from exc

        logger.debug("HTTP %s %s -> status=%s", method, path, response.status_code)
        if response.status_code >= 500:
            raise OpenMeteoServerError(response.status_code, response.text)
        if 400 <= response.status_code < 500:
            raise OpenMeteoClientError(response.status_code, response.text)
        return response

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        retryer = AsyncRetrying(
            retry=retry_if_exception_type(_RETRYABLE),
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                return await self._do_request(method, path, **kwargs)

    async def get_precipitation(self, latitude: float, longitude: float) -> WeatherResult:
        """Today's forecast daily precipitation total (mm) for one coordinate."""
        response = await self._request(
            "GET",
            "/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "precipitation_sum",
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
        data = response.json()
        daily = data.get("daily") or {}
        precipitation_values = daily.get("precipitation_sum") or []
        if not precipitation_values or precipitation_values[0] is None:
            raise OpenMeteoError(f"no daily.precipitation_sum in Open-Meteo response: {data}")

        return WeatherResult(rainfall_mm=float(precipitation_values[0]), raw=data)
