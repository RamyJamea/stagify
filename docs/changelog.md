# Release notes

## 0.1.2 · October 27, 2026

Documentation and example update; the staged runtime is unchanged.

- Use `GoogleProvider` with `gemini-3.8-flash` in the README and tutorials.
- Omit deprecated sampling parameters in Gemini 3.8 examples.
- Show labeled simulated Gemini responses and validate examples with the real SDK over mock HTTP transport.
- Check long-loop row coverage from current evidence before completion.
- Use the cropped, background-removed penguin PNG as the documentation favicon.

## 0.1.1 · October 27, 2026

Branding and documentation release. The staged runtime is unchanged from 0.1.0.

- Adopt the supplied penguin crew artwork in the repository, package description, and documentation.
- Add a transparent logo derivative while retaining the original artwork.
- Restyle documentation in black, white, and neutral grays, with light/dark themes, top-level navigation, sidebars, and a page outline.
- Include the documentation URL in package metadata and refresh the PyPI README.

## Documentation updates · October 27, 2026

The documentation site adds a credential-free quickstart, cleaner and long-loop tutorials, conceptual and operational guides, and a source-generated API reference. Included offline examples and strict site builds are checked in CI. These documentation changes do not alter the published 0.1.0 runtime.

## 0.1.0 · October 27, 2026

First alpha release, published on [PyPI](https://pypi.org/project/stagify/0.1.0/).

- Typed tools/stages and stages exposed as tools, with fresh child transcripts.
- Optional artifact offloading, history summarization, and explicit context contracts.
- Exact evidence, resource revisions, and versioned working findings.
- Own/child/inclusive token usage, structured logs, typed errors, and bounded execution.
- Gemini Interactions adapter, scripted examples, and package validation across Linux/Windows and Python 3.12–3.14.

See [supported features](STATUS.md) for the release's current limits.
