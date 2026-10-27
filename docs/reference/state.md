# Context and evidence

All storage is process-local. Use the [evidence guide](../guides/evidence-memory.md) for the distinction between exact observations, working findings, and revisions.

## RunContext

`resources` maps names to application objects; revisions default to zero and may be supplied explicitly. `artifacts`, `memory`, `results`, and `last_result` are created by the context. Results are keyed by invocation ID. Reuse a context sequentially; concurrent root runs are rejected.

::: stagify.RunContext
    options:
      members: [__init__]

## ToolContext

The runner constructs this scoped context. `resource(name)` checks declared access. `touch(name)` requires a declared write and advances its revision. `save` validates supporting evidence and source revisions, then creates/replaces a working entry. Accessing low-level shared primitives is intended for trusted application code.

::: stagify.ToolContext
    options:
      members: [__init__, artifacts, memory, revisions, resource, touch, save]

## ArtifactStore

`record` creates a distinct evidence ID even for identical results. `get` returns a copy. `read` accepts JSON Pointer and list pagination; `limit` must be 1–100 and `offset` nonnegative. `index` returns a page of metadata. These application methods do not add the stage grant filtering performed by built-in model-facing tools.

::: stagify.ArtifactStore
    options:
      members: [record, get, read, index]

## WorkingState

`update` creates or replaces a keyed entry, or withdraws it with `withdraw=True`. Replacements require the current `expected_version`. This lower-level method accepts caller-supplied dependencies; use `ToolContext.save` for validated evidence-backed findings.

`snapshot` labels entries current/stale and omits withdrawn entries. `require_current` raises `StateConflictError` if a required entry is absent, withdrawn, or stale. `entries` contains latest records and `events` retains updates in memory.

::: stagify.WorkingState
    options:
      members: [update, snapshot, require_current]
