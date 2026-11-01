# Compose a workflow

Use a `Workflow` for a deterministic sequence of stages. Each `Step` binds its
input from the validated workflow input, earlier typed outputs, or application
resources. The existing runner executes every step and child with one run ID,
usage ledger, model/tool/stage invocation budget, and deadline.

```python
from pydantic import BaseModel
from stagify import Runner, Stage, Step, Workflow

class Task(BaseModel):
    task: str

explore = Stage("explore", "Identify the investigation scope.", Task)
write = Stage("write", "Write a report from the supplied observations.", Task)
report = Workflow("report", Task, (
    Step(explore),
    Step(write, input=lambda state: {"task": state.output("explore")}),
))

async def generate_report(provider, question):
    async with Runner(provider) as runner:
        result = await runner.run(report, {"task": question})
    return result.output, result.usage.total
```

An omitted step input binding passes the workflow input to the stage. A binding
may be sync or async; its result is validated against the next stage's input
model. Invalid input or a binding failure stops execution. Stages must have
unique names in a workflow. Workflows are sequential, not a general graph engine.

`WorkflowContext.input` is the initial Pydantic model. `output(name)` returns a
previous stage's actual output, and `results[name]` exposes its full diagnostic
result. `resource(name)` reads shared resources for trusted application binding
code. Model tools and injected context sources still use declared resource grants.

## Results, partial work, and failures

`WorkflowResult.output` defaults to the last step's output. Supply a sync or async
`Workflow(output=...)` binding to assemble another application result.

`result.steps` contains top-level stage results; their children retain delegated
invocations. Read `result.usage.total` once for combined usage. Summaries and
retries consume the same shared budget. Unknown usage stays unknown.

A workflow can continue from a stage's explicitly permitted partial output, and
its overall status remains `partial`, even if the writer succeeds. Inspect status.
Use [Completion](completion.md) to specify exactly which local failures may
produce a supported partial result.

Typed errors retain their original class and `error.result` stage snapshot.
`error.workflow_result` contains completed and failed steps plus aggregate usage.
Binding failures become safe `StageExecutionError` exceptions retaining the
original cause. Cancellation propagates; the latest workflow snapshot is available
on `RunContext.last_workflow_result`.

Separate calls to `Runner.run(stage, ...)` still start independent budgets.
Sharing a `RunContext` between those calls shares resources and memory, not their
ledgers. Use one workflow when the entire sequence needs a single budget.

## Provider lifecycle

`async with Runner(provider) as runner` closes the default provider and any
stage-specific providers used during execution, once per provider object.
Cleanup attempts continue if one close fails. A close failure does not replace
an existing execution error or cancellation.

Bare `Runner.run(...)` preserves application ownership of providers. Call
`runner.aclose()` or close providers yourself. A runner cannot close while runs
are active. An externally supplied Google SDK client remains owned by its caller.

## Complete analysis example

The [reference analysis workflow](../tutorials/analysis-workflow.md) explores,
delegates cleaning, saves a supported finding, and writes Markdown. It has no
application runner, provider wrapper, result translator, or manual stage loop.
