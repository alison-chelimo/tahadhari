import logging

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings

logger = logging.getLogger("ai_layer.clients.icpac_client")


class IcpacError(Exception):
    pass


class IcpacConnectionError(IcpacError):
    pass


class IcpacTimeoutError(IcpacError):
    pass


class IcpacServerError(IcpacError):
    """5xx -- retryable."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"{status_code}: {body}")
        self.status_code = status_code
        self.body = body


class IcpacClientError(IcpacError):
    """4xx -- NOT retried, fail fast/loud."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"{status_code}: {body}")
        self.status_code = status_code
        self.body = body


_RETRYABLE = (IcpacConnectionError, IcpacTimeoutError, IcpacServerError)


class IcpacClient:
    """Client for ICPAC's GeoNode WFS endpoint (geoportal.icpac.net/geoserver/wfs).

    No layer on this portal is a true live rainfall-alert feed as of writing -- it's a
    catalog of mostly static/historical geospatial layers. This client is deliberately
    generic (any WFS type_name in, GeoJSON features out) so it keeps working once a
    real live layer is chosen; see Settings.icpac_layer_type_name.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        settings = get_settings()
        self._base_url = (base_url or settings.icpac_base_url).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.icpac_timeout_seconds
        self._max_retries = max_retries if max_retries is not None else settings.icpac_max_retries
        self._client = http_client or httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        self._owns_client = http_client is None

    async def __aenter__(self) -> "IcpacClient":
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
            raise IcpacTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.debug("HTTP %s %s connection error: %s", method, path, exc)
            raise IcpacConnectionError(str(exc)) from exc

        logger.debug("HTTP %s %s -> status=%s", method, path, response.status_code)
        if response.status_code >= 500:
            raise IcpacServerError(response.status_code, response.text)
        if 400 <= response.status_code < 500:
            raise IcpacClientError(response.status_code, response.text)
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

    async def fetch_layer_features(self, type_name: str) -> list[dict]:
        """WFS GetFeature against /geoserver/wfs, GeoJSON output. Returns the raw
        `features` list (each a GeoJSON Feature dict with a `properties` dict)."""
        response = await self._request(
            "GET",
            "/geoserver/wfs",
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": type_name,
                "outputFormat": "application/json",
            },
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise IcpacError(f"non-JSON response fetching layer {type_name!r}: {exc}") from exc
        return data.get("features", [])
