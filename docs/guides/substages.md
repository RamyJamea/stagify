# Stages as tools

A substage is both a stage and a tool: it runs its own loop, while the parent sees a tool definition and result.

```python
from pydantic import BaseModel
from stagify import Stage

class Task(BaseModel):
    task: str

class Summary(BaseModel):
    text: str

cleaner = Stage(
    "cleaner",
    "Describe the requested preparation work.",
    Task,
    Summary,
)
analysis = Stage(
    "analysis",
    "Delegate preparation when needed, then analyze the result.",
    Task,
    Summary,
    tools=[cleaner.as_tool(name="clean_data")],
)
```

This minimal definition demonstrates the boundary; add application tools to perform preparation. The [cleaner tutorial](../tutorials/analysis-with-cleaner.md) includes an actual resource mutation and a complete Gemini example with simulated-response replay.

## Isolation and sharing

| Private to the invocation | Shared within the run |
| --- | --- |
| Validated stage input and selected fields | Application resources and revisions |
| Instructions, tools, and local transcript | Evidence store and working memory |
| Context compiler and summary checkpoints | Root model/tool call limits and deadline |
| Local call limit and completion contract | Usage ledger, with separate stage attribution |

Each call starts a fresh child invocation. Its first message is its own validated input. Parent history is not implicitly copied. Stage policies override runner policy defaults; the root `apply_context_policies` override applies to descendants too.

The child's output envelope returns to the parent. Full child history and usage are available to application code in `result.children`; the full usage tree is not injected into parent model messages.

## Failure behavior

`cleaner.as_tool(on_error="raise")` is the default. A typed child failure becomes `SubstageError` in the parent, with the child error code and current resource revisions.

Choose `on_error="return"` to give the parent a structured failure response and let its loop continue. This does not undo resource changes. The developer can still inspect the child result. A partial child returns its status and `ok=False` in the tool envelope.

`input_mapper` can adapt validated tool arguments before the child starts. It receives `(parsed_args, parent_tool_context)` and may be async. Its output must satisfy the child's input model.

Recursive stage cycles and excessive depth are rejected. Design explicit handoffs instead of making a stage call itself.
