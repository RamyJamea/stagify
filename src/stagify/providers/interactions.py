"""Thin adapter over the application's original Gemini Interactions scripts."""

from __future__ import annotations

from typing import Any, Self

from ..contracts import ModelRequest, ModelResponse, ProviderCapabilities, ToolCall, dumps
from ..errors import (
    ConfigurationError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderOutputError,
    ProviderTransientError,
)
from ..nlp.interface import ProviderError as NLPProviderError
from ..nlp.interface import ProviderOutputError as NLPProviderOutputError
from ..nlp.interface import ProviderTransientError as NLPProviderTransientError
from ..nlp.schemas import GenConfig, ToolResult
from ..nlp.schemas import ToolSpec as NLPToolSpec
from ..usage import TokenUsage


class GoogleProvider:
    """Uses interactions.create, store=False, stream=False, and opaque step replay."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        client: Any = None,
        temperature: float | None = 0.0,
        top_p: float | None = 1.0,
        thinking_level: str | None = "low",
        capabilities: ProviderCapabilities | None = None,
    ):
        try:
            from ..nlp.providers.gemini import GeminiNLP
        except ImportError as exc:
            raise ConfigurationError(
                "Install the Google adapter with: uv add 'stagify[google]'"
            ) from exc
        self.config = GenConfig(
            model_name=model, temperature=temperature, top_p=top_p, thinking_level=thinking_level
        )
        self.model, self.name = model, "google:" + model
        self.capabilities = capabilities or ProviderCapabilities()
        self.nlp = GeminiNLP()
        self.nlp.client = client
        self._api_key, self._owned = api_key, client is None

    def _content(self, request: ModelRequest) -> list[dict[str, Any]]:
        content = []
        for message in request.messages:
            if message.native is not None:
                if message.native.get("provider") != "google_interactions":
                    raise ProviderOutputError("Replay data belongs to a different provider API")
                content.extend(message.native["replay_content"])
            elif message.role == "tool":
                content.extend(
                    self.nlp.create_tool_result(
                        ToolResult(
                            call_id=message.call_id, name=message.name, result=message.content
                        )
                    )
                )
            elif message.role == "assistant":
                if message.calls:
                    content.extend(
                        self.nlp.create_tool_call(call, call.arguments) for call in message.calls
                    )
                else:
                    content.append(self.nlp.create_model_msg(str(message.content)))
            else:
                content.append(
                    self.nlp.create_user_msg(
                        message.content
                        if isinstance(message.content, str)
                        else dumps(message.content)
                    )
                )
        return content

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if self.nlp.client is None:
            await self.nlp.connect(self._api_key)
        config = self.config.model_copy(
            update={
                "instructions": request.instructions,
                "max_output_tokens": request.max_output_tokens,
            }
        )
        try:
            response = await self.nlp.gen_turn(
                config,
                self._content(request),
                [
                    NLPToolSpec(name=t.name, description=t.description, parameters=t.parameters)
                    for t in request.tools
                ],
            )
        except NLPProviderTransientError as exc:
            error = ProviderTransientError(retry_after=exc.retry_after)
            error.details["status_code"] = exc.status_code
            raise error from exc
        except NLPProviderOutputError as exc:
            raise ProviderOutputError(str(exc), details={"status_code": exc.status_code}) from exc
        except NLPProviderError as exc:
            error_class = (
                ProviderAuthenticationError if exc.status_code in (401, 403) else ProviderError
            )
            raise error_class(str(exc), details={"status_code": exc.status_code}) from exc
        return ModelResponse(
            text=response.text or "",
            calls=tuple(ToolCall(c.call_id, c.name, c.arguments) for c in response.calls),
            usage=TokenUsage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cached_input_tokens=response.cache_tokens,
                reasoning_tokens=response.reason_tokens,
                tool_tokens=response.tool_tokens,
            ),
            native={"provider": "google_interactions", "replay_content": response.replay_content}
            if response.replay_content
            else None,
            request_id=response.request_id,
            status=response.status,
        )

    async def aclose(self) -> None:
        if self._owned:
            await self.nlp.disconnect()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
