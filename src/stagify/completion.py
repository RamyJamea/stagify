"""Explicit submission schemas, state-derived outputs, and partial-result policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from .errors import (
    ConfigurationError,
    ContextBudgetExceeded,
    StageModelLimitExceeded,
    StageTimeoutError,
    StagifyError,
)


@dataclass(frozen=True)
class Completion:
    arguments: type[BaseModel] | None = None
    output: Callable[..., Any] | None = None
    required_memory: tuple[str, ...] = ()
    partial_on: tuple[type[StagifyError], ...] = ()
    partial_output: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        if self.arguments is not None and (
            not isinstance(self.arguments, type) or not issubclass(self.arguments, BaseModel)
        ):
            raise ConfigurationError("Completion arguments must be a Pydantic model class")
        allowed = {StageModelLimitExceeded, ContextBudgetExceeded, StageTimeoutError}
        if any(error not in allowed for error in self.partial_on):
            raise ConfigurationError(
                "Partial output is limited to explicit stage budget/timeout errors"
            )
        if bool(self.partial_on) != (self.partial_output is not None):
            raise ConfigurationError("partial_on and partial_output must be supplied together")
