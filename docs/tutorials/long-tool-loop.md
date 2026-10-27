# A long tool loop

Keep a long analysis loop within an input allocation while retaining exact observations. This tutorial combines a cleaner substage, twelve large batch reads, artifact offloading, historical summaries, current working memory, and an exact final calculation.

The provider is deterministic and the data is synthetic. It demonstrates runtime behavior; it does not measure a model's reasoning quality or prove comparative accuracy.

## Run the comparison

Install `stagify`, save the complete source below as `long_tool_loop.py`, and run:

```bash
uv run python long_tool_loop.py
```

The enabled run completes with `Total sales: 1830.0 across 60 rows.` It prints the child count, compaction count, summary-call count, and synthetic usage. The disabled run uses fresh data and the same request allocation, then stops with `ContextBudgetExceeded` as expected.

## What the example proves

1. The cleaner receives only its typed task and normalizes 60 rows through a declared writer.
2. Each batch returns five rows with deliberately long notes. Original outputs remain in canonical history and the evidence store.
3. The request compiler substitutes small previews and evidence IDs for those large batch outputs.
4. Older complete tool batches are summarized when the estimated request reaches its configured trigger. Two recent batches remain exact in the request view.
5. The final calculation reads the current resource using `Decimal`. The summary is not used as the source of the numeric answer.
6. A current `revenue` finding is required before analysis completes. Summary requests and cleaner requests appear in inclusive usage.

The source asserts each behavior, including the presence of actual compactions and offloaded request messages. CI executes this same file; the documentation includes it directly.

## Complete source

```python
--8<-- "examples/long_tool_loop.py"
```

## Adapt it to real models

Replace the scripted provider with [Gemini Interactions](../guides/providers.md). In this tutorial the script chooses exactly twelve batches; with a real model, your prompts, schemas, and completion validator must enforce the required coverage. A summary alone cannot prove every row was inspected.

For larger datasets, prefer tools that return useful bounded aggregates or pages from the start. Offloading retains the large result in process memory. Use evidence pointers for exact values and recompute findings after resource changes.

Use the [policy guide](../guides/context-management.md) to tune thresholds. Token estimates and these synthetic counters are not actual provider billing or a savings benchmark.
