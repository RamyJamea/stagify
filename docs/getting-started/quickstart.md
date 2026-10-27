# Your first stage with Gemini

Use `gemini-3.8-flash` through **Gemini Interactions** to choose a typed application tool and submit a validated answer. The code below calls Gemini; the response walkthrough is explicitly simulated to show the flow.

## Install and configure

```bash
uv add "stagify[google]"
```

Set `GEMINI_API_KEY` in your shell or secret manager. Stagify does not load `.env` files automatically. You need access to `gemini-3.8-flash` for a live run.

## Save and run

Save this complete example as `gemini.py`:

```python
--8<-- "examples/gemini.py"
```

```bash
uv run python gemini.py
```

The example omits `temperature` and `top_p` by passing `None`, following [Google's Gemini 3.8 guidance](https://ai.google.dev/gemini-api/docs/latest-model). Tool arguments and completion output are validated against Pydantic schemas.

## Simulated Gemini responses

This excerpt illustrates two Interactions responses. IDs are examples; unrelated fields and thought steps are omitted for readability. These are **simulated responses, not a recorded API run**.

First, Gemini selects the application tool:

```json
{
  "model": "gemini-3.8-flash",
  "status": "requires_action",
  "steps": [
    {"type": "function_call", "id": "call-double", "name": "double", "arguments": {"value": 21}}
  ]
}
```

Stagify validates `Number`, executes `double`, stores the exact result as evidence, and returns it as a matching function result. Gemini then submits the typed stage output:

```json
{
  "model": "gemini-3.8-flash",
  "status": "requires_action",
  "steps": [
    {"type": "function_call", "id": "call-finish", "name": "complete_stage", "arguments": {"value": 42}}
  ]
}
```

The application prints `{'value': 42}` and the returned usage counters. A real run's tool choices, call count, token usage, and latency can vary. The adapter preserves full replay steps and signatures even though this walkthrough abbreviates them.

## Run the same code with simulated responses

From a source checkout:

```bash
uv sync --locked --all-extras
uv run python scripts/simulate_gemini.py examples/gemini.py
```

The simulator intercepts HTTP requests to Interactions with `httpx.MockTransport`. The example still uses the real `GoogleProvider` and Google SDK. No Gemini credentials or live API requests are needed in this mode. Fixture usage is labeled simulated; it is not a token estimate or billing measurement.

`@tool` handlers accept `(args: PydanticModel, ctx: ToolContext)`. With an output model, `complete_stage` must be submitted alone. For a text-only stage, omit `output_model`; a text response without tool calls can complete it.

Next: learn the [core concepts](concepts.md), then [expose a stage as a tool](../guides/substages.md).
