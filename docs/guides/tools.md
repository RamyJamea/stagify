# Define tools

A tool connects model-selected arguments to application code. Use Pydantic to define arguments and return a JSON-compatible value.

```python
from pydantic import BaseModel, Field
from stagify import ToolContext, tool

class Page(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=100)

@tool(reads={"sales"})
def read_sales(args: Page, ctx: ToolContext):
    """Read a bounded page of sales rows."""
    rows = ctx.resource("sales")
    return {"rows": rows[args.offset:args.offset + args.limit]}
```

Add `read_sales` to a stage's `tools` and supply the resource:

```python
from stagify import RunContext

context = RunContext(resources={"sales": [{"amount": "10.50"}]})
```

## Execution and validation

Handlers accept exactly `(args, context)`. The decorator infers the Pydantic model from the first parameter's type annotation; use `arguments=Page` if it cannot resolve that annotation. Async handlers are awaited. Synchronous handlers run in `asyncio.to_thread`.

Invalid arguments return sanitized feedback to the model without executing the handler. Unexpected handler exceptions become `ToolExecutionError`. Return values must be JSON-compatible; avoid live objects such as database connections in results.

Successful application tools record evidence by default. The model receives an envelope containing `ok`, `data`, `evidence_id`, and `resource_versions`.

## Declare writes

Use `@tool(writes={"sales"})` for an operation that changes the resource. Writers can access the named resource, and Stagify advances its revision after execution. A potentially mutating failure conservatively advances revisions too. `ctx.touch("sales")` can explicitly advance a revision during an operation.

Reads and writes declared against the same resource are serialized by the runtime. A child stage's resource requirements must fit inside its parent's grant. An explicit `Stage(resources=...)` must cover its tools' requirements.

These are application contracts. A Python handler can still access globals or external systems. Enforce authorization in your application and implement idempotency where external writes require it.

## Provide a small preview

`projection=` supplies a preview when [artifact offloading](context-management.md) replaces a large result in a request view:

```python
@tool(reads={"sales"}, projection=lambda result: {"rows": len(result["rows"])})
def sales_preview(args: Page, ctx: ToolContext):
    """Read sales with a compact preview available for offloading."""
    rows = ctx.resource("sales")
    return {"rows": rows[args.offset:args.offset + args.limit]}
```

The original result remains in evidence. Keep previews small; oversized previews fall back to shape metadata. See the [complete tool API](../reference/runtime.md).
