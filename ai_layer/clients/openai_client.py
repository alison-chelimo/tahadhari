import logging
from typing import Type, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from ..config import get_settings

logger = logging.getLogger("ai_layer.clients.openai_client")

T = TypeVar("T", bound=BaseModel)


class OpenAIClientError(Exception):
    pass


class OpenAITimeoutError(OpenAIClientError):
    pass


class OpenAIAPIError(OpenAIClientError):
    def __init__(self, status_code: int | None, message: str):
        super().__init__(message)
        self.status_code = status_code


class OpenAIParsingError(OpenAIClientError):
    """Raised when structured output can't be validated against the requested schema."""


class OpenAIClient:
    """Drop-in replacement for ClaudeClient (same create_text/parse_structured surface)
    so personalizer.py and feedback_classifier.py need no structural changes to switch
    providers -- see ai_layer/clients/claude_client.py for the Claude version, kept
    intact so switching back only means uncommenting its usage."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        settings = get_settings()
        self._model = model or settings.openai_model
        self._client = openai.AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            timeout=timeout if timeout is not None else settings.openai_timeout_seconds,
            max_retries=max_retries if max_retries is not None else settings.openai_max_retries,
        )

    async def create_text(self, *, system: str, user_content: str, max_tokens: int = 1024) -> str:
        logger.debug("OpenAI create_text: model=%s max_tokens=%s", self._model, max_tokens)
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            )
        except openai.APITimeoutError as exc:
            raise OpenAITimeoutError(str(exc)) from exc
        except openai.APIStatusError as exc:
            raise OpenAIAPIError(exc.status_code, str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise OpenAIClientError(str(exc)) from exc

        text = response.choices[0].message.content or ""
        logger.debug(
            "OpenAI create_text: response length=%d finish_reason=%s",
            len(text), response.choices[0].finish_reason,
        )
        return text

    async def parse_structured(
        self, *, system: str, user_content: str, output_model: Type[T], max_tokens: int = 1024
    ) -> T:
        logger.debug(
            "OpenAI parse_structured: model=%s output_model=%s", self._model, output_model.__name__
        )
        try:
            response = await self._client.chat.completions.parse(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                response_format=output_model,
            )
        except openai.APITimeoutError as exc:
            raise OpenAITimeoutError(str(exc)) from exc
        except openai.APIStatusError as exc:
            raise OpenAIAPIError(exc.status_code, str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise OpenAIClientError(str(exc)) from exc
        except ValidationError as exc:
            raise OpenAIParsingError(str(exc)) from exc

        message = response.choices[0].message
        if message.refusal:
            raise OpenAIParsingError(f"model refused to produce structured output: {message.refusal}")
        if message.parsed is None:
            raise OpenAIParsingError("no parsed structured output returned")

        logger.debug("OpenAI parse_structured: parsed OK finish_reason=%s", response.choices[0].finish_reason)
        return message.parsed

    async def aclose(self) -> None:
        await self._client.close()
