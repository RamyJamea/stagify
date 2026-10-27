# Stages and context contracts

Use a stage to give one part of your workflow a clear input, purpose, tool set, and completion contract.

```python
from pydantic import BaseModel
from stagify import Stage

class AnalysisInput(BaseModel):
    task: str
    tenant_id: str
    debug_notes: str = ""

class Report(BaseModel):
    conclusion: str

analysis = Stage(
    name="analysis",
    instructions="Answer the task using the available evidence.",
    input_model=AnalysisInput,
    output_model=Report,
    context_fields=("task", "tenant_id"),
    max_model_calls=20,
)
```

## Expected context for each stage

`input_model` defines the data callers must supply. Stagify validates input before requesting a model. Values follow your Pydantic model's validation and coercion rules; configure strict Pydantic fields if coercion is unsuitable.

By default every validated input field enters the request. `context_fields` selects fields to render. It must contain **all required fields**; it can omit optional fields such as `debug_notes`. Unknown field names fail configuration.

All selected input values remain exact after validation in 0.1.0. History summaries do not summarize these values. If required content cannot fit, Stagify raises `ContextBudgetExceeded` rather than dropping it.

Application resources belong in `RunContext(resources=...)` and are available to declared tools. They are not automatically serialized into stage input.

## Completion

With `output_model=Report`, the provider must call `complete_stage` with valid `Report` fields, alone in its response. Invalid completion receives bounded repair feedback. `max_completion_repairs` defaults to `1`; repairs still consume model requests.

Without an output model, a plain text response with no tool calls can complete a stage. Set `validate_completion` for application checks:

```python
def has_conclusion(output, context):
    return bool(output.conclusion.strip())
```

Pass that function as `validate_completion=has_conclusion`. It receives `(output, ToolContext)` and may return an awaitable. Returning `False` rejects completion. `required_memory=("revenue",)` additionally requires those entries to exist and be current.

## Handoff and reuse

For a fixed sequence, call `runner.run` twice and pass the first result's output into the next stage's input. Reuse a `RunContext` sequentially to retain resources, artifacts, and memory; each root call starts a new run and usage ledger. A single context cannot serve concurrent root runs.

For model-selected delegation, use [a stage as a tool](substages.md). Stage definitions can be reused; invocation histories and IDs are created per execution.

See [the stage API](../reference/runtime.md) for every constructor option.


## Stage providers and execution limits

`Stage(provider=...)` selects a provider for that stage, including when invoked
through `as_tool()`. Otherwise the runner's provider is used. The application
owns and closes stage-specific providers. `Stage(max_output_tokens=...)` bounds
that stage's response together with the runner and provider limits.

`Runner(min_interval_seconds=...)` waits before every provider attempt, including
retries, child requests and context summarization. It is per-run pacing, not a
distributed rate limiter.

`StageModelLimitExceeded` identifies exhaustion of a stage's own model-call
allocation. A final response without typed completion also raises this error;
an early unsubmitted response remains `ProviderOutputError`. Invalid submissions
remain completion errors. Child exhaustion is wrapped in `SubstageError`.

Provider failures on the last allowed attempt retain their provider error type,
even when `allow_partial=True`. They cannot become partial budget results.
