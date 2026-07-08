from unittest.mock import AsyncMock

import httpx
import pytest

from ai_layer.clients.alerts_api import (
    AlertsApiClient,
    AlertsApiClientError,
    AlertsApiConnectionError,
    AlertsApiError,
    AlertsApiNotFoundError,
    AlertsApiServerError,
    AlertsApiTimeoutError,
)
from ai_layer.schemas import AlertIn, FeedbackIn, MessageIn, FeedbackCategory


def _alert_json(alert_id: int = 1) -> dict:
    return {
        "id": alert_id,
        "hazard_type": "heavy_rainfall",
        "severity": "high",
        "geography_type": "ward",
        "geography_ref": "Kisumu_Central",
        "rainfall_mm": 65.0,
        "created_at": "2024-01-01T00:00:00Z",
    }


def _client_with_mock(response=None, side_effect=None, max_retries: int = 0) -> tuple[AlertsApiClient, AsyncMock]:
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    if side_effect is not None:
        mock_http_client.request.side_effect = side_effect
    else:
        mock_http_client.request.return_value = response
    client = AlertsApiClient(
        base_url="http://testserver", max_retries=max_retries, http_client=mock_http_client
    )
    return client, mock_http_client


@pytest.mark.asyncio
async def test_ingest_alert_success():
    client, mock_http_client = _client_with_mock(response=httpx.Response(200, json=_alert_json()))
    alert = await client.ingest_alert(
        AlertIn(source="test", geography_type="ward", geography_ref="Kisumu_Central", rainfall_mm=65.0)
    )
    assert alert.id == 1
    assert alert.severity == "high"
    mock_http_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_alert_success():
    client, _ = _client_with_mock(response=httpx.Response(200, json=_alert_json(alert_id=7)))
    alert = await client.get_alert(7)
    assert alert.id == 7


@pytest.mark.asyncio
async def test_get_alert_raises_on_malformed_response():
    client, _ = _client_with_mock(response=httpx.Response(200, json=None))
    with pytest.raises(AlertsApiError):
        await client.get_alert(1)


@pytest.mark.asyncio
async def test_predict_flooding_returns_predictions():
    payload = {
        "predictions": [
            {"segment": "Adams_Arcade", "risk": "high", "flood_prediction_id": 5},
        ]
    }
    client, _ = _client_with_mock(response=httpx.Response(200, json=payload))
    predictions = await client.predict_flooding(1)
    assert len(predictions) == 1
    assert predictions[0].segment_name == "Adams_Arcade"
    assert predictions[0].risk_level == "high"


@pytest.mark.asyncio
async def test_match_templates_returns_templates():
    payload = [
        {
            "id": 1, "hazard_type": "heavy_rainfall", "occupation": "farmer",
            "severity": "high", "language": "en", "template_text": "Rain expected.",
        }
    ]
    client, _ = _client_with_mock(response=httpx.Response(200, json=payload))
    templates = await client.match_templates(
        hazard_type="heavy_rainfall", occupation="farmer", severity="high"
    )
    assert len(templates) == 1
    assert templates[0].id == 1


@pytest.mark.asyncio
async def test_create_message_success():
    payload = {
        "id": 1, "profile_id": 1, "alert_id": 1, "template_id": None, "flood_prediction_id": None,
        "final_text": "hello", "channel": "whatsapp", "delivery_status": "pending",
        "sent_at": "2024-01-01T00:00:00Z",
    }
    client, _ = _client_with_mock(response=httpx.Response(201, json=payload))
    message = await client.create_message(
        MessageIn(profile_id=1, alert_id=1, final_text="hello", channel="whatsapp")
    )
    assert message.id == 1


@pytest.mark.asyncio
async def test_create_feedback_success():
    payload = {
        "id": 1, "message_id": 1, "profile_id": 1, "feedback_type": "helpful",
        "feedback_text": None, "created_at": "2024-01-01T00:00:00Z",
    }
    client, mock_http_client = _client_with_mock(response=httpx.Response(201, json=payload))
    feedback = await client.create_feedback(
        FeedbackIn(message_id=1, profile_id=1, feedback_type=FeedbackCategory.HELPFUL)
    )
    assert feedback.id == 1
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["json"]["feedback_type"] == "helpful"


@pytest.mark.asyncio
async def test_client_error_fails_fast_without_retry():
    client, mock_http_client = _client_with_mock(
        response=httpx.Response(400, text="bad request"), max_retries=3
    )
    with pytest.raises(AlertsApiClientError):
        await client.get_alert(1)
    mock_http_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_not_found_raises_specific_error():
    client, _ = _client_with_mock(response=httpx.Response(404, text="missing"))
    with pytest.raises(AlertsApiNotFoundError):
        await client.get_alert(999)


@pytest.mark.asyncio
async def test_server_error_exhausts_retries_then_raises(mocker):
    mocker.patch("asyncio.sleep", new=AsyncMock())
    client, mock_http_client = _client_with_mock(
        response=httpx.Response(500, text="boom"), max_retries=2
    )
    with pytest.raises(AlertsApiServerError):
        await client.get_alert(1)
    assert mock_http_client.request.await_count == 3


@pytest.mark.asyncio
async def test_server_error_succeeds_after_retry(mocker):
    mocker.patch("asyncio.sleep", new=AsyncMock())
    client, mock_http_client = _client_with_mock(
        side_effect=[httpx.Response(500, text="boom"), httpx.Response(200, json=_alert_json())],
        max_retries=2,
    )
    alert = await client.get_alert(1)
    assert alert.id == 1
    assert mock_http_client.request.await_count == 2


@pytest.mark.asyncio
async def test_timeout_raises_timeout_error():
    client, _ = _client_with_mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(AlertsApiTimeoutError):
        await client.get_alert(1)


@pytest.mark.asyncio
async def test_connection_error_raises_connection_error():
    client, _ = _client_with_mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(AlertsApiConnectionError):
        await client.get_alert(1)


@pytest.mark.asyncio
async def test_aclose_closes_owned_client_only():
    owned_client = AlertsApiClient(base_url="http://testserver")
    assert owned_client._owns_client is True

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    injected_client = AlertsApiClient(base_url="http://testserver", http_client=mock_http_client)
    assert injected_client._owns_client is False
    await injected_client.aclose()
    mock_http_client.aclose.assert_not_awaited()

    await owned_client.aclose()


@pytest.mark.asyncio
async def test_context_manager_closes_client():
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.request.return_value = httpx.Response(200, json=_alert_json())
    async with AlertsApiClient(base_url="http://testserver", http_client=mock_http_client) as client:
        await client.get_alert(1)
