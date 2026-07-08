from unittest.mock import AsyncMock, MagicMock

import anthropic
import httpx
import pytest
from pydantic import BaseModel, ValidationError

from ai_layer.clients.claude_client import (
    ClaudeAPIError,
    ClaudeClient,
    ClaudeClientError,
    ClaudeParsingError,
    ClaudeTimeoutError,
)


class _Output(BaseModel):
    category: str
    confidence: float


def _client() -> ClaudeClient:
    return ClaudeClient(api_key="test-key", model="claude-test")


def _text_response(text: str = "hello") -> MagicMock:
    block = MagicMock(type="text", text=text)
    return MagicMock(content=[block], stop_reason="end_turn")


def _dummy_validation_error() -> ValidationError:
    class _Dummy(BaseModel):
        x: int

    try:
        _Dummy(x=["not", "an", "int"])
    except ValidationError as exc:
        return exc
    raise AssertionError("expected ValidationError")


@pytest.mark.asyncio
async def test_create_text_success():
    client = _client()
    client._client.messages.create = AsyncMock(return_value=_text_response("hi there"))
    result = await client.create_text(system="sys", user_content="hello")
    assert result == "hi there"


@pytest.mark.asyncio
async def test_create_text_joins_multiple_text_blocks():
    client = _client()
    blocks = [MagicMock(type="text", text="a"), MagicMock(type="text", text="b")]
    client._client.messages.create = AsyncMock(
        return_value=MagicMock(content=blocks, stop_reason="end_turn")
    )
    result = await client.create_text(system="sys", user_content="hello")
    assert result == "ab"


@pytest.mark.asyncio
async def test_create_text_timeout_raises_claude_timeout_error():
    client = _client()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client._client.messages.create = AsyncMock(
        side_effect=anthropic.APITimeoutError(request=request)
    )
    with pytest.raises(ClaudeTimeoutError):
        await client.create_text(system="sys", user_content="hello")


@pytest.mark.asyncio
async def test_create_text_status_error_raises_claude_api_error():
    client = _client()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(500, text="server error", request=request)
    client._client.messages.create = AsyncMock(
        side_effect=anthropic.APIStatusError("server error", response=response, body=None)
    )
    with pytest.raises(ClaudeAPIError) as exc_info:
        await client.create_text(system="sys", user_content="hello")
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_create_text_connection_error_raises_claude_client_error():
    client = _client()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client._client.messages.create = AsyncMock(
        side_effect=anthropic.APIConnectionError(message="connection failed", request=request)
    )
    with pytest.raises(ClaudeClientError):
        await client.create_text(system="sys", user_content="hello")


@pytest.mark.asyncio
async def test_create_text_missing_api_key_type_error_wrapped():
    client = _client()
    client._client.messages.create = AsyncMock(side_effect=TypeError("missing api key header"))
    with pytest.raises(ClaudeAPIError) as exc_info:
        await client.create_text(system="sys", user_content="hello")
    assert exc_info.value.status_code is None


@pytest.mark.asyncio
async def test_parse_structured_success():
    client = _client()
    expected = _Output(category="helpful", confidence=0.9)
    client._client.messages.parse = AsyncMock(
        return_value=MagicMock(parsed_output=expected, stop_reason="end_turn")
    )
    result = await client.parse_structured(system="sys", user_content="hello", output_model=_Output)
    assert result == expected


@pytest.mark.asyncio
async def test_parse_structured_validation_error_raises_claude_parsing_error():
    client = _client()
    client._client.messages.parse = AsyncMock(side_effect=_dummy_validation_error())
    with pytest.raises(ClaudeParsingError):
        await client.parse_structured(system="sys", user_content="hello", output_model=_Output)


@pytest.mark.asyncio
async def test_parse_structured_timeout_raises_claude_timeout_error():
    client = _client()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client._client.messages.parse = AsyncMock(
        side_effect=anthropic.APITimeoutError(request=request)
    )
    with pytest.raises(ClaudeTimeoutError):
        await client.parse_structured(system="sys", user_content="hello", output_model=_Output)


@pytest.mark.asyncio
async def test_aclose_closes_underlying_client():
    client = _client()
    client._client.close = AsyncMock()
    await client.aclose()
    client._client.close.assert_awaited_once()
