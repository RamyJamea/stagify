"""Typed synchronous/asynchronous application tools."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel, ValidationError

from .contracts import ToolSpec
from .errors import ConfigurationError, ToolInputError
from .state import ToolContext


def validate_name(name: str) -> None:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", name) is None:
        raise ConfigurationError("Names must be 1-64 letters, digits, underscores or hyphens")


@dataclass(frozen=True)
class Tool:
    name: str
    arguments: type[BaseModel]
    handler: Callable[..., Any]
    description: str = ""
    reads: frozenset[str] = frozenset()
    writes: frozenset[str] = frozenset()
    projection: Callable[[Any], Any] | None = None
    record_evidence: bool = True

    def __post_init__(self) -> None:
        validate_name(self.name)
        if not isinstance(self.arguments, type) or not issubclass(self.arguments, BaseModel):
            raise ConfigurationError("Tool arguments must be a Pydantic model class")
        object.__setattr__(self, "reads", frozenset(self.reads))
        object.__setattr__(self, "writes", frozenset(self.writes))

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.arguments.model_json_schema())

    def parse(self, arguments: dict[str, Any]) -> BaseModel:
        try:
            return self.arguments.model_validate(arguments)
        except ValidationError as exc:
            fields = [".".join(map(str, e["loc"])) or "$" for e in exc.errors(include_input=False)]
            raise ToolInputError("Invalid arguments for fields: " + ", ".join(fields)) from exc

    async def invoke(self, arguments: BaseModel, context: ToolContext) -> Any:
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(arguments, context)
        result = await asyncio.to_thread(self.handler, arguments, context)
        return await result if inspect.isawaitable(result) else result


def tool(
    function: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    arguments: type[BaseModel] | None = None,
    description: str | None = None,
    reads: set[str] | frozenset[str] = frozenset(),
    writes: set[str] | frozenset[str] = frozenset(),
    projection: Callable[[Any], Any] | None = None,
) -> Any:
    """Decorate a function with signature (args: PydanticModel, ctx: ToolContext)."""

    def build(fn: Callable[..., Any]) -> Tool:
        parameters = list(inspect.signature(fn).parameters.values())
        if len(parameters) != 2:
            raise ConfigurationError("A tool function must accept exactly (args, context)")
        model = arguments
        if model is None:
            try:
                model = get_type_hints(fn).get(parameters[0].name)
            except (NameError, TypeError) as exc:
                raise ConfigurationError(
                    "Could not resolve arguments; supply arguments= explicitly"
                ) from exc
        return Tool(
            name or fn.__name__,
            model,
            fn,
            description or inspect.getdoc(fn) or "",
            frozenset(reads),
            frozenset(writes),
            projection,
        )

    return build(function) if function is not None else build
