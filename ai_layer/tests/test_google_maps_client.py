from unittest.mock import AsyncMock

import httpx
import pytest

from ai_layer.clients.google_maps_client import (
    GoogleMapsClient,
    GoogleMapsClientError,
    GoogleMapsConnectionError,
    GoogleMapsNoResultsError,
    GoogleMapsServerError,
    GoogleMapsTimeoutError,
)


def _geocode_ok_json(lat: float = -1.4536, lng: float = 36.9721, formatted_address: str = "Kitengela, Kenya") -> dict:
    return {
        "status": "OK",
        "results": [
            {"formatted_address": formatted_address, "geometry": {"location": {"lat": lat, "lng": lng}}}
        ],
    }


def _client_with_mock(response=None, side_effect=None, max_retries: int = 0) -> tuple[GoogleMapsClient, AsyncMock]:
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    if side_effect is not None:
        mock_http_client.request.side_effect = side_effect
    else:
        mock_http_client.request.return_value = response
    client = GoogleMapsClient(
        api_key="test-key", base_url="http://testserver", max_retries=max_retries, http_client=mock_http_client
    )
    return client, mock_http_client


@pytest.mark.asyncio
async def test_geocode_success():
    client, mock_http_client = _client_with_mock(response=httpx.Response(200, json=_geocode_ok_json()))
    result = await client.geocode("Kitengela")
    assert result.latitude == -1.4536
    assert result.longitude == 36.9721
    assert result.formatted_address == "Kitengela, Kenya"
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["params"]["address"] == "Kitengela"


@pytest.mark.asyncio
async def test_geocode_zero_results_raises_no_results_error():
    client, _ = _client_with_mock(response=httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []}))
    with pytest.raises(GoogleMapsNoResultsError):
        await client.geocode("asdkfjasldkfj")


@pytest.mark.asyncio
async def test_geocode_invalid_request_fails_fast():
    client, mock_http_client = _client_with_mock(
        response=httpx.Response(200, json={"status": "INVALID_REQUEST", "results": []}), max_retries=3
    )
    with pytest.raises(GoogleMapsClientError):
        await client.geocode("")
    mock_http_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_geocode_request_denied_fails_fast():
    client, mock_http_client = _client_with_mock(
        response=httpx.Response(200, json={"status": "REQUEST_DENIED", "results": []}), max_retries=3
    )
    with pytest.raises(GoogleMapsClientError):
        await client.geocode("Kitengela")
    mock_http_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_geocode_over_query_limit_retried_then_raises(mocker):
    mocker.patch("asyncio.sleep", new=AsyncMock())
    client, mock_http_client = _client_with_mock(
        response=httpx.Response(200, json={"status": "OVER_QUERY_LIMIT", "results": []}), max_retries=2
    )
    with pytest.raises(GoogleMapsServerError):
        await client.geocode("Kitengela")
    assert mock_http_client.request.await_count == 3


@pytest.mark.asyncio
async def test_geocode_over_query_limit_succeeds_after_retry(mocker):
    mocker.patch("asyncio.sleep", new=AsyncMock())
    client, mock_http_client = _client_with_mock(
        side_effect=[
            httpx.Response(200, json={"status": "OVER_QUERY_LIMIT", "results": []}),
            httpx.Response(200, json=_geocode_ok_json()),
        ],
        max_retries=2,
    )
    result = await client.geocode("Kitengela")
    assert result.formatted_address == "Kitengela, Kenya"
    assert mock_http_client.request.await_count == 2


@pytest.mark.asyncio
async def test_http_5xx_is_retryable():
    client, mock_http_client = _client_with_mock(response=httpx.Response(500, text="boom"), max_retries=0)
    with pytest.raises(GoogleMapsServerError):
        await client.geocode("Kitengela")
    mock_http_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_timeout_raises_timeout_error():
    client, _ = _client_with_mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(GoogleMapsTimeoutError):
        await client.geocode("Kitengela")


@pytest.mark.asyncio
async def test_connection_error_raises_connection_error():
    client, _ = _client_with_mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(GoogleMapsConnectionError):
        await client.geocode("Kitengela")


@pytest.mark.asyncio
async def test_aclose_closes_owned_client_only():
    owned_client = GoogleMapsClient(api_key="test-key", base_url="http://testserver")
    assert owned_client._owns_client is True

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    injected_client = GoogleMapsClient(
        api_key="test-key", base_url="http://testserver", http_client=mock_http_client
    )
    assert injected_client._owns_client is False
    await injected_client.aclose()
    mock_http_client.aclose.assert_not_awaited()

    await owned_client.aclose()
