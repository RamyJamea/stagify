# Contributing

Changes should include a runnable example or appropriate verification when behavior changes. Keep API claims aligned with the currently implemented release.

## Set up

```bash
git clone https://github.com/RamyJamea/stagify.git
cd stagify
uv sync --locked --all-extras --group docs
```

## Check runtime changes

```bash
uv run pytest -q
uv run ruff check src tests scripts examples
uv run ruff format --check src tests scripts examples
uv build --no-sources
uv run python scripts/check_distribution.py
```

The package workflow checks Linux and Windows across Python 3.12–3.14. Tests use scripted providers and mocked Google HTTP responses; live API credentials are not required.

## Write and preview documentation

```bash
uv run --group docs mkdocs serve
```

Open the local address shown by MkDocs. Edit Markdown under `docs/` and navigation in `mkdocs.yml`. Source examples live in `examples/` and are included with the snippets extension, so the displayed code is the executed file.

Before pushing:

```bash
uv run --all-extras --group docs python scripts/check_docs.py
uv run --group docs mkdocs build --strict
```

The checker parses Python fences in the README and docs, requires reference coverage for public exports, and executes the included Gemini examples through `scripts/simulate_gemini.py`. That harness intercepts Interactions HTTP requests while keeping the real Google SDK and Stagify adapter in use. It verifies `gemini-3.8-flash`, stateless settings, and omitted sampling parameters. Add new Gemini scenarios explicitly to the harness and checker. No paid model calls run in docs CI.

The API reference reads the checked-in source using mkdocstrings. Add prose for semantics, failure cases, and defaults that a signature alone cannot explain. Label simulated responses, fixture usage, and incomplete snippets clearly.

## Hosting and releases

The `Documentation` workflow builds on pull requests and pushes. Pull requests validate without deploying; successful pushes to `main` deploy the built artifact to GitHub Pages. A workflow dispatch can rebuild manually. Deployment uses the `github-pages` environment and a short-lived Actions identity.

The public URL is [ramyjamea.github.io/stagify](https://ramyjamea.github.io/stagify/). Repository settings must use GitHub Actions as the Pages publishing source. Hosting uses the free public-repository Pages service; no custom domain or paid documentation service is configured.

Documentation follows the current `main` branch and labels the current package release. Changes to docs do not publish a new Python package. Package publication remains a separate manually dispatched PyPI workflow. Update release notes and version labels when a new package version ships.

The site uses MkDocs, its community Material theme, and mkdocstrings. All are documentation dependencies, not Stagify runtime dependencies. Fonts use the visitor's system fonts; no analytics are configured.

## Submit changes

Open a pull request with the concrete behavior change and relevant validation. Use the [issue tracker](https://github.com/RamyJamea/stagify/issues) for reproducible bugs and documentation gaps. Preserve the original extracted provider implementation unless a provider behavior change is explicitly intended and covered by regression tests.
