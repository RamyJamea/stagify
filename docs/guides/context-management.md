# Context policies

Long tool loops accumulate results, decisions, and repeated observations. Stagify compiles a request view before each provider call, so you can reduce what is sent while keeping the invocation's original history and evidence in memory.

## Enable only what you need

```python
from stagify import ArtifactOffload, ContextPolicies, Runner, Summarize

policies = ContextPolicies(
    enabled=True,
    protected_fields=("task",),
    artifact_offload=ArtifactOffload(enabled=True, max_chars=4000),
    history=Summarize(
        enabled=True,
        recent_batches=3,
        trigger_fraction=0.8,
        target_fraction=0.6,
        max_input_tokens=6000,
        max_output_tokens=1000,
    ),
)
```

Pass `context_policies=policies` to `Runner` or a `Stage`. For a stage that must retrieve offloaded results, enable `memory=True` to expose evidence-reading tools.

## Policy precedence

| Setting | Effect |
| --- | --- |
| No policy configuration | No offloading or summarization |
| Runner policies | Defaults for stages without their own policies |
| Stage policies | Replace the runner policy object for that stage |
| `run(..., apply_context_policies=False)` | Disable context transformations throughout that run, including children |
| `run(..., apply_context_policies=True)` | Enable the policy container throughout the run; individual policy switches still apply |

Disabling transformations does not disable input validation, evidence recording, enabled memory tools, completion checks, or hard limits. With policies disabled, `memory_keys` filtering is also bypassed.

## What stays exact?

All selected, validated stage input values stay exact in 0.1.0. `protected_fields` validates that named fields exist in the rendered input; it is not a separate per-field compressor. Required inputs cannot be omitted by `context_fields`.

Working memory entries are rendered as structured data. `memory_keys` can restrict which keys enter a request when policies are enabled; it is a selection setting, not an access-control boundary for shared memory.

Canonical history and stored tool outputs are retained. This costs process memory even when requests shrink. There is no persistent storage backend in this release.

## Offload large tool outputs

`ArtifactOffload` replaces large successful evidence-bearing tool messages in the request view with their ID, revisions, content hash, and a small preview. `max_chars` bounds the serialized message view. A tool's `projection` can provide a useful preview; otherwise Stagify uses shape metadata.

Enable memory tools and instruct the stage to use `read_evidence` for exact values. Offloading does not summarize or delete the source output. Page large evidence reads or select a narrower JSON Pointer, since evidence responses are bounded too.

## What does `history=Summarize(...)` mean?

It configures the **history reduction strategy**. It does not summarize a Python variable named `history` immediately.

Before a provider call, the compiler estimates request size. At `trigger_fraction` of the input allocation, it tries to reduce older complete assistant/tool batches toward `target_fraction`, retaining `recent_batches` at the end. Summaries include earlier summary data when extending a checkpoint.

Summary requests use the same provider and consume model-call budget and tokens. A checkpoint is accepted only if it is nonempty, fits its output allocation, and reduces request size. An oversized indivisible batch or an ineffective summary raises `ContextBudgetExceeded`. The recent tail can prevent reaching the target; the hard request budget still applies.

Changes to scoped resource revisions invalidate the checkpoint. The compiler can rebuild from retained canonical history. Invalidation helps avoid silently reusing an old summary; it does not make a new summary factually infallible.

Inspect `result.compactions` for batch ranges and estimated sizes before/after. Inspect `result.usage.by_purpose["summarize"]` when summary calls occurred.

## Budgeting

The input allocation is the minimum of `RunLimits.max_input_tokens`, the provider's declared input limit, and its context window minus reserved output capacity. Request size uses a conservative UTF-8 heuristic, **not a provider tokenizer**. Leave headroom for provider-specific formatting.

`max_input_tokens` limits each request, not cumulative input across a run. Model/tool call caps limit iteration. Required context that cannot fit fails explicitly.

Follow the [long-loop tutorial](../tutorials/long-tool-loop.md) to see a complete comparison with policies enabled and disabled.
