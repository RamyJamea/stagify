<p align="center">
  <img src="https://raw.githubusercontent.com/RamyJamea/stagify/v0.1.2/docs/assets/brand/stagify-original.jpg" width="280" alt="Stagify: a hand-drawn crew of four penguins">
</p>

# Stagify

Staged agent workflows with explicit context management.

Define typed stages and tools, expose stages as tools, and control the context
sent to a provider during long tool loops. Keep exact evidence available while
using optional artifact offloading and historical summaries.

**[Documentation](https://ramyjamea.github.io/stagify/)** ·
[Quickstart](https://ramyjamea.github.io/stagify/getting-started/quickstart/) ·
[PyPI](https://pypi.org/project/stagify/) ·
[Examples](https://github.com/RamyJamea/stagify/tree/main/examples)

## Install

Python 3.12 or newer is required.

```bash
uv add stagify
```

For the Gemini Interactions adapter:

```bash
uv add "stagify[google]"
```

## Run a stage with Gemini Interactions

Install `stagify[google]` and set `GEMINI_API_KEY` in your environment. The example
uses `gemini-3.8-flash`, omitting deprecated sampling settings.

```python
import asyncio
import os

from pydantic import BaseModel

from stagify import RunLimits, Runner, Stage, ToolContext, tool
from stagify.providers.google import GoogleProvider


class Question(BaseModel):
    task: str


class Number(BaseModel):
    value: int


class Answer(BaseModel):
    value: int


@tool
def double(args: Number, ctx: ToolContext):
    """Double one integer exactly."""
    return {"value": args.value * 2}


async def main():
    stage = Stage(
        "analysis",
        "Use double to calculate the answer, then submit complete_stage.",
        Question,
        Answer,
        tools=[double],
    )
    async with GoogleProvider(
        model="gemini-3.8-flash",
        api_key=os.environ["GEMINI_API_KEY"],
        temperature=None,
        top_p=None,
    ) as provider:
        runner = Runner(provider, limits=RunLimits(max_model_calls=8, timeout_seconds=60))
        result = await runner.run(stage, {"task": "What is double 21?"})
        assert result.output.value == 42
        print(result.output.model_dump())
        print("Usage returned by Gemini:", result.usage.total.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
```

Simulated Gemini responses for this flow:

```text
gemini-3.8-flash → double(value=21)
double          → {"value": 42} with an evidence ID
gemini-3.8-flash → complete_stage(value=42)
Stage output    → {"value": 42}
```

This walkthrough is simulated, not a recorded API response. Running the Python
example calls your Google account; actual tool choices and usage can vary.

From a source checkout, run the same example with simulated Interactions HTTP
responses through the real Google SDK and Stagify adapter:

```bash
uv sync --locked --all-extras
uv run python scripts/simulate_gemini.py examples/gemini.py
```

The simulation makes no live API requests. Its usage counters are fixture data.
See the [complete quickstart](https://ramyjamea.github.io/stagify/getting-started/quickstart/).

## Build a workflow

Compose stages without writing another execution loop:

```python
from pydantic import BaseModel
from stagify import Runner, Stage, Step, Workflow

class Task(BaseModel):
    task: str

explore = Stage("explore", "Identify the investigation scope.", Task)
write = Stage("write", "Write from the supplied observations.", Task)
report = Workflow("report", Task, (
    Step(explore),
    Step(write, input=lambda state: {"task": state.output("explore")}),
))

async def generate_report(provider, question):
    async with Runner(provider) as runner:
        result = await runner.run(report, {"task": question})
    return result.output, result.usage.total
```

All steps and children share one run budget, deadline and usage ledger.
`ContextField` injects application-owned values with preserve/replace/append
rules. `as_tool(arguments=...)` exposes only model-supplied child arguments.
`Completion` separates submission from state-derived output and permits precise
partial-result policies.

The [native analysis harness](https://ramyjamea.github.io/stagify/tutorials/analysis-workflow/)
combines exploration, delegated cleaning, evidence-backed memory and Markdown
writing. Run it offline through the real Gemini SDK:

```bash
uv run python scripts/simulate_gemini.py examples/analysis_workflow.py
```

- **Stages and substages:** typed input/output contracts, isolated transcripts,
  and `stage.as_tool()` for model-selected delegation.
- **Optional context policies:** preserve selected input fields, offload large
  tool results, summarize older history, or disable transformations for a baseline.
- **Evidence and memory:** retrieve exact results, replace working findings,
  and detect stale dependencies after resource changes.
- **Run diagnostics:** own/child/inclusive usage, structlog events, typed errors,
  bounded retries, deadlines, and execution limits.
- **Provider boundary:** Gemini Interactions is bundled; custom adapters implement
  the normalized `Provider` protocol.

Follow [analysis with a cleaner](https://ramyjamea.github.io/stagify/tutorials/analysis-with-cleaner/)
or [a long tool loop](https://ramyjamea.github.io/stagify/tutorials/long-tool-loop/).
Both use Gemini Interactions and support an explicitly simulated HTTP replay for offline checks.

## Current scope

Version 0.2.0 is an alpha release. State is in memory, request token sizing is
estimated, and only the Gemini Interactions model adapter ships. Summaries can
lose information; evidence references do not establish semantic truth. See the
[supported features and limitations](https://ramyjamea.github.io/stagify/STATUS/) and
[prior-art notes](https://ramyjamea.github.io/stagify/RESEARCH/).

## Develop and contribute

```bash
git clone https://github.com/RamyJamea/stagify.git
cd stagify
uv sync --locked --all-extras --group docs
uv run pytest -q
uv run --all-extras --group docs python scripts/check_docs.py
uv run --group docs mkdocs serve
```

See [contributing](https://ramyjamea.github.io/stagify/contributing/) for checks, documentation authoring, and
GitHub Pages deployment. Package CI checks Linux/Windows and Python 3.12–3.14.
Documentation CI replays simulated Gemini HTTP responses through the included
examples and builds the site in strict mode. Live model calls are excluded from CI.

## License

[MIT](https://github.com/RamyJamea/stagify/blob/v0.1.2/LICENSE).
