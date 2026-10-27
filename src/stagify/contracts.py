"""Portable provider messages, limits, and stage result envelopes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import to_jsonable_python

from .usage import StageUsage, TokenUsage

T = TypeVar("T")


def json_data(value: Any) -> Any:
    return json.loads(json.dumps(to_jsonable_python(value), allow_nan=False))


def dumps(value: Any) -> str:
    return json.dumps(json_data(value), ensure_ascii=False, sort_keys=True, allow_nan=False)


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant", "tool"]
    content: Any = ""
    calls: tuple[ToolCall, ...] = ()
    call_id: str | None = None
    name: str | None = None
    native: Any = None


@dataclass(frozen=True)
class ModelRequest:
    instructions: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    max_output_tokens: int = 4096


@dataclass(frozen=True)
class ModelResponse:
    text: str = ""
    calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)
    native: Any = None
    request_id: str | None = None
    status: Literal["completed", "requires_action", "failed", "incomplete"] = "completed"


@dataclass(frozen=True)
class ProviderCapabilities:
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    context_window: int | None = None


@dataclass(frozen=True)
class RunLimits:
    max_model_calls: int = 60
    max_tool_calls: int = 120
    max_input_tokens: int = 24_000
    max_output_tokens: int = 4096
    max_depth: int = 5
    max_model_retries: int = 2
    retry_delay: float = 0.1
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "max_model_calls",
            "max_tool_calls",
            "max_input_tokens",
            "max_output_tokens",
            "max_depth",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.max_model_retries < 0 or self.retry_delay < 0:
            raise ValueError("Retry settings cannot be negative")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StageResult(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    status: Literal["completed", "partial", "failed", "cancelled"]
    output: T | None = None
    run_id: str
    stage_name: str
    invocation_id: str
    parent_invocation_id: str | None = None
    usage: StageUsage = Field(default_factory=StageUsage)
    error: ErrorInfo | None = None
    history: list[Message] = Field(default_factory=list)
    children: list[StageResult] = Field(default_factory=list)
    compactions: list[dict[str, Any]] = Field(default_factory=list)
    resource_versions: dict[str, int] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
