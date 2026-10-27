# Token usage

Every stage returns its own usage and the usage of its descendants:

```python
print(result.usage.own.model_dump())
print(result.usage.children.model_dump())
print(result.usage.total.model_dump())
for child in result.children:
    print(child.stage_name, child.usage.total.model_dump())
```

| View | Counts |
| --- | --- |
| `own` | Requests and tools attributed to this invocation |
| `children` | All descendant invocations, counted once |
| `total` | This invocation plus all descendants |
| `by_purpose` | Inclusive provider-request usage grouped by purpose, such as `agent` or `summarize` |

The cleaner tutorial's simulated Gemini replay uses six HTTP response fixtures: four in analysis and two in the cleaner. At 100 input and 20 output tokens per request, analysis totals 720 simulated tokens: 480 own and 240 in children.

## Interpret the fields

`TokenUsage` contains `input_tokens`, `output_tokens`, `total_tokens`, `cached_input_tokens`, `reasoning_tokens`, and `tool_tokens`. When total is absent but input and output are known, Stagify derives total as input plus output.

Cached, reasoning, and tool-use values are provider-defined breakdowns. Do not add them to `total_tokens` as if they were independent billable amounts. Stagify does not calculate monetary cost or guarantee equivalent billing semantics across providers.

`model_calls` counts provider attempts, including retries and summary requests. `tool_calls` counts runtime tool-call attempts, including `complete_stage`; it is separate from the provider's `tool_tokens` field. `by_purpose` attributes provider requests; its `tool_calls` counters are zero, so use `own`, `children`, or `total` for executed-tool accounting.

## Unknown usage stays unknown

If any included request lacks a token field, its aggregate field remains `None`. A failed request may have no response usage. `complete=False` means at least one included request has unknown input or output usage. `complete=True` does not guarantee every optional breakdown is available.

Use this distinction in dashboards: `None` should display as unknown rather than zero. Model-call limits still count attempts with unknown usage.

On a typed failure, inspect `error.result.usage` if a result snapshot exists. Cancellation snapshots are available through the supplied context's `last_result`.

The runtime logs aggregate usage but does not send the full accounting tree back into the parent model's context. See [result and usage types](../reference/results.md) for the field reference.
