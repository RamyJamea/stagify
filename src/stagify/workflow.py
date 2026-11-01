"""Deterministic stage composition over one runner ledger and resource scope."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import ErrorInfo, StageResult
from .errors import ConfigurationError
from .stages import Stage
from .state import RunContext
from .tools import validate_name
from .usage import StageUsage


@dataclass(frozen=True)
class WorkflowContext:
    input: BaseModel
    results: dict[str, StageResult[Any]]
    context: RunContext

    def output(self, name: str) -> Any:
        return self.results[name].output

    def resource(self, name: str) -> Any:
        return self.context.resources[name]


@dataclass(frozen=True)
class Step:
    stage: Stage[Any, Any]
    input: Callable[[WorkflowContext], BaseModel | dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stage, Stage):
            raise ConfigurationError("Step requires a Stage")
        if self.input is not None and not callable(self.input):
            raise ConfigurationError("Step input must be a binding function")


@dataclass(frozen=True)
class Workflow:
    name: str
    input_model: type[BaseModel]
    steps: tuple[Step, ...]
    output: Callable[[WorkflowContext], Any] | None = None

    def __post_init__(self) -> None:
        validate_name(self.name)
        if not isinstance(self.input_model, type) or not issubclass(self.input_model, BaseModel):
            raise ConfigurationError("Workflow input_model must be a Pydantic model class")
        object.__setattr__(self, "steps", tuple(self.steps))
        if not self.steps or any(not isinstance(step, Step) for step in self.steps):
            raise ConfigurationError("Workflow requires at least one Step")
        names = [step.stage.name for step in self.steps]
        if len(names) != len(set(names)):
            raise ConfigurationError("Workflow stage names must be unique")
        if self.output is not None and not callable(self.output):
            raise ConfigurationError("Workflow output must be a binding function")


class WorkflowResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    status: Literal["completed", "partial", "failed", "cancelled"]
    output: Any = None
    run_id: str
    workflow_name: str
    steps: dict[str, StageResult[Any]] = Field(default_factory=dict)
    usage: StageUsage = Field(default_factory=StageUsage)
    error: ErrorInfo | None = None
