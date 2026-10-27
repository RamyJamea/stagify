# Installation

Use Python **3.12 or newer**. Stagify is published on [PyPI](https://pypi.org/project/stagify/).

## Create a project

```bash
uv init my-agent
cd my-agent
uv add stagify
```

If you already have a uv project, run `uv add stagify` in that project. It adds the dependency and updates your lockfile.

Verify the installed distribution:

```bash
uv run python -c "from importlib.metadata import version; print(version('stagify'))"
```

The current release is `0.1.0`. For an application that must stay on this release, use `uv add "stagify==0.1.0"` and commit `uv.lock`.

## Add Gemini support

```bash
uv add "stagify[google]"
```

This extra installs `google-genai`. The core package supports custom providers and the credential-free `ScriptedProvider` without installing the Google SDK. See [providers](../guides/providers.md) for configuration.

## Use pip instead

```bash
python -m pip install stagify
python -m pip install "stagify[google]"
```

## Work on the source

```bash
git clone https://github.com/RamyJamea/stagify.git
cd stagify
uv sync --locked --all-extras --group docs
uv run python examples/basic.py
```

Use the [contribution guide](../contributing.md) for tests, documentation previews, and deployment details.

Next: [run your first stage](quickstart.md).
