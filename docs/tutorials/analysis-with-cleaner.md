# Analysis with a cleaner

Use `gemini-3.8-flash` to delegate normalization to a cleaner stage, calculate an exact total, and save a finding backed by current evidence. Both stages use Gemini Interactions with separate local transcripts.

## Run with Gemini

Install `stagify[google]`, set `GEMINI_API_KEY`, save the source below as `analysis_with_cleaner.py`, and run:

```bash
uv run python analysis_with_cleaner.py
```

The application prints the report and returned Gemini usage. The data has two rows totaling `24.0`; wording, tool choices, request count, and usage can vary in a real run.

## Simulated Gemini walkthrough

This is an illustrative sequence, not a recorded model trace:

| Step | Stage | Simulated Gemini selection | Context and state |
| --- | --- | --- | --- |
| 1 | Analysis | `clean_data(task="Normalize sales amount strings.")` | Parent supplies the cleaner's typed task |
| 2 | Cleaner | `normalize_amounts()` | Fresh child transcript; declared write access to sales |
| 3 | Cleaner | `complete_stage(text="Amounts normalized; all rows retained.")` | Sales revision becomes 1; parent receives child output/revisions |
| 4 | Analysis | `total_sales()` | Exact Decimal total from the current resource |
| 5 | Analysis | `save_memory(key="revenue", value="24.0", evidence_ids=[...])` | Finding references evidence from sales revision 1 |
| 6 | Analysis | `complete_stage(text="Total sales are 24.0 across both rows.")` | `required_memory` checks the finding is current |

The cleaner's tools and instructions are specific to preparation. It shares the run budget, resources, evidence store, and working memory with analysis.

## Complete source

```python
--8<-- "examples/analysis_with_cleaner.py"
```

## Replay simulated Interactions responses

From a source checkout, run the same example without live API requests:

```bash
uv sync --locked --all-extras
uv run python scripts/simulate_gemini.py examples/analysis_with_cleaner.py
```

The real Google SDK and Stagify adapter process simulated HTTP responses. This fixture uses four parent requests and two child requests. At 100 input and 20 output fixture tokens per request, inclusive usage is 720 simulated tokens. Those counters are not an observed Gemini bill or a prediction for live runs.

`result.children` contains the cleaner results. `ContextPolicies(enabled=True, protected_fields=("task",))` validates the input field but does not enable compression by itself. Continue to [a long tool loop](long-tool-loop.md) to see offloading and summarization.
