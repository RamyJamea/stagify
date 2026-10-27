import json
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx
from google import genai

from ..interface import (
    BaseNLP,
    ProviderError,
    ProviderOutputError,
    ProviderTransientError,
)
from ..schemas import GenConfig, ToolSpec, ToolResult
from ..schemas import CompleteToolCall, TurnResponse


class GeminiNLP(BaseNLP):
    def __init__(self):
        self.client = None

    async def connect(self, api_key: str | None, base_url: str | None = None) -> None:
        self.client = genai.Client(
            api_key=api_key, http_options={"retry_options": {"attempts": 1}}
        )
        self._disable_interactions_retries()

    def _disable_interactions_retries(self):
        if isinstance(self.client, genai.Client):
            self.client.aio.interactions.sdk_configuration.retry_config.strategy = (
                "none"
            )

    async def disconnect(self) -> None:
        if self.client is not None:
            await self.client.aio.aclose()
        self.client = None

    def create_model_msg(self, message):
        return {"type": "model_output", "content": [{"type": "text", "text": message}]}

    def create_user_msg(self, message):
        return {"type": "user_input", "content": [{"type": "text", "text": message}]}

    def create_tool_call(self, call: CompleteToolCall, arguments: dict) -> dict:
        return {
            "type": "function_call",
            "id": call.call_id,
            "name": call.name,
            "arguments": arguments,
        }

    def create_tool_result(self, result: ToolResult) -> list[dict]:
        return [
            {
                "type": "function_result",
                "name": result.name,
                "call_id": result.call_id,
                "result": [
                    {
                        "type": "text",
                        "text": json.dumps(result.result, ensure_ascii=False),
                    }
                ],
            }
        ]

    def create_tools(self, tools: list[ToolSpec]) -> list[dict]:
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in tools
        ]

    @staticmethod
    def _usage(response) -> dict:
        usage = getattr(response, "usage", None)
        return {
            "input_tokens": getattr(usage, "total_input_tokens", None),
            "reason_tokens": getattr(usage, "total_thought_tokens", None),
            "output_tokens": getattr(usage, "total_output_tokens", None),
            "cache_tokens": getattr(usage, "total_cached_tokens", None),
            "tool_tokens": getattr(usage, "total_tool_use_tokens", None),
        }

    @staticmethod
    def _error_details(exc) -> dict:
        body = getattr(exc, "body", None)
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except ValueError:
                return {}
        error = body.get("error", body) if isinstance(body, dict) else None
        return error if isinstance(error, dict) else {}

    @staticmethod
    def _seconds(value) -> float | None:
        if value is None:
            return None
        try:
            seconds = float(str(value).removesuffix("s"))
        except ValueError:
            try:
                seconds = (
                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds()
            except (TypeError, ValueError, OverflowError):
                return None
        return max(0, seconds) if math.isfinite(seconds) else None

    @classmethod
    def _retry_after(cls, exc) -> float | None:
        headers = getattr(getattr(exc, "response", None), "headers", {})
        hints = [headers.get("retry-after")]
        details = cls._error_details(exc).get("details", [])
        for detail in details if isinstance(details, list) else []:
            if (
                isinstance(detail, dict)
                and detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo"
            ):
                hints.append(detail.get("retryDelay"))
        delays = [delay for hint in hints if (delay := cls._seconds(hint)) is not None]
        return max(delays, default=None)

    async def gen_turn(
        self,
        config: GenConfig,
        content: str | list[dict],
        tools: list[ToolSpec] | None = None,
    ) -> TurnResponse:
        if self.client is None:
            raise RuntimeError("Provider is not connected")
        self._disable_interactions_retries()

        try:
            response = await self.client.aio.interactions.create(
                model=config.model_name,
                input=content,
                store=False,
                stream=False,
                system_instruction=config.instructions,
                generation_config={
                    key: value
                    for key, value in {
                        "temperature": config.temperature,
                        "top_p": config.top_p,
                        "thinking_level": config.thinking_level,
                        "max_output_tokens": config.max_output_tokens,
                    }.items()
                    if value is not None
                },
                tools=self.create_tools(tools) if tools else [],
            )
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            error = self._error_details(exc)
            if status_code == 429 and error.get("code") == "quota_exceeded":
                raise ProviderError(
                    "Provider daily quota exhausted", status_code=429
                ) from exc
            if status_code in {408, 429, 500, 502, 503, 504}:
                raise ProviderTransientError(
                    status_code, self._retry_after(exc)
                ) from exc
            if status_code == 400 and error.get("code") == "malformed_tool_call":
                raise ProviderOutputError(
                    "Malformed tool JSON", status_code=status_code
                ) from exc

            if status_code is not None:
                raise ProviderError(
                    f"Provider request failed (HTTP {status_code})",
                    status_code=status_code,
                ) from exc
            transport_errors = (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.RemoteProtocolError,
                TimeoutError,
                ConnectionError,
            )
            if isinstance(exc, transport_errors) or isinstance(
                exc.__cause__, transport_errors
            ):
                raise ProviderTransientError() from exc
            raise

        if response.steps is None:
            raise ProviderOutputError("Provider returned no generation steps")
        steps = [s.model_dump(mode="json", exclude_none=True) for s in response.steps]
        calls = [
            CompleteToolCall(call_id=s["id"], name=s["name"], arguments=s["arguments"])
            for s in steps
            if s["type"] == "function_call"
        ]
        return TurnResponse(
            model_name=config.model_name,
            request_id=str(response.id),
            text=response.output_text,
            status=response.status,
            calls=calls,
            replay_content=steps,
            **self._usage(response),
        )
