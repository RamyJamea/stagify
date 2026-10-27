# Analysis with a cleaner

Build a parent analysis stage that delegates normalization, calculates an exact total, and saves a finding backed by current evidence. This example uses two sales rows and a scripted provider, so it needs no API key.

## Run it

Install `stagify`, save the complete source below as `analysis_with_cleaner.py`, and run:

```bash
uv run python analysis_with_cleaner.py
```

The report is `Total sales are 24.0 across both rows.` The example also prints synthetic usage and asserts the resulting revision, memory, child count, and request count.

## Follow the boundaries

| Step | Stage | Operation | Context and state |
| --- | --- | --- | --- |
| 1 | Analysis | Call `clean_data` | Parent supplies the cleaner's typed task |
| 2 | Cleaner | Call `normalize_amounts` | Fresh child transcript; declared write access to sales |
| 3 | Cleaner | Submit completion | Sales revision becomes 1; parent receives child output/revisions |
| 4 | Analysis | Call `total_sales` | Exact Decimal total from current resource |
| 5 | Analysis | Call `save_memory` | Save `revenue` with evidence from sales revision 1 |
| 6 | Analysis | Submit completion | `required_memory` checks the finding is current |

The cleaner does not decide what the parent should conclude. Its instruction scope and tools are specific to preparation. Its execution still shares the run budget, resources, evidence store, and working memory.

## Complete source

```python
--8<-- "examples/analysis_with_cleaner.py"
```

## Inspect the returned result

`result.children[0]` contains the cleaner's full stage result. `result.usage.own.model_calls` is 4, `children.model_calls` is 2, and `total.model_calls` is 6. The synthetic inclusive total is 720 tokens.

`ContextPolicies(enabled=True, protected_fields=("task",))` validates the selected input field but does not enable compression by itself. This short example intentionally has neither offloading nor summarization enabled. Continue to [a long tool loop](long-tool-loop.md) to see both transformations.
