# Errors and limits

Treat failure as a returned diagnostic snapshot plus a typed exception. A successful root run returns `StageResult`; most failures raise a `StagifyError` subclass.

```python
from stagify.errors import StagifyError

try:
    result = await runner.run(stage, stage_input, context=context)
except StagifyError as error:
    print(error.code, error.details)
    if error.result is not None:
        print(error.result.status, error.result.usage.total.model_dump())
```

Errors raised before an invocation starts, such as reusing an active context, may not have a snapshot.

## Configure execution limits

```python
from stagify import RunLimits, Runner

limits = RunLimits(
    max_model_calls=40,
    max_tool_calls=80,
    max_input_tokens=24000,
    max_output_tokens=4096,
    max_depth=4,
    max_model_retries=2,
    retry_delay=0.1,
    timeout_seconds=120,
)
```

Pass `limits=limits` to `Runner`. Root/child requests share run call caps and the root deadline. Stage `max_model_calls` limits that invocation's own requests, including its summaries and retries. Stage `timeout_seconds` bounds the local invocation and cannot extend the root deadline. Input/output token settings are per-request allocations, not cumulative billing caps.

On the final available request for a typed stage, only `complete_stage` remains available. Budget planning should leave room for summaries, retries, and final submission.

## Recovery depends on the failure

| Failure | Runtime behavior | Application response |
| --- | --- | --- |
| Invalid tool arguments | Sanitized feedback; handler is not executed | Improve schema or instructions if repeated |
| Invalid completion | Bounded repair, then `StageCompletionError` | Inspect contract and required memory |
| Typed transient provider error | Bounded exponential retry or provider delay | Tune limits; investigate sustained failures |
| Authentication/provider output error | Raise typed error | Correct credentials, API configuration, or adapter |
| Tool execution error | Raise `ToolExecutionError`; retain cause | Reconcile external effects before retrying |
| Context cannot fit | Raise `ContextBudgetExceeded` | Page results, enable suitable policies, or adjust allocation |
| Child fails | `SubstageError`, unless `on_error="return"` | Inspect child result and actual resource changes |

Already executed tools are not automatically repeated by provider retries. This does not provide exactly-once external writes or rollback. A failed writer may have changed resources, so revisions advance conservatively.

## Partial output

`Stage(allow_partial=True)` permits partial results on call-limit exhaustion or timeout. For `RunLimitExceeded`, `partial_output(context)` can supply a fallback; an output model validates that fallback. An invalid fallback raises `StageCompletionError`. Timeout partial results contain no fallback output in 0.1.0. Other failure classes still raise.

Always inspect `result.status` before treating output as complete.

## Cancellation

Cancellation propagates as `asyncio.CancelledError`. Child tasks are cancelled, and a root cancelled snapshot is stored on the supplied `RunContext.last_result`. A synchronous tool running in a worker thread may continue externally after cancellation. Reconcile those effects in the host application.

The [error reference](../reference/errors.md) lists stable codes and all exported error classes.
