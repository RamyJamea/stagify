# Results and usage

## StageResult

| Field | Meaning |
| --- | --- |
| `status` | `completed`, `partial`, `failed`, or `cancelled` |
| `output` | Validated output model, text, fallback output, or `None` |
| `run_id`, `stage_name` | Root execution ID and stage definition name |
| `invocation_id`, `parent_invocation_id` | Invocation tree identifiers |
| `usage` | Own, descendant, inclusive, and purpose-attributed counters |
| `error` | Optional `code`, `message`, and `details` |
| `history` | Full canonical local transcript |
| `children` | Direct child results, each retaining its descendants |
| `compactions` | Accepted summary batch ranges and estimated size changes |
| `resource_versions` | Shared resource revisions captured when the invocation ended |
| `evidence_ids` | Evidence created by this invocation, excluding descendants |

Typed errors generally attach this envelope as `error.result`. It is a diagnostic result, not a durable execution checkpoint. Treat histories, errors, and outputs as potentially sensitive application data when storing them.

::: stagify.StageResult
    options:
      members: false

## StageUsage

`own` counts the invocation, `children` counts all descendants, and `total` counts both. `by_purpose` is inclusive provider-request accounting. Do not sum every node's inclusive total: that would count descendants repeatedly.

::: stagify.StageUsage
    options:
      members: false

## TokenUsage

All six token fields are nullable nonnegative integers. Total is derived from input plus output when both are known and no total was supplied. Optional breakdowns are not additive billing categories.

::: stagify.TokenUsage
    options:
      members: false

## UsageTotals

Adds `model_calls`, `tool_calls`, and `complete`. Completion attempts count as tool calls. `complete` describes availability of input/output accounting, not whether the agent task completed successfully.

::: stagify.UsageTotals
    options:
      members: false

See [token usage](../guides/usage.md) for examples and unknown-field aggregation.
