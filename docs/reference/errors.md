# Errors

Import specialized errors from `stagify.errors`. `StagifyError` is also exported from the package root. Its `details` contains structured diagnostics and `result` is an optional stage snapshot. Python's exception cause retains underlying failures where applicable.

| Class | Stable code |
| --- | --- |
| `StagifyError` | `stagify_error` |
| `ConfigurationError` | `configuration_error` |
| `ContextValidationError` | `context_validation_error` |
| `ContextBudgetExceeded` | `context_budget_exceeded` |
| `ToolInputError` | `invalid_tool_input` |
| `EvidenceError` | `invalid_evidence` |
| `ToolExecutionError` | `tool_execution_error` |
| `StageExecutionError` | `stage_execution_error` |
| `ProviderError` | `provider_error` |
| `ProviderTransientError` | `provider_transient_error` |
| `ProviderAuthenticationError` | `provider_authentication_error` |
| `ProviderOutputError` | `provider_output_error` |
| `StageCompletionError` | `invalid_stage_completion` |
| `StateConflictError` | `state_conflict` |
| `RunLimitExceeded` | `run_limit_exceeded` |
| `StageTimeoutError` | `stage_timeout` |
| `SubstageError` | `substage_error` |

::: stagify.StagifyError
    options:
      members: [__init__]

`ProviderTransientError(retry_after=...)` accepts an optional finite nonnegative retry delay in seconds. The runner validates the hint before sleeping.

::: stagify.errors.ProviderTransientError
    options:
      members: [__init__]

`EvidenceError` is a `ToolInputError`; provider-specific errors derive from `ProviderError`. Other listed classes derive directly from `StagifyError`. Most error constructors accept `message` and optional keyword `details`.

Refer to [errors and limits](../guides/errors.md) for which failures retry, return feedback, permit partial results, or stop a parent stage.
