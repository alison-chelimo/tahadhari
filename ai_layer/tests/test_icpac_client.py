from unittest.mock import AsyncMock

import httpx
import pytest

from ai_layer.clients.icpac_client import (
    IcpacClient,
    IcpacClientError,
    IcpacConnectionError,
    IcpacError,
    IcpacServerError,
    IcpacTimeoutError,
)


def _feature_collection() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"iso3": "KEN", "duration": 12.0}},
            {"type": "Feature", "properties": {"iso3": "UGA", "duration": 30.0}},
        ],
    }


def _client_with_mock(response=None, side_effect=None, max_retries: int = 0) -> tuple[IcpacClient, AsyncMock]:
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    if side_effect is not None:
        mock_http_client.request.side_effect = side_effect
    else:
        mock_http_client.request.return_value = response
    client = IcpacClient(base_url="http://testserver", max_retries=max_retries, http_client=mock_http_client)
    return client, mock_http_client


@pytest.mark.asyncio
async def test_fetch_layer_features_success():
    client, mock_http_client = _client_with_mock(response=httpx.Response(200, json=_feature_collection()))
    features = await client.fetch_layer_features("geonode:gha_dr_events")
    assert len(features) == 2
    assert features[0]["properties"]["iso3"] == "KEN"
    mock_http_client.request.assert_awaited_once()
    _, kwargs = mock_http_client.request.call_args
    assert kwargs["params"]["typeNames"] == "geonode:gha_dr_events"


@pytest.mark.asyncio
async def test_fetch_layer_features_no_features_key_returns_empty_list():
    client, _ = _client_with_mock(response=httpx.Response(200, json={"type": "FeatureCollection"}))
    features = await client.fetch_layer_features("geonode:empty")
    assert features == []


@pytest.mark.asyncio
async def test_fetch_layer_features_non_json_raises_icpac_error():
    client, _ = _client_with_mock(response=httpx.Response(200, text="<xml>not json</xml>"))
    with pytest.raises(IcpacError):
        await client.fetch_layer_features("geonode:bad")


@pytest.mark.asyncio
async def test_client_error_fails_fast_without_retry():
    client, mock_http_client = _client_with_mock(
        response=httpx.Response(400, text="bad request"), max_retries=3
    )
    with pytest.raises(IcpacClientError):
        await client.fetch_layer_features("geonode:bad")
    mock_http_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_server_error_exhausts_retries_then_raises(mocker):
    mocker.patch("asyncio.sleep", new=AsyncMock())
    client, mock_http_client = _client_with_mock(
        response=httpx.Response(500, text="boom"), max_retries=2
    )
    with pytest.raises(IcpacServerError):
        await client.fetch_layer_features("geonode:bad")
    assert mock_http_client.request.await_count == 3


@pytest.mark.asyncio
async def test_timeout_raises_timeout_error():
    client, _ = _client_with_mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(IcpacTimeoutError):
        await client.fetch_layer_features("geonode:bad")


@pytest.mark.asyncio
async def test_connection_error_raises_connection_error():
    client, _ = _client_with_mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(IcpacConnectionError):
        await client.fetch_layer_features("geonode:bad")


@pytest.mark.asyncio
async def test_aclose_closes_owned_client_only():
    owned_client = IcpacClient(base_url="http://testserver")
    assert owned_client._owns_client is True

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    injected_client = IcpacClient(base_url="http://testserver", http_client=mock_http_client)
    assert injected_client._owns_client is False
    await injected_client.aclose()
    mock_http_client.aclose.assert_not_awaited()

    await owned_client.aclose()
