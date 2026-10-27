# Evidence and working memory

Use evidence for exact observations and working memory for findings that can be replaced or withdrawn.

## Evidence records

Successful application tools record their JSON-compatible result in `RunContext.artifacts`. Each record has a unique ID, tool arguments, source resource revisions, and a content hash. The corresponding tool-result message includes `evidence_id`.

Application code can retrieve exact output after a run:

```python
evidence = context.artifacts.get(result.evidence_ids[0])
print(evidence.data)
page = context.artifacts.read(evidence.id, pointer="/rows", offset=0, limit=5)
```

Here `context` is the `RunContext` passed to the runner, and `result` is its `StageResult`. `result.evidence_ids` contains that invocation's records; child IDs are available through child results. `get` returns a copy. `read` supports JSON Pointer and paginates lists. An oversized selection raises `EvidenceError`; request a narrower pointer or smaller page.

## Expose model-facing memory tools

Set `memory=True` on a stage to add these reserved tools:

| Tool | Arguments | Behavior |
| --- | --- | --- |
| `list_evidence` | `offset=0`, `limit=20` (1–100) | List evidence metadata within the stage's resource grant |
| `read_evidence` | `evidence_id`, `pointer=""`, `offset=0`, `limit=25` (1–100) | Read an exact selected value or list page |
| `save_memory` | `key`, `value`, `evidence_ids`, optional `expected_version`, `kind="finding"` | Create or replace a supported finding |
| `withdraw_memory` | `key`, `expected_version` | Retract an existing finding |

Evidence read responses are bounded by `artifact_offload.max_chars`, even if offloading is disabled. Do not reuse these reserved names for application tools.

## Replace a finding instead of appending forever

A model can submit:

```json
{"key": "revenue", "value": "24.0", "evidence_ids": ["an-evidence-id"]}
```

The ID must refer to an actual current record accessible to the stage. The response returns the key, version, and status. To replace version 1, supply `expected_version: 1`; the entry becomes version 2. A missing or outdated expected version raises `StateConflictError`. A withdrawal uses the current version too.

`ToolContext.save` provides the same supported-entry validation to application tools. The lower-level `WorkingState.update` is an application primitive: callers supply dependencies themselves, so it does not perform the evidence validation of `save`.

## Resource changes and stale findings

Each declared resource starts at a revision, normally 0. A writer advances its revision. Evidence records the revisions at execution, and saved findings inherit those dependencies.

If sales change from revision 0 to 1, a finding based on sales revision 0 is **stale**. It stays visible with that status rather than disappearing. Refresh the observation and replace the finding with current evidence.

`required_memory=("revenue",)` prevents completion until the named entry exists and is current. It validates dependency freshness, not the semantic correctness of the claim.

External changes made outside Stagify's tools require your application to keep revisions consistent. Use a fresh context or explicitly update the relevant revision before continuing. In-memory history, artifacts, and memory are lost when the process ends; result snapshots are not durable resume checkpoints.

See [analysis with a cleaner](../tutorials/analysis-with-cleaner.md) for evidence-backed completion after a resource mutation.
