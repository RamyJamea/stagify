# Providers and Gemini

Stages use normalized requests and responses. The bundled model adapter uses **Gemini Interactions**, including opaque step replay. It calls `client.aio.interactions.create` with `store=False` and `stream=False`.

## Connect Gemini Interactions

```bash
uv add "stagify[google]"
```

Configure `GEMINI_API_KEY` and `GEMINI_MODEL` through your shell or secret manager. Choose a model identifier available to your account that supports Interactions. Stagify does not load `.env` files automatically.

Save and run this example:

```python
--8<-- "examples/gemini.py"
```

```bash
uv run python gemini.py
```

This example makes real provider calls. Model access, rate limits, and billing come from your Google account. The offline tutorials use scripted responses instead.

## Configuration and lifecycle

`GoogleProvider` defaults to `temperature=0.0`, `top_p=1.0`, and `thinking_level="low"`. Supply values supported by your selected model, or `None` to omit a setting. The SDK client connects lazily on the first request. The async context manager closes a client created by the adapter.

You may pass `client=` to reuse a configured compatible Google SDK client. You then own its lifecycle. Supply `ProviderCapabilities` if you know your deployment's input/output limits and context window; the adapter does not discover them automatically.

The adapter preserves response replay content, tool-call IDs, and thought signatures. It disables hidden SDK retries so the runner can account for retries. Its original provider implementation and regression coverage are documented in [design provenance](../EXTRACTION.md).

## Implement a custom provider

Implement the `Provider` protocol: a `name`, `capabilities`, and async `generate(ModelRequest) -> ModelResponse`.

```python
from stagify import ModelRequest, ModelResponse, ProviderCapabilities

class EchoProvider:
    name = "echo"
    capabilities = ProviderCapabilities(max_input_tokens=8000)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(text=str(request.messages[0].content))
```

This minimal provider works for a text-only stage; it does not implement tool selection. A real adapter must translate tool schemas, preserve matching call IDs, replay assistant calls and tool results, and normalize usage. Return `None` for unknown usage fields instead of inventing zeros.

Raise `ProviderTransientError(retry_after=...)` for retryable failures, `ProviderAuthenticationError` for authentication failures, and `ProviderOutputError` for malformed responses. Only typed transient failures receive the runner's bounded retries. Other provider failures propagate as typed errors or are wrapped in `StageExecutionError` for unexpected exceptions.

`native` is adapter-specific replay data. Do not transfer Google replay payloads to another API without translation. See the [provider API](../reference/providers.md).
