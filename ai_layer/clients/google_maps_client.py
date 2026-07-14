"""Client for the Google Maps Geocoding API, used to resolve a user's free-text
location reply (e.g. "Kitengela") to lat/lon before it's handed to OpenMeteoClient.

Important asymmetry vs. AlertsApiClient/OpenMeteoClient: Google's Geocoding API
reports "no results," "bad key," and "rate limited" as HTTP 200 with a JSON `status`
field, NOT via the HTTP status code -- `_do_request`'s 4xx/5xx branching never fires
for those cases. geocode() therefore inspects `response.json()["status"]` itself after
a successful request and does its own retry loop around that check (see below), rather
than relying purely on `_request`'s transport-level retry."""

import logging

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings
from ..schemas import GeocodeResult

logger = logging.getLogger("ai_layer.clients.google_maps_client")

# Geocoding API `status` values that are transport-level-equivalent-to-5xx: worth
# retrying, since they're not a property of this specific place_name.
_RETRYABLE_STATUSES = {"OVER_QUERY_LIMIT", "UNKNOWN_ERROR"}


class GoogleMapsError(Exception):
    pass


class GoogleMapsConnectionError(GoogleMapsError):
    pass


class GoogleMapsTimeoutError(GoogleMapsError):
    pass


class GoogleMapsServerError(GoogleMapsError):
    """5xx, or a retryable Geocoding API `status` (OVER_QUERY_LIMIT/UNKNOWN_ERROR)."""

    def __init__(self, status_code_or_status, body: str):
        super().__init__(f"{status_code_or_status}: {body}")
        self.status_code_or_status = status_code_or_status
        self.body = body


class GoogleMapsClientError(GoogleMapsError):
    """4xx, or a non-retryable Geocoding API `status` (INVALID_REQUEST/REQUEST_DENIED)."""

    def __init__(self, status_code_or_status, body: str):
        super().__init__(f"{status_code_or_status}: {body}")
        self.status_code_or_status = status_code_or_status
        self.body = body


class GoogleMapsNoResultsError(GoogleMapsError):
    """status == ZERO_RESULTS -- terminal, not a transport/quota error."""


_RETRYABLE = (GoogleMapsConnectionError, GoogleMapsTimeoutError, GoogleMapsServerError)


class GoogleMapsClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        settings = get_settings()
        self._api_key = api_key or settings.google_maps_api_key
        self._base_url = (base_url or settings.google_maps_base_url).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.google_maps_timeout_seconds
        self._max_retries = max_retries if max_retries is not None else settings.google_maps_max_retries
        self._client = http_client or httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        self._owns_client = http_client is None

    async def __aenter__(self) -> "GoogleMapsClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _do_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        logger.debug("HTTP %s %s params=%s", method, path, {k: v for k, v in (kwargs.get("params") or {}).items() if k != "key"})
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            logger.debug("HTTP %s %s timed out: %s", method, path, exc)
            raise GoogleMapsTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.debug("HTTP %s %s connection error: %s", method, path, exc)
            raise GoogleMapsConnectionError(str(exc)) from exc

        logger.debug("HTTP %s %s -> status=%s", method, path, response.status_code)
        if response.status_code >= 500:
            raise GoogleMapsServerError(response.status_code, response.text)
        if 400 <= response.status_code < 500:
            raise GoogleMapsClientError(response.status_code, response.text)
        return response

    async def geocode(self, place_name: str) -> GeocodeResult:
        retryer = AsyncRetrying(
            retry=retry_if_exception_type(_RETRYABLE),
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                response = await self._do_request(
                    "GET", "/maps/api/geocode/json", params={"address": place_name, "key": self._api_key},
                )
                data = response.json()
                status = data.get("status")

                if status == "OK":
                    results = data.get("results") or []
                    if not results:
                        raise GoogleMapsNoResultsError(f"status=OK but no results for {place_name!r}")
                    location = results[0]["geometry"]["location"]
                    return GeocodeResult(
                        latitude=location["lat"],
                        longitude=location["lng"],
                        formatted_address=results[0].get("formatted_address", place_name),
                    )
                if status == "ZERO_RESULTS":
                    raise GoogleMapsNoResultsError(f"no geocoding results for {place_name!r}")
                if status in _RETRYABLE_STATUSES:
                    # Raised INSIDE the `with attempt:` block so tenacity's retry-on-type
                    # check (which only sees exceptions, not response bodies) still fires.
                    raise GoogleMapsServerError(status, str(data))
                raise GoogleMapsClientError(status, str(data))
