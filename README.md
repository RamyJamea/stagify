# Stagify

Staged agent workflows with explicit context management.

Define typed stages and tools, expose stages as tools, and control the context
sent to a provider during long tool loops. Keep exact evidence available while
using optional artifact offloading and historical summaries.

**[Documentation](https://ramyjamea.github.io/stagify/)** ·
[Quickstart](https://ramyjamea.github.io/stagify/getting-started/quickstart/) ·
[PyPI](https://pypi.org/project/stagify/) ·
[Examples](examples/)

## Install

Python 3.12 or newer is required.

```bash
uv add stagify
```

For the Gemini Interactions adapter:

```bash
uv add "stagify[google]"
```

## Run a stage without an API key

```python
import asyncio

from pydantic import BaseModel
from stagify import ModelResponse, Runner, Stage
from stagify.testing import ScriptedProvider


class Task(BaseModel):
    task: str


async def main():
    stage = Stage("analysis", "Answer the task.", Task)
    provider = ScriptedProvider([ModelResponse(text="Hello from Stagify.")])
    result = await Runner(provider).run(stage, {"task": "Say hello."})
    print(result.output)


asyncio.run(main())
```

The [complete quickstart](https://ramyjamea.github.io/stagify/getting-started/quickstart/)
adds a typed application tool, validated output, and token accounting.

## Build a workflow

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
Both tutorials run without model credentials and include assertions.

## Current scope

Version 0.1.0 is an alpha release. State is in memory, request token sizing is
estimated, and only the Gemini Interactions model adapter ships. Summaries can
lose information; evidence references do not establish semantic truth. See the
[supported features and limitations](docs/STATUS.md) and
[prior-art notes](docs/RESEARCH.md).

## Develop and contribute

```bash
git clone https://github.com/RamyJamea/stagify.git
cd stagify
uv sync --locked --all-extras --group docs
uv run pytest -q
uv run --group docs python scripts/check_docs.py
uv run --group docs mkdocs serve
```

See [contributing](docs/contributing.md) for checks, documentation authoring, and
GitHub Pages deployment. Package CI checks Linux/Windows and Python 3.12–3.14.
Documentation CI executes the included offline examples and builds the site in
strict mode. Live model calls are excluded from CI.

## License

[MIT](LICENSE).
