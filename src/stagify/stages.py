"""A stage can run directly or be exposed through a StageTool adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

from .completion import Completion
from .context import ContextPolicies
from .context.fields import ContextField
from .contracts import ToolSpec
from .errors import ConfigurationError
from .providers.base import Provider
from .tools import Tool, validate_name

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT")
RESERVED = {"complete_stage", "read_evidence", "list_evidence", "save_memory", "withdraw_memory"}


@dataclass(frozen=True)
class Stage(Generic[InputT, OutputT]):
    name: str
    instructions: str
    input_model: type[InputT]
    output_model: type[BaseModel] | None = None
    tools: tuple[Tool | StageTool, ...] = ()
    context_policies: ContextPolicies | None = None
    context_fields: tuple[str, ...] | None = None
    memory: bool = False
    required_memory: tuple[str, ...] = ()
    validate_completion: Callable[..., Any] | None = None
    max_model_calls: int | None = None
    max_completion_repairs: int = 1
    timeout_seconds: float | None = None
    allow_partial: bool = False
    partial_output: Callable[..., Any] | None = None
    verbose: bool | None = None
    resources: frozenset[str] | None = None
    provider: Provider | None = None
    max_output_tokens: int | None = None
    context: dict[str, ContextField] = field(default_factory=dict)
    completion: Completion | None = None

    def __post_init__(self) -> None:
        validate_name(self.name)
        if not isinstance(self.input_model, type) or not issubclass(self.input_model, BaseModel):
            raise ConfigurationError("Stage input_model must be a Pydantic model class")
        if self.output_model is not None and not issubclass(self.output_model, BaseModel):
            raise ConfigurationError("Stage output_model must be a Pydantic model class or None")
        object.__setattr__(self, "tools", tuple(self.tools))
        names = [t.name for t in self.tools]
        if len(names) != len(set(names)) or set(names) & RESERVED:
            raise ConfigurationError("Duplicate or reserved tool name")
        if self.max_model_calls is not None and self.max_model_calls < 1:
            raise ConfigurationError("max_model_calls must be positive")
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ConfigurationError("max_output_tokens must be positive")
        if self.max_completion_repairs < 0:
            raise ConfigurationError("max_completion_repairs cannot be negative")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ConfigurationError("timeout_seconds must be positive")
        known = set(self.input_model.model_fields)
        object.__setattr__(self, "context", dict(self.context))
        if not set(self.context) <= known or any(
            not isinstance(value, ContextField) for value in self.context.values()
        ):
            raise ConfigurationError(
                "Injected context must name input fields with ContextField values"
            )
        if any(
            self.input_model.model_fields[name].validation_alias not in (None, name)
            for name in self.context
        ):
            raise ConfigurationError(
                "Injected fields must use their Python field names without aliases"
            )
        if self.completion is not None:
            if self.output_model is None:
                raise ConfigurationError("Completion policy requires an output_model")
            if self.allow_partial or self.partial_output is not None:
                raise ConfigurationError("Use either Completion or the legacy partial options")
        if self.context_fields is not None:
            selected = set(self.context_fields)
            required = {k for k, v in self.input_model.model_fields.items() if v.is_required()}
            if not selected <= known or not required <= selected:
                raise ConfigurationError("context_fields must contain all required input fields")
            if not set(self.context) <= selected:
                raise ConfigurationError("Injected context fields must be selected")
        if self.context_policies is not None:
            protected = set(self.context_policies.protected_fields)
            if not protected <= (
                known if self.context_fields is None else set(self.context_fields)
            ):
                raise ConfigurationError("Protected fields must be selected input fields")

    def as_tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        on_error: Literal["raise", "return"] = "raise",
        input_mapper: Callable[..., Any] | None = None,
        arguments: type[BaseModel] | None = None,
    ) -> StageTool:
        return StageTool(
            self,
            name or self.name,
            description or self.instructions,
            on_error,
            input_mapper,
            arguments,
        )


@dataclass(frozen=True)
class StageTool:
    stage: Stage[Any, Any]
    name: str
    description: str = ""
    on_error: Literal["raise", "return"] = "raise"
    input_mapper: Callable[..., Any] | None = None
    argument_model: type[BaseModel] | None = None

    def __post_init__(self) -> None:
        validate_name(self.name)
        if self.on_error not in ("raise", "return"):
            raise ConfigurationError("on_error must be 'raise' or 'return'")
        if self.argument_model is not None and (
            not isinstance(self.argument_model, type)
            or not issubclass(self.argument_model, BaseModel)
        ):
            raise ConfigurationError("Substage arguments must be a Pydantic model class")
        if self.stage.context and set(self.arguments.model_fields) & set(self.stage.context):
            raise ConfigurationError("Injected fields must not be exposed as substage arguments")

    @property
    def arguments(self) -> type[BaseModel]:
        return self.argument_model or self.stage.input_model

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.arguments.model_json_schema())

    @property
    def reads(self) -> frozenset[str]:
        return frozenset(self.stage.resources or ()).union(*(t.reads for t in self.stage.tools))

    @property
    def writes(self) -> frozenset[str]:
        return frozenset().union(*(t.writes for t in self.stage.tools))
