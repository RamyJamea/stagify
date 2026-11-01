# Inject and update stage context

Model arguments and application context have different owners. A cleaner model
can choose a task; the application supplies its current catalog and revision.

```python
from pydantic import BaseModel, ConfigDict
from stagify import ContextField, Stage

class CleaningTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str

class CleaningInput(CleaningTask):
    catalog: dict
    revision: int

class Summary(BaseModel):
    text: str

cleaner = Stage(
    "clean", "Prepare the requested source fields.", CleaningInput, Summary,
    resources={"dataset"},
    context={
        "catalog": ContextField(
            lambda ctx: ctx.resource("dataset").catalog(),
            depends_on=("dataset",), protected=True,
        ),
        "revision": ContextField(lambda ctx: ctx.revisions["dataset"]),
    },
)
clean_data = cleaner.as_tool(name="clean_data", arguments=CleaningTask)
```

Only `CleaningTask` enters the parent model's tool schema. After argument validation,
the child loads its own injected values under its resource grants. No
`input_mapper`, optional catalog defaults, or model-supplied revision is needed.
The application still defines tools that perform preparation.

Injected sources override caller values, execute before initial input validation,
and refresh between model turns. Sources accept a `ToolContext` and may be async.
The complete updated input must validate before it is sent. A failed refresh
retains the last committed context in the diagnostic snapshot.

## Update rules

| Rule | Behavior |
| --- | --- |
| `replace` | Reload before each agent turn; with dependencies, reload only when their revisions change |
| `preserve` | Load once for this invocation and retain the exact value |
| `append` | Append a list delta once for each observed dependency-version change, including an initial delta |

Append sources must declare `depends_on` and return only new list entries. Stagify
does not deduplicate events or infer a stream cursor. Every child invocation gets
its own field state. A preserved value is an initial snapshot, not a guarantee
that an underlying resource remains current.

Resource dependencies must be inside the stage's grant. Tool `writes` declarations
advance the existing framework revisions; applications should use that revision
system for these field dependencies. Sources are trusted application code and
should read state without mutating it.

Injected fields use unaliased Python field names. Ordinary input fields can use
Pydantic aliases. Explicitly forbidding aliases on injected fields prevents a
caller alias from overriding an application-owned value.

## Compression and selected fields

`protected=True` contributes the field to the stage's protected field set.
Existing `ContextPolicies`, offload, summarization, and per-run policy overrides
continue to apply. All selected input fields remain exact: per-field lossy
summarization is not added by this feature.

Refreshed input is projected into the next request; canonical history retains
the initial input and original tool turns. `StageResult.context` contains the
latest committed selected input. History summaries still invalidate when
resource revisions change.

Growth from append fields is bounded by the existing request input budget.
Stagify raises `ContextBudgetExceeded` if required exact fields cannot fit.

## Existing input mappers

`as_tool(input_mapper=...)` remains supported for application-specific adaptation.
`arguments=...` selects its model-facing schema; injected child fields resolve
after mapping and still override mapped values.
