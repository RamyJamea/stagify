# Troubleshooting

## `uv add stagify` cannot resolve a release

Confirm Python is 3.12 or newer, and check whether your project uses a private index or a restricted mirror. Stagify 0.1.0 is on [public PyPI](https://pypi.org/project/stagify/0.1.0/). Use `uv add "stagify==0.1.0"` for an explicit version. A network/index failure is separate from an incompatible Python requirement.

## Google SDK is missing

Install the extra with `uv add "stagify[google]"`. The core install intentionally has no model SDK dependency. Verify that `uv run python` uses the same project environment in which you added the extra.

## Gemini rejects the request

Confirm the key, model access, and selected model's Interactions support. The bundled adapter uses Interactions, so a client supporting only Generate Content is insufficient. Check model-specific support for thinking settings and inspect the typed error and underlying cause. Do not paste API keys into issues.

## Context still grows after enabling policies

Check `ContextPolicies.enabled` and each individual policy's `enabled` flag. A stage policy replaces the runner policy object. A run override can disable transformations for every child. `protected_fields` alone does not activate history summaries or offloading.

Canonical history staying large is expected: reductions apply to request views. Process memory does not shrink automatically.

## `ContextBudgetExceeded` occurs with summarization enabled

Selected stage input, instructions, schemas, memory, and recent batches still need space. A single history batch may exceed the summarizer allocation, or a summary may fail to reduce size. Page tool outputs, enable offloading, reduce the recent tail, narrow memory selection, or use a larger supported allocation. Inspect compaction receipts and verbose events before changing several settings together.

## An offloaded value is unavailable to the model

Enable `memory=True` to provide `read_evidence` and `list_evidence`. Teach the stage to retrieve exact fields by evidence ID, JSON Pointer, and page. Evidence outside the stage's resource grant is rejected. Requests for oversized evidence selections must be narrowed.

## Completion is rejected after a cleaner runs

The cleaner may have changed a resource revision. A previous finding based on that resource is now stale. Recompute the observation and replace the working entry with its current `expected_version`. Check `required_memory` and your completion validator.

## `verbose=True` shows no request logs

Verbose events are DEBUG events. Configure the application's logger to permit DEBUG as well. The runner does not reconfigure global logging.

## Usage contains `None`

A provider attempt did not report that field. It may have failed before returning usage. Unknown values are not zero, and optional breakdowns may be absent even when `complete=True`. See [token usage](usage.md).

## A `RunContext` is already active

Do not share one context between concurrent root `run()` calls. Use separate contexts for concurrent independent work; use substages for delegation within one run.

## Report an issue

Include Stagify/Python versions, provider and API type, a minimal reproduction, the stable error code, and a sanitized traceback. Note whether context policies were enabled. Use the [GitHub issue tracker](https://github.com/RamyJamea/stagify/issues) and remove credentials and sensitive input first.
