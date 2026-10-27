# Stagify

A Python framework being developed for staged tool workflows with explicit context policies.

**Status: implementation plan and installable package scaffold.** The stage runner,
provider adapters, context policies, substages, structured logging, and framework
error handling are planned work. They are not available APIs in this checkout.

Start with [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). It defines the
milestones, expected context for each reference stage, optional policy behavior,
substage execution, logging conventions, error handling, and acceptance criteria.
The [research notes](docs/RESEARCH.md) explain the existing capabilities this
project builds on and the comparisons it needs to earn.

## Planned scope

- Typed tools and stages over a provider-independent ReAct runner.
- Context contracts specifying required fields, updates, and handoffs.
- Optional context policies at runner, stage, policy, and invocation levels.
- Protected fields, bounded tool output views, exact retrieval, and optional summaries.
- Nested stages, including a cleaner invoked by an analysis stage.
- Evidence references and resource revisions for invalidating stale findings.
- Structured events through `structlog` and typed, actionable errors.
- uv packaging, provider extras, and a release process for PyPI.

## Work on the scaffold

Python 3.12 or newer is required. The bootstrap currently has no runtime
dependencies; Pydantic and structlog will be added with their implementations.

```powershell
git clone https://github.com/RamyJamea/stagify.git
cd stagify
uv sync --locked
uv run python -c "from importlib.metadata import version; print(version('stagify'))"
uv build --no-sources
uv run python scripts/check_distribution.py
```

The distribution check installs the built wheel in an isolated environment and
checks its import and metadata outside the source tree. It also checks the source
archive. This verifies packaging; it is not a framework functionality test.

For installation into another Python project:

```powershell
uv add "stagify @ git+https://github.com/RamyJamea/stagify.git"
```

This installs the scaffold from GitHub. No Stagify distribution has been
published to PyPI by this project, and the PyPI name is not reserved by creating
the GitHub repository. After a release is published under the confirmed name,
installation will use `uv add stagify`. Provider extras will be documented as
they become implemented and tested.

## Development order

1. Define the public contracts and a deterministic test provider.
2. Implement the tool runner and typed completion/error behavior.
3. Add stage context contracts and policy opt-in/opt-out.
4. Add artifact storage, evidence updates, and resource revision tracking.
5. Add deterministic context reduction and optional summarization.
6. Add substages with shared budgets and isolated model contexts.
7. Integrate a real provider and the first application.
8. Compare against existing solutions and prepare the first PyPI alpha.

The implementation plan specifies dependencies between these milestones; logging
and error handling begin with the contracts and are implemented throughout.

## License

[MIT](LICENSE).
