import logging

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings
from ..schemas import (
    Alert,
    AlertIn,
    ActionTemplate,
    PredictionRecord,
    MessageIn,
    Message,
    FeedbackIn,
    Feedback,
)

logger = logging.getLogger("ai_layer.clients.alerts_api")


class AlertsApiError(Exception):
    pass


class AlertsApiConnectionError(AlertsApiError):
    pass


class AlertsApiTimeoutError(AlertsApiError):
    pass


class AlertsApiServerError(AlertsApiError):
    """5xx -- retryable."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"{status_code}: {body}")
        self.status_code = status_code
        self.body = body


class AlertsApiClientError(AlertsApiError):
    """4xx -- NOT retried, fail fast/loud."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"{status_code}: {body}")
        self.status_code = status_code
        self.body = body


class AlertsApiNotFoundError(AlertsApiClientError):
    """404 specifically."""


_RETRYABLE = (AlertsApiConnectionError, AlertsApiTimeoutError, AlertsApiServerError)


class AlertsApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        settings = get_settings()
        self._base_url = (base_url or settings.tahadhari_api_base_url).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.tahadhari_api_timeout_seconds
        self._max_retries = max_retries if max_retries is not None else settings.tahadhari_api_max_retries
        self._client = http_client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"X-API-Key": settings.tahadhari_service_api_key},
        )
        self._owns_client = http_client is None

    async def __aenter__(self) -> "AlertsApiClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _do_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        logger.debug("HTTP %s %s params=%s json=%s", method, path, kwargs.get("params"), kwargs.get("json"))
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            logger.debug("HTTP %s %s timed out: %s", method, path, exc)
            raise AlertsApiTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.debug("HTTP %s %s connection error: %s", method, path, exc)
            raise AlertsApiConnectionError(str(exc)) from exc

        logger.debug("HTTP %s %s -> status=%s", method, path, response.status_code)
        if response.status_code >= 500:
            raise AlertsApiServerError(response.status_code, response.text)
        if response.status_code == 404:
            raise AlertsApiNotFoundError(response.status_code, response.text)
        if 400 <= response.status_code < 500:
            raise AlertsApiClientError(response.status_code, response.text)
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

    # ---- typed API surface ----

    async def ingest_alert(self, alert_in: AlertIn) -> Alert:
        response = await self._request(
            "POST", "/alerts/ingest", json=alert_in.model_dump(mode="json", exclude_none=True)
        )
        return Alert(**response.json())

    async def get_alert(self, alert_id: int) -> Alert:
        response = await self._request("GET", f"/alerts/{alert_id}")
        try:
            return Alert(**response.json())
        except (ValueError, TypeError) as exc:
            # Known upstream bug: a bad alert_id can 200 with a null/malformed body
            # instead of 404 (alerts.py has no HTTPException handling -- out of scope
            # to fix there; we just fail loudly here instead of silently returning None).
            raise AlertsApiError(f"malformed response from GET /alerts/{alert_id}: {exc}") from exc

    async def predict_flooding(self, alert_id: int) -> list[PredictionRecord]:
        response = await self._request("POST", f"/alerts/predict/{alert_id}")
        data = response.json()
        return [
            PredictionRecord(
                segment_name=p["segment"],
                risk_level=p["risk"],
                flood_prediction_id=p.get("flood_prediction_id"),
                window_start=p.get("window_start"),
                window_end=p.get("window_end"),
            )
            for p in data.get("predictions", [])
        ]

    async def match_templates(
        self, *, hazard_type: str, occupation: str, severity: str, language: str = "en"
    ) -> list[ActionTemplate]:
        response = await self._request(
            "GET",
            "/templates/match",
            params={
                "hazard_type": hazard_type,
                "occupation": occupation,
                "severity": severity,
                "language": language,
            },
        )
        return [ActionTemplate(**row) for row in response.json()]

    async def create_message(self, message_in: MessageIn) -> Message:
        response = await self._request("POST", "/messages/", json=message_in.model_dump(mode="json"))
        return Message(**response.json())

    async def create_feedback(self, feedback_in: FeedbackIn) -> Feedback:
        payload = feedback_in.model_dump(mode="json")
        payload["feedback_type"] = feedback_in.feedback_type.value
        response = await self._request("POST", "/feedback/", json=payload)
        return Feedback(**response.json())
