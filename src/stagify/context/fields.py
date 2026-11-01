"""Application-injected fields with explicit update and resource dependencies."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from ..contracts import json_data
from ..errors import ConfigurationError, ContextValidationError
from ..state import ToolContext


@dataclass(frozen=True)
class ContextField:
    source: Callable[[ToolContext], Any]
    update: Literal["replace", "preserve", "append"] = "replace"
    protected: bool = False
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not callable(self.source) or self.update not in {"replace", "preserve", "append"}:
            raise ConfigurationError("ContextField requires a source and a valid update rule")
        if self.update == "append" and not self.depends_on:
            raise ConfigurationError("Append sources require resource dependencies")


class ContextView:
    def __init__(
        self,
        model: type[BaseModel],
        value: BaseModel | dict[str, Any],
        fields: Mapping[str, ContextField],
        context: ToolContext,
        selected: tuple[str, ...] | None,
    ):
        self.model, self.fields, self.context, self.selected = model, fields, context, selected
        self.original = value
        self.values = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
        self.versions: dict[str, dict[str, int]] = {}
        self.initialized: set[str] = set()
        self.payload: dict[str, Any] | None = None

    async def refresh(self) -> dict[str, Any]:
        values, versions = deepcopy(self.values), dict(self.versions)
        changed = False
        for key, field in self.fields.items():
            if not set(field.depends_on) <= self.context.revisions.keys():
                raise ConfigurationError("Context field depends on an undeclared resource")
            current = {name: self.context.revisions[name] for name in field.depends_on}
            if key in self.initialized and (
                field.update == "preserve" or (field.depends_on and current == versions[key])
            ):
                continue
            value = field.source(self.context)
            if inspect.isawaitable(value):
                value = await value
            value = json_data(value)
            if field.update == "append":
                previous = values.get(key, []) if key in self.initialized else []
                if not isinstance(previous, list) or not isinstance(value, list):
                    raise ContextValidationError("Append context fields require list values")
                value = previous + value
            values[key], versions[key] = value, current
            changed = True
        if self.payload is not None and not changed:
            return deepcopy(self.payload)
        try:
            candidate = (
                self.original
                if not self.fields and isinstance(self.original, self.model)
                else values
            )
            validated = self.model.model_validate(candidate, by_name=True)
        except (ValidationError, ValueError, TypeError) as exc:
            raise ContextValidationError("Stage input does not satisfy its input_model") from exc
        # Commit sources and their versions only after the complete input validates.
        self.values, self.versions = values, versions
        self.initialized.update(self.fields)
        self.payload = validated.model_dump(
            mode="json",
            include=set(self.selected) if self.selected is not None else None,
        )
        return deepcopy(self.payload)
