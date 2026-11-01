# A native analysis harness

The runnable example uses Stagify for the coordination that an application
otherwise writes itself:

1. Explore the supplied catalog.
2. Let analysis delegate source preparation to a cleaner.
3. Refresh analysis context after the resource changes.
4. Calculate an exact total and save it with supporting evidence.
5. Accept an empty completion submission and build the brief from current memory.
6. Write Markdown from that brief.

The application supplies Pydantic schemas, two sales tools, a brief formatter,
and declarative stages. It contains no custom provider, ReAct loop, stage runner,
evidence store, result translator, invocation counter, or provider cleanup loop.

## Run without a model account

From the source checkout:

```bash
uv sync --locked --all-extras
uv run python scripts/simulate_gemini.py examples/analysis_workflow.py
```

This exercises the real Google SDK and Stagify Interactions adapter over simulated
HTTP responses for `gemini-3.8-flash`. No paid requests occur. Model replies and
usage numbers are fixture data, not an accuracy benchmark.

Expected output includes:

```text
# Sales report

Total recorded sales: 24.0. Export completeness is unknown.
Verified 8 simulated Interactions HTTP requests through the real Google SDK and Stagify adapter.
```

The cleaner starts with revision zero; after normalization both cleaner and
analysis expose revision one. Combined usage counts all eight requests once,
including the two cleaner requests.

## Read the complete source

```python
--8<-- "examples/analysis_workflow.py"
```

## Run against Gemini

Set `GEMINI_API_KEY`, then run:

```bash
uv run python examples/analysis_workflow.py
```

This makes real calls to your Google account. Actual choices and usage may vary.
The framework validates schemas, provenance and freshness; application-specific
correctness checks remain your responsibility.

The example's storage is process-local. Add application loading and delivery
around it when integrating with a service; calculations, source formats, chart
rendering and deployment remain application concerns.

See [workflows](../guides/workflows.md), [context injection](../guides/context-fields.md),
and [completion policy](../guides/completion.md) for the individual contracts.
