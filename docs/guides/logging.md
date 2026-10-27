# Structured logging

Stagify emits `structlog` events and leaves the host application's global logging configuration to you.

## Configure JSON output

Call this during application startup, before creating the runner:

```python
import logging
import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)
```

Use `structlog.dev.ConsoleRenderer()` instead of `JSONRenderer()` for a local terminal.

## Enable verbose events

`Runner(provider, verbose=False)` is the default. It emits stage/run terminal summaries, warnings, and errors. `verbose=True` adds DEBUG events for provider requests, tool execution, and context transformations. Configure your application to allow DEBUG messages as well:

```python
# In the configuration above, use logging.DEBUG for the filtering bound logger.
runner = Runner(provider, verbose=True)
```

Run-level `run(..., verbose=...)` takes precedence. A stage's explicit verbosity overrides inherited verbosity; otherwise the child inherits its parent's effective setting, and the root falls back to the runner.

Changing a filtering wrapper after cached loggers have been created may require recreating those loggers. Configure the application once at startup.

## Correlate events

Stage events bind `run_id`, `stage_name`, `stage_invocation_id`, and `parent_invocation_id`. Terminal events include status, duration, and usage. Request events include purpose and attempt; tool events include names and call IDs. Context events identify offloads, compactions, and invalidated summaries.

For example, a terminal JSON event has this shape (IDs and values vary):

```json
{"event":"stage.completed","stage_name":"analysis","run_id":"...","stage_invocation_id":"...","parent_invocation_id":null,"status":"completed","duration_ms":12.4,"error_code":null,"usage":{"model_calls":2,"tool_calls":2,"input_tokens":200,"output_tokens":40,"total_tokens":240,"complete":true}}
```

Stagify's built-in events do not log raw prompts, tool payloads, or API keys. Application tools, custom loggers, and SDK logging have their own behavior. `Runner(logger=...)` accepts an application-supplied compatible bound logger.
