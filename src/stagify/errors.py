"""Stable errors with safe model-facing messages and recoverable result snapshots."""

from __future__ import annotations

from typing import Any


class StagifyError(Exception):
    code = "stagify_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}
        self.result: Any = None


class ConfigurationError(StagifyError):
    code = "configuration_error"


class ContextValidationError(StagifyError):
    code = "context_validation_error"


class ContextBudgetExceeded(StagifyError):
    code = "context_budget_exceeded"


class ToolInputError(StagifyError):
    code = "invalid_tool_input"


class ToolExecutionError(StagifyError):
    code = "tool_execution_error"


class StageExecutionError(StagifyError):
    code = "stage_execution_error"


class ProviderError(StagifyError):
    code = "provider_error"


class ProviderTransientError(ProviderError):
    code = "provider_transient_error"

    def __init__(
        self, message: str = "Temporary provider failure", *, retry_after: float | None = None
    ):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderAuthenticationError(ProviderError):
    code = "provider_authentication_error"


class ProviderOutputError(ProviderError):
    code = "provider_output_error"


class StageCompletionError(StagifyError):
    code = "invalid_stage_completion"


class StateConflictError(StagifyError):
    code = "state_conflict"


class EvidenceError(ToolInputError):
    code = "invalid_evidence"


class RunLimitExceeded(StagifyError):
    code = "run_limit_exceeded"


class StageModelLimitExceeded(RunLimitExceeded):
    """The current stage consumed its own model-call allocation."""

    code = "stage_model_limit_exceeded"


class StageTimeoutError(StagifyError):
    code = "stage_timeout"


class SubstageError(StagifyError):
    code = "substage_error"
