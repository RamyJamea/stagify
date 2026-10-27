# Providers and Gemini

Stages use normalized requests and responses. The bundled adapter uses **Gemini Interactions**, including opaque step replay. It calls `client.aio.interactions.create` with `store=False` and `stream=False`.

## Connect Gemini 3.8 Flash

```bash
uv add "stagify[google]"
```

Configure `GEMINI_API_KEY` in your shell or secret manager. The examples explicitly select `gemini-3.8-flash`, a [stable model documented by Google](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash/). Stagify does not load `.env` files automatically.

Save this example as `gemini.py`:

```python
--8<-- "examples/gemini.py"
```

```bash
uv run python gemini.py
```

This calls your Google account. Access, rate limits, and billing depend on that account. For an explicitly simulated run from the source checkout, use `uv run python scripts/simulate_gemini.py examples/gemini.py`. The [quickstart](../getting-started/quickstart.md) shows simulated Interactions responses and explains that mode.

## Configuration and lifecycle

The adapter's existing defaults are `temperature=0.0`, `top_p=1.0`, and `thinking_level="low"`. The Gemini 3.8 examples explicitly pass **`temperature=None, top_p=None`**, which omits these deprecated sampling parameters from requests. This follows [Google's model migration guidance](https://ai.google.dev/gemini-api/docs/latest-model); the shared adapter defaults remain unchanged for existing applications.

The SDK connects lazily on the first request. Its async context manager closes an owned client. Pass `client=` to reuse a configured compatible Google SDK client, whose lifecycle remains your responsibility. Supply `ProviderCapabilities` for your deployment's limits; the adapter does not discover model limits automatically.

The adapter preserves replay content, call IDs, and thought signatures and disables hidden SDK retries. See [design provenance](../EXTRACTION.md) for the extracted implementation and regression coverage.

## Simulated Gemini responses

`scripts/simulate_gemini.py` intercepts Interactions HTTP requests with `httpx.MockTransport`, sets a local simulation key, and returns explicit response fixtures. The same examples still construct `GoogleProvider(model="gemini-3.8-flash", ...)`; they do not replace it with a different provider.

The harness checks the model name, stateless settings, omitted sampling parameters, and selected tool availability. Simulated usage is fixture data. No live model evaluation runs in CI.

## Implement a custom provider

Implement the [Provider protocol](../reference/providers.md): `name`, `capabilities`, and async `generate(ModelRequest) -> ModelResponse`. A real adapter translates tool schemas, preserves matching call IDs, replays tool results and native steps, and normalizes usage. Unknown usage fields stay `None`.

Raise `ProviderTransientError(retry_after=...)` for retryable failures, `ProviderAuthenticationError` for authentication failures, and `ProviderOutputError` for malformed responses. Only typed transient failures receive bounded retries. Unexpected exceptions are wrapped in `StageExecutionError`.

`native` is adapter-specific replay data. Do not transfer Google replay payloads to a different API without translation.
