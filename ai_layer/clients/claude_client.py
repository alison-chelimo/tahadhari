import logging
from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from ..config import get_settings

logger = logging.getLogger("ai_layer.clients.claude_client")

T = TypeVar("T", bound=BaseModel)


class ClaudeClientError(Exception):
    pass


class ClaudeTimeoutError(ClaudeClientError):
    pass


class ClaudeAPIError(ClaudeClientError):
    def __init__(self, status_code: int | None, message: str):
        super().__init__(message)
        self.status_code = status_code


class ClaudeParsingError(ClaudeClientError):
    """Raised when structured output can't be validated against the requested schema."""


class ClaudeClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        settings = get_settings()
        self._model = model or settings.anthropic_model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or settings.anthropic_api_key,
            timeout=timeout if timeout is not None else settings.claude_timeout_seconds,
            max_retries=max_retries if max_retries is not None else settings.claude_max_retries,
        )
        # Retries and timeout are handled natively by the Anthropic SDK's client
        # constructor (max_retries auto-retries connection errors/408/409/429/5xx with
        # exponential backoff; timeout is a hard per-request ceiling) -- deliberately NOT
        # reimplementing tenacity here, per "only add custom retry logic if you need
        # behavior beyond what the SDK provides."

    async def create_text(self, *, system: str, user_content: str, max_tokens: int = 1024) -> str:
        logger.debug("Claude create_text: model=%s max_tokens=%s", self._model, max_tokens)
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APITimeoutError as exc:
            raise ClaudeTimeoutError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise ClaudeAPIError(exc.status_code, str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise ClaudeClientError(str(exc)) from exc
        except TypeError as exc:
            # The SDK doesn't reject a missing/empty api_key at construction time --
            # it raises a bare TypeError from header-building on the first real
            # request. Wrap it so a missing key degrades via the same fallback path
            # as any other Claude failure, instead of crashing the caller.
            raise ClaudeAPIError(None, str(exc)) from exc

        text = "".join(b.text for b in response.content if b.type == "text")
        logger.debug("Claude create_text: response length=%d stop_reason=%s", len(text), response.stop_reason)
        return text

    async def parse_structured(
        self, *, system: str, user_content: str, output_model: Type[T], max_tokens: int = 1024
    ) -> T:
        logger.debug("Claude parse_structured: model=%s output_model=%s", self._model, output_model.__name__)
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
                output_format=output_model,
            )
        except anthropic.APITimeoutError as exc:
            raise ClaudeTimeoutError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise ClaudeAPIError(exc.status_code, str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise ClaudeClientError(str(exc)) from exc
        except ValidationError as exc:
            raise ClaudeParsingError(str(exc)) from exc
        except TypeError as exc:
            # See create_text's identical TypeError handling: a missing/empty
            # api_key surfaces here, not at client construction.
            raise ClaudeAPIError(None, str(exc)) from exc

        logger.debug("Claude parse_structured: parsed OK stop_reason=%s", response.stop_reason)
        return response.parsed_output

    async def aclose(self) -> None:
        await self._client.close()
