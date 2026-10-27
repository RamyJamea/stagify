# Runner, stages, and tools

These signatures are generated from the checked-in Python source. Guides explain behavior; this reference lists the actual types and defaults for the current `0.1.1` API.

## Runner

Pass a provider, optional `RunLimits`, policy defaults, verbosity, and a compatible bound logger. `run` accepts a stage, a Pydantic instance or dictionary, and optional shared context and run overrides. It returns `StageResult`; typed failures usually attach a result to the exception.

::: stagify.Runner
    options:
      members: [__init__, run]

## Stage

| Option | Meaning |
| --- | --- |
| `name`, `instructions` | Invocation identity label and stage-specific instructions |
| `input_model`, `output_model` | Pydantic input contract and optional typed completion contract |
| `tools` | Application tools and stage-tool adapters |
| `context_fields` | Selected input fields; must include every required field |
| `context_policies` | Stage policy object replacing runner defaults |
| `memory`, `required_memory` | Enable built-in memory tools and require current findings at completion |
| `validate_completion` | Sync/async `(output, ToolContext)` callback; `False` rejects completion |
| `max_model_calls`, `max_completion_repairs` | Own-request cap and bounded completion repair count |
| `timeout_seconds` | Local deadline, bounded by the root deadline |
| `allow_partial`, `partial_output` | Partial results on limits/timeouts; fallback callback is used for call limits |
| `resources` | Explicit resource grant; defaults to tool requirements |
| `verbose` | Optional verbosity override |

::: stagify.Stage
    options:
      members: [as_tool]

## StageTool

Prefer `stage.as_tool()` to construct this adapter. `on_error` is `"raise"` or `"return"`. `input_mapper(parsed_args, parent_tool_context)` may be sync or async; its output is revalidated as child input.

::: stagify.StageTool
    options:
      members: [arguments, spec, reads, writes]

## Tool decorator

Decorate a handler accepting exactly `(args: PydanticModel, ctx: ToolContext)`. `reads` and `writes` declare resource access. `projection` provides a compact preview for artifact offloading. A docstring supplies the description unless one is passed explicitly.

::: stagify.tool

## Tool

The explicit definition also exposes `record_evidence`, which defaults to `True`; the decorator uses that default. `parse` validates raw arguments. `invoke` dispatches sync handlers to a worker thread and awaits async handlers. Use the runner for evidence, limits, and resource accounting rather than invoking application tools directly.

::: stagify.Tool
    options:
      members: [spec, parse, invoke]

Names must match `[A-Za-z_][A-Za-z0-9_-]{0,63}`. Stage tools cannot reuse reserved built-in names or duplicate another tool name within the stage.
