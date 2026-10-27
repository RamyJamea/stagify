# A long tool loop with Gemini

Use `gemini-3.8-flash` with a cleaner substage, large batch reads, artifact offloading, history summaries, working memory, and an exact final calculation. The code uses Gemini Interactions; an offline mode replays simulated Interactions responses through the real SDK.

## Run with Gemini

Install `stagify[google]`, set `GEMINI_API_KEY`, save the source below as `long_tool_loop.py`, and run:

```bash
uv run python long_tool_loop.py
```

This runs an enabled-policy analysis and a fresh policies-disabled comparison. Both use your provider account in live mode. Request counts, summary quality, and token usage depend on the model's choices.

## Simulated response sequence

The replay fixture selects these tool calls for `gemini-3.8-flash`:

1. Analysis calls `clean_data`; the cleaner calls `normalize`, then submits completion.
2. Analysis calls `read_batch` for offsets 0, 5, 10, …, 55, reading all 60 rows.
3. Large results enter later requests as previews and evidence IDs. The compiler requests a historical summary when its configured threshold is reached.
4. Analysis calls `compute_total`, which calculates `1830.0` using `Decimal` from the current resource.
5. Analysis saves a current `revenue` finding and submits the final report.

The simulated report is `Total sales: 1830.0 across 60 rows.` The fixture verifies that at least one summary request and offloaded result occurred. The disabled comparison exceeds the same input allocation. These are simulation results, not a model quality or savings benchmark.

## Complete source

```python
--8<-- "examples/long_tool_loop.py"
```

## Run without live API requests

From a source checkout:

```bash
uv sync --locked --all-extras
uv run python scripts/simulate_gemini.py examples/long_tool_loop.py
```

The simulator replaces HTTP transport, while the Google SDK still serializes requests, parses responses, replays thought/tool steps, and supplies usage to Stagify. Its banner and output identify fixture counters as simulated.

## Enforce coverage and preserve evidence

The completion validator checks exact batch evidence to ensure all 60 rows were read at the current resource revision. A historical summary alone cannot prove row coverage. The final calculation reads current data directly; it does not calculate from a model-written summary.

Original results stay in canonical history and process-local evidence storage. With a real model, a run can fail a limit or completion check; summaries and output wording are not deterministic. For larger datasets, return useful bounded aggregates or pages from the start and retrieve exact fields through evidence pointers.

See [context policies](../guides/context-management.md) for thresholds and precedence. Token sizing is estimated, and simulation counters are not actual provider billing.
