# Your first stage

Run a typed stage without an API key. This example uses `ScriptedProvider` to request an application tool and then submit a validated answer. The provider's choices and token counts are synthetic, so the result is reproducible.

## Install

```bash
uv add stagify
```

## Save and run

Save this complete example as `first_stage.py`:

```python
--8<-- "examples/first_stage.py"
```

```bash
uv run python first_stage.py
```

Alongside Stagify's completion logs, expect:

```text
Answer: 42
Model calls: 2
Tokens: 240
```

## What happened?

1. `Runner.run` validated the task against `Question`.
2. The first provider response requested `double`. Stagify validated its arguments and passed a `ToolContext` to the handler.
3. Stagify stored the tool's exact JSON result as evidence and appended a tool-result message.
4. The next response called `complete_stage`, which validated `Answer` and completed the invocation.
5. `StageResult` returned the typed output, history, evidence IDs, and usage.

`@tool` turns the handler into a tool definition. Its first parameter is a Pydantic argument model; the second is the execution context. Descriptions come from the function's docstring unless overridden.

For a text-only stage, omit `output_model`; a text response without tool calls can complete it. With an output model, completion uses `complete_stage`, submitted alone in a response.

## Move to a model

The stage and tool definitions work with `GoogleProvider` too. Replace the scripted provider with a [Gemini Interactions provider](../guides/providers.md). Actual model calls consume API usage, and tool selection becomes model-driven.

Next: learn the [core concepts](concepts.md), then [expose a stage as a tool](../guides/substages.md).
