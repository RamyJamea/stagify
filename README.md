# Stagify

Staged tool workflows with explicit, optional context management.

Stagify provides typed stages and tools, stages exposed as tools, context
contracts, evidence memory, optional compression, structured logs, and token usage.
The Google adapter uses **Gemini Interactions**, extracted from the existing
application scripts. See [extraction details](docs/EXTRACTION.md).

## Install

Python 3.12 or newer is required.

```powershell
uv add stagify
```

For the Gemini Interactions adapter, include the Google extra:

```powershell
uv add "stagify[google]"
```

Version 0.1.0 is available on [PyPI](https://pypi.org/project/stagify/0.1.0/).
See [supported features and limitations](docs/STATUS.md) for this initial release.

## Typed stages and tools

```python
from pydantic import BaseModel
from stagify import Runner, Stage, ToolContext, tool
from stagify.providers.google import GoogleProvider

class Question(BaseModel):
    task: str

class Number(BaseModel):
    value: int

class Answer(BaseModel):
    text: str

@tool
def double(args: Number, ctx: ToolContext):
    """Double one integer."""
    return {"value": args.value * 2}

analysis = Stage(
    name="analysis",
    instructions="Answer the task using the available tools.",
    input_model=Question,
    output_model=Answer,
    tools=[double],
)

async def answer(model: str, api_key: str):
    async with GoogleProvider(model, api_key=api_key) as provider:
        result = await Runner(provider, verbose=False).run(
            analysis, {"task": "What is double 21?"}
        )
        return result.output, result.usage
```

Output models are submitted through a schema-backed complete_stage tool.
For a text stage, omit output_model. Inputs are validated before model calls.
Tools receive validated argument models and support synchronous or asynchronous
handlers. Tool instances are definitions; per-run resources belong in RunContext.

## A stage can also be a tool

```python
cleaner = Stage(
    name="cleaner",
    instructions="Perform only the requested preparation task.",
    input_model=Question,
    output_model=Answer,
    tools=[normalization_tool],
)

analysis = Stage(
    name="analysis",
    instructions="Analyze the data; delegate preparation when needed.",
    input_model=Question,
    output_model=Answer,
    tools=[cleaner.as_tool(name="clean_data"), calculation_tool],
)
```

The parent sees a tool schema and result. The child has its own validated input,
instructions, tools, context policies, completion, and transcript. Child calls
share run limits and usage accounting. Every call starts a fresh child invocation.
This example assumes application-defined normalization/calculation tools; a full
credential-free example is in [analysis_with_cleaner.py](examples/analysis_with_cleaner.py).

## Context policies are optional

```python
from stagify import ArtifactOffload, ContextPolicies, Summarize

policies = ContextPolicies(
    enabled=True,
    protected_fields=("task",),
    artifact_offload=ArtifactOffload(enabled=True, max_chars=4000),
    history=Summarize(enabled=True, recent_batches=3),
)

runner = Runner(provider, context_policies=policies, verbose=False)
result = await runner.run(analysis, {"task": "Analyze sales."})

# A baseline run with all context transformations disabled, including in children.
baseline = await runner.run(
    analysis, {"task": "Analyze sales."}, apply_context_policies=False
)
```

Runner policies are defaults. A stage may supply its own ContextPolicies.
The run-level override takes precedence; each individual policy's enabled flag
still applies. No compression or offloading happens by default. Disabling
policies keeps the stage's local transcript, while schema validation, resource
grants, completion checks, and hard execution/context limits remain active.

Stage input fields are preserved exactly in this release, including all selected
protected fields. context_fields can explicitly omit optional input fields;
required fields cannot be omitted. Original tool outputs and history remain in
memory even when the request view contains an artifact handle or summary.
Required content that cannot fit causes ContextBudgetExceeded.

History summaries use the configured provider and have bounded input/output
allocations. They cover older complete tool batches and retain a recent tail.
Summary calls count toward the run's limits and token usage. Compaction receipts
are returned in result.compactions.

## Evidence and resources

Declare resource reads/writes on tools, and supply the actual objects separately:

```python
from stagify import RunContext

@tool(reads={"sales"})
def count_sales(args: Question, ctx: ToolContext):
    return {"count": len(ctx.resource("sales"))}

context = RunContext(resources={"sales": application_sales_rows})
```

Successful tools record exact JSON-compatible evidence. Tools declared as writers
advance resource revisions; potentially mutating failures conservatively advance
them too. Failed input parsing never executes a tool. Writes and reads against
the same resource are serialized. These declarations are application contracts,
not a security sandbox around arbitrary Python code.

Set memory=True on a stage to expose read_evidence, list_evidence, save_memory,
and withdraw_memory. Evidence reads support JSON Pointer selection and list
pagination. Working entries use explicit versions when replacing values and
track their supporting evidence/resource revisions. A stage can require current
working entries through required_memory or an application completion validator.

## Usage returned at every stage

```python
result.usage.own       # This stage's provider requests, including its summaries
result.usage.children  # All descendant requests, counted once
result.usage.total     # Inclusive totals
result.usage.by_purpose
result.children       # Individual child-stage results
```

Counters include input, output, total, cached input, reasoning, and tool-use
tokens. Cached/reasoning/tool-use counts are breakdowns; do not add them blindly
to the total. Missing provider usage remains unknown, and complete=False marks
incomplete accounting (for example, a failed request with no usage response).

The Interactions adapter preserves the existing scripts' usage field mapping.
No monetary-cost estimate or provider-independent billing equivalence is claimed.
Developer results and logs contain usage; the full usage tree is not injected
into the parent model's tool-result messages.

## Logs and errors

Stagify uses structlog without changing the host's global configuration. The
verbose=False default emits terminal summaries, warnings, and errors. verbose=True
adds DEBUG events for requests, tools, policy decisions, and compactions. Enable
DEBUG in the application's logging configuration to display those details.
The run override takes precedence over stage and runner verbosity settings.

Logs carry run/stage/parent invocation identifiers and aggregate usage. Raw
prompts, tool payloads, and API keys are not logged. Applications choose JSON or
console rendering.

```python
from stagify.errors import StagifyError

try:
    result = await runner.run(analysis, prepared_input)
except StagifyError as error:
    print(error.code, error.details)
    failed_result = error.result
```

Recoverable tool argument errors become sanitized model feedback. Provider
transient errors retry within the model-call budget; already executed tools are
not repeated. The existing Interactions provider retains Retry-After, quota, and
malformed-tool-output handling and disables hidden SDK retries.

Invalid completion has a configurable repair limit. Child failures stop the
parent by default; as_tool(on_error="return") returns a structured failure to the
parent instead. Child failures still expose actual resource changes. Limits and
timeouts raise typed errors; allow_partial=True permits explicit partial results.
Cancellation propagates after storing a cancelled snapshot on the supplied
RunContext. There is no automatic rollback or exactly-once guarantee for arbitrary
external side effects.

## Run the examples and tests

```powershell
uv sync --locked --all-extras
uv run python examples/basic.py
uv run python examples/analysis_with_cleaner.py
uv run pytest -q
uv run ruff check src tests scripts examples
uv run ruff format --check src tests scripts examples
uv build --no-sources
uv run python scripts/check_distribution.py
```

The examples use ScriptedProvider and synthetic token counts. The Google SDK is
tested through mocked Interactions HTTP responses, including the original
provider regression tests. No paid model evaluation is required to run the suite.
CI checks Linux/Windows with Python 3.12-3.14 and verifies wheel installation away
from the checkout.

The [original roadmap](IMPLEMENTATION_PLAN.md) remains as design history.
[Research notes](docs/RESEARCH.md) acknowledge overlapping capabilities in existing
frameworks. Stagify does not yet have comparative real-model accuracy results.

## License

[MIT](LICENSE).
