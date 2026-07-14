from unittest.mock import AsyncMock

import httpx
import pytest

from ai_layer.clients.open_meteo_client import (
    OpenMeteoClient,
    OpenMeteoClientError,
    OpenMeteoConnectionError,
    OpenMeteoError,
    OpenMeteoServerError,
    OpenMeteoTimeoutError,
)


def _forecast_json(precipitation: float = 12.5) -> dict:
    return {"daily": {"precipitation_sum": [precipitation]}}


def _client_with_mock(response=None, side_effect=None, max_retries: int = 0) -> tuple[OpenMeteoClient, AsyncMock]:
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    if side_effect is not None:
        mock_http_client.request.side_effect = side_effect
    else:
        mock_http_client.request.return_value = response
    client = OpenMeteoClient(base_url="http://testserver", max_retries=max_retries, http_client=mock_http_client)
    return client, mock_http_client


@pytest.mark.asyncio
async def test_get_precipitation_success():
    client, mock_http_client = _client_with_mock(response=httpx.Response(200, json=_forecast_json(40.0)))
    result = await client.get_precipitation(-1.4536, 36.9721)
    assert result.rainfall_mm == 40.0
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["params"]["latitude"] == -1.4536
    assert kwargs["params"]["longitude"] == 36.9721


@pytest.mark.asyncio
async def test_get_precipitation_missing_daily_data_raises():
    client, _ = _client_with_mock(response=httpx.Response(200, json={"daily": {"precipitation_sum": []}}))
    with pytest.raises(OpenMeteoError):
        await client.get_precipitation(0.0, 0.0)


@pytest.mark.asyncio
async def test_client_error_fails_fast_without_retry():
    client, mock_http_client = _client_with_mock(
        response=httpx.Response(400, json={"error": True, "reason": "bad latitude"}), max_retries=3
    )
    with pytest.raises(OpenMeteoClientError):
        await client.get_precipitation(999.0, 0.0)
    mock_http_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_server_error_exhausts_retries_then_raises(mocker):
    mocker.patch("asyncio.sleep", new=AsyncMock())
    client, mock_http_client = _client_with_mock(response=httpx.Response(500, text="boom"), max_retries=2)
    with pytest.raises(OpenMeteoServerError):
        await client.get_precipitation(0.0, 0.0)
    assert mock_http_client.request.await_count == 3


@pytest.mark.asyncio
async def test_timeout_raises_timeout_error():
    client, _ = _client_with_mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(OpenMeteoTimeoutError):
        await client.get_precipitation(0.0, 0.0)


@pytest.mark.asyncio
async def test_connection_error_raises_connection_error():
    client, _ = _client_with_mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(OpenMeteoConnectionError):
        await client.get_precipitation(0.0, 0.0)


@pytest.mark.asyncio
async def test_aclose_closes_owned_client_only():
    owned_client = OpenMeteoClient(base_url="http://testserver")
    assert owned_client._owns_client is True

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    injected_client = OpenMeteoClient(base_url="http://testserver", http_client=mock_http_client)
    assert injected_client._owns_client is False
    await injected_client.aclose()
    mock_http_client.aclose.assert_not_awaited()

    await owned_client.aclose()
