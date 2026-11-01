# Implementation status

This source targets the 0.2.0 alpha release. Install the latest published version
with `uv add stagify`; new workflow/context APIs require 0.2.0 or this source checkout.

Implemented:

- Deterministic Workflow/Step composition with typed boundaries and one shared run ledger.
- Separate model-facing substage arguments and application-injected context.
- Preserve/replace/append field rules, declared dependencies and validated refreshes.
- State-derived completion schemas and precise local partial-result policies.
- Managed runner cleanup for default and stage-specific providers.

- Typed tools/stages, input validation, structured completion, and explicit handoffs.
- One provider-independent runner, synchronous/asynchronous tool execution.
- Stages exposed as tools, fresh child context/history, shared budgets and usage.
- Optional runner/stage/run context policy controls; individual policy switches.
- Exact stage input preservation; optional-field projection and protected field validation.
- In-memory artifacts, exact evidence reads/pages, keyed memory updates/withdrawal.
- Declared resource revisions, conservative invalidation, current-memory completion checks.
- Bounded artifact projections and history summaries; full source retained in memory.
- Usage own/children/total/by-purpose, unknown accounting, and failed result snapshots.
- structlog events, verbose overrides, bounded retries, cancellation and typed errors.
- Gemini Interactions through the extracted original provider and its regression tests.
- Gemini examples, simulated Interactions HTTP responses, and long-tool-loop scenario tests.
- Build/install checks, CI matrix, and a manually dispatched Trusted Publishing workflow.

Current limits:

- Storage, history, and working state are process-local; no durable resume backend.
- Request sizes use a UTF-8 estimate, not a provider-exact tokenizer. Configure limits
  with headroom and deployment-specific capabilities.
- Only the Google Interactions SDK adapter ships; other providers can implement Provider.
- No streaming, automatic multi-provider failover, or vector/relevance retrieval.
- Memory operations replace/withdraw keyed entries; arbitrary merge semantics and
  automatic LLM extraction are not implemented.
- All selected stage input values are exact. Per-field lossy transformation of stage
  inputs is not implemented.
- Injected context fields use unaliased Python names. Append sources supply deltas;
  deduplication, stream cursors and cross-process delivery remain application concerns.
- Workflows are sequential; conditional graphs, parallel steps and durable execution
  are not implemented.
- Resource scope is declared by trusted application tools; it cannot sandbox Python.
- Source references and revisions do not establish semantic truth of model-written claims.
- Threaded synchronous tools may continue externally after cancellation; reconcile
  potentially mutating outcomes. No distributed exactly-once guarantee.
- No external-framework benchmark or paid real-model accuracy comparison has been run.

See README.md for the supported public API. The original implementation plan
records additional future work and does not imply that all roadmap features ship.
