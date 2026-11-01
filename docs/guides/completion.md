# Complete from saved state

A submission schema need not be the stage's output schema. This lets an analyst
submit `{}` while the application builds its output from validated saved state.

```python
from pydantic import BaseModel, ConfigDict
from stagify import Completion, Stage
from stagify.errors import StageModelLimitExceeded

class Task(BaseModel):
    task: str

class Done(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Report(BaseModel):
    text: str

def saved_report(ctx):
    value = ctx.memory.values(
        ctx.revisions, ("revenue",), require_current=True,
    )["revenue"]
    return Report(text=f"Recorded revenue: {value}.")

analysis = Stage(
    "analysis", "Save supported revenue, then submit {}.", Task, Report,
    resources={"sales"}, memory=True, max_model_calls=20,
    max_completion_repairs=0,
    completion=Completion(
        arguments=Done,
        output=lambda submission, ctx: saved_report(ctx),
        required_memory=("revenue",),
        partial_on=(StageModelLimitExceeded,),
        partial_output=lambda ctx: Report(
            text=saved_report(ctx).text + " Analysis coverage is incomplete.",
        ),
    ),
)
```

Add analytical tools that compute evidence for `save_memory`. The built-in memory
store retains evidence dependencies and marks entries stale after resource changes.
Evidence support and freshness do not establish semantic truth of a claim.

## Normal completion

The provider sees `Completion.arguments` as the `complete_stage` schema. Its
validated submission is passed to `output(submission, context)`. That result is
validated against `Stage.output_model`; required memory and the existing
`validate_completion` callback must also pass.

Omit `arguments` to use the stage's output model as the submission schema. Omit
`output` to use the validated submission as the output. Callbacks may be async.

`max_completion_repairs` continues to bound repair feedback. Set it to zero for
an invalid submission to fail immediately.

## Explicit partial output

Partial output is disabled by default. Supply both `partial_on` and
`partial_output` to permit specific failures:

- `StageModelLimitExceeded`: this invocation exhausted its own model allocation.
- `ContextBudgetExceeded`: its rendered context cannot fit.
- `StageTimeoutError`: its local deadline expired.

Matching is exact. Provider failures, invalid completions, child failures, global
call/tool/stage limits, and cancellation cannot be selected as partial outcomes.
A child exhausting its limit reaches its parent as `SubstageError`; it cannot
trigger the parent's local-budget fallback.

Partial output passes the same output schema, required memory and completion
validator as normal output. Missing or stale required support produces
`StageCompletionError`. Only the application can decide how to disclose incomplete
coverage; the example adds that disclosure without asking a model to rewrite findings.

`WorkingState.values(versions)` selects current values only. Use
`keys=(...)` to select specific entries and `require_current=True` to reject missing,
withdrawn, or stale selections. Full history remains available through the existing
memory snapshot and events APIs.

Legacy `allow_partial`/`partial_output` options remain supported. They cannot be
combined with `Completion`; prefer the explicit policy for new applications.
