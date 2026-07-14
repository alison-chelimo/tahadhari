from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest
from pydantic import BaseModel, ValidationError

from ai_layer.clients.openai_client import (
    OpenAIAPIError,
    OpenAIClient,
    OpenAIClientError,
    OpenAIParsingError,
    OpenAITimeoutError,
)


class _Output(BaseModel):
    category: str
    confidence: float


def _client() -> OpenAIClient:
    return OpenAIClient(api_key="test-key", model="gpt-test")


def _text_response(text: str = "hello") -> MagicMock:
    message = MagicMock(content=text)
    choice = MagicMock(message=message, finish_reason="stop")
    return MagicMock(choices=[choice])


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
    client._client.chat.completions.create = AsyncMock(return_value=_text_response("hi there"))
    result = await client.create_text(system="sys", user_content="hello")
    assert result == "hi there"


@pytest.mark.asyncio
async def test_create_text_timeout_raises_openai_timeout_error():
    client = _client()
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    client._client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=request)
    )
    with pytest.raises(OpenAITimeoutError):
        await client.create_text(system="sys", user_content="hello")


@pytest.mark.asyncio
async def test_create_text_status_error_raises_openai_api_error():
    client = _client()
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(500, text="server error", request=request)
    client._client.chat.completions.create = AsyncMock(
        side_effect=openai.APIStatusError("server error", response=response, body=None)
    )
    with pytest.raises(OpenAIAPIError) as exc_info:
        await client.create_text(system="sys", user_content="hello")
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_create_text_connection_error_raises_openai_client_error():
    client = _client()
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    client._client.chat.completions.create = AsyncMock(
        side_effect=openai.APIConnectionError(message="connection failed", request=request)
    )
    with pytest.raises(OpenAIClientError):
        await client.create_text(system="sys", user_content="hello")


@pytest.mark.asyncio
async def test_parse_structured_success():
    client = _client()
    expected = _Output(category="helpful", confidence=0.9)
    message = MagicMock(parsed=expected, refusal=None)
    choice = MagicMock(message=message, finish_reason="stop")
    client._client.chat.completions.parse = AsyncMock(return_value=MagicMock(choices=[choice]))
    result = await client.parse_structured(system="sys", user_content="hello", output_model=_Output)
    assert result == expected


@pytest.mark.asyncio
async def test_parse_structured_refusal_raises_parsing_error():
    client = _client()
    message = MagicMock(parsed=None, refusal="cannot comply")
    choice = MagicMock(message=message, finish_reason="stop")
    client._client.chat.completions.parse = AsyncMock(return_value=MagicMock(choices=[choice]))
    with pytest.raises(OpenAIParsingError):
        await client.parse_structured(system="sys", user_content="hello", output_model=_Output)


@pytest.mark.asyncio
async def test_parse_structured_validation_error_raises_openai_parsing_error():
    client = _client()
    client._client.chat.completions.parse = AsyncMock(side_effect=_dummy_validation_error())
    with pytest.raises(OpenAIParsingError):
        await client.parse_structured(system="sys", user_content="hello", output_model=_Output)


@pytest.mark.asyncio
async def test_parse_structured_timeout_raises_openai_timeout_error():
    client = _client()
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    client._client.chat.completions.parse = AsyncMock(
        side_effect=openai.APITimeoutError(request=request)
    )
    with pytest.raises(OpenAITimeoutError):
        await client.parse_structured(system="sys", user_content="hello", output_model=_Output)


@pytest.mark.asyncio
async def test_aclose_closes_underlying_client():
    client = _client()
    client._client.close = AsyncMock()
    await client.aclose()
    client._client.close.assert_awaited_once()
