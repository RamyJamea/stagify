# Stagify implementation plan

Created 27 October 2026. This document records the original roadmap.
The initial runtime is now implemented; see docs/STATUS.md and README.md for the
supported API and the features that remain future work.

## 1. Objective and scope

Build a small typed Python library for stages, tools, nested stages, and explicit
context management over provider adapters. Publish its source independently of
the original application, and prepare it for installation through uv and a later
PyPI release.

The intended developer workflow is: define tools, define stages and expected
context, enable the context policies needed, then run. Context management must be
optional. Stage contracts, tool allowlists, validation, and execution limits must
continue to work when context policies are disabled.

The initial implementation must cover:

- A provider-independent ReAct loop with typed tool arguments and stage outputs.
- Expected context contracts for each stage, with explicit input and handoff mapping.
- Optional policies for protected fields, structured state, artifact offloading,
  retrieval, and history compaction.
- Substages such as a cleaner invoked by an analysis stage.
- Evidence provenance, declared resource revisions, and stale-state handling.
- Structured logging using structlog, controlled by a verbose variable.
- Typed errors, bounded recovery, cancellation, and truthful partial results.
- A buildable distribution, examples, comparative evaluations, and release checks.

These capabilities overlap with existing frameworks. The product hypothesis is
that their integration is simpler and easier to inspect, not that stages,
compression, or protected context are new. See [research](docs/RESEARCH.md).

## 2. Deliverable boundaries

### Present in the foundation

- [x] Independent src-layout Python package metadata and typed-package marker.
- [x] README and this implementation plan with explicit implementation status.
- [x] MIT license and source/build exclusions.
- [x] Packaging checks that install the built wheel outside the checkout.
- [x] CI definition for Python 3.12-3.14 on Linux and Windows.
- [x] Verify the built distribution locally on Python 3.12, 3.13, and 3.14.
- [x] Prepare the independent repository for its initial GitHub push.

### Planned after the foundation

All runtime classes and policy names in this document are proposed interfaces.
There are no placeholder classes pretending to implement them. Each milestone
adds executable behavior, meaningful tests, documentation, and a working example.

Start with Pydantic v2 and structlog as core dependencies when milestone M1 lands.
Provider SDKs are optional extras, added only with tested adapters. Do not include
pandas, ERP models, HTTP servers, message brokers, or business prompts in core.

## 3. Public API and source organization

Keep the first public surface small: Stage, Tool or @tool, Runner, ContextPolicies,
and Provider. Evidence stores, budget accounting, reducers, and journals can use
internal protocols until integrations require public extension points.

Proposed layout as implementation grows:

```text
src/stagify/
  __init__.py
  py.typed
  contracts.py
  errors.py
  logging.py
  tools.py
  stages.py
  runner.py
  substages.py
  context/
    contracts.py
    policies.py
    compiler.py
    accounting.py
    summaries.py
  memory/
    entries.py
    reducers.py
    revisions.py
  storage/
    artifacts.py
    journal.py
  providers/
    base.py
    google.py
tests/
  unit/
  integration/
  scenarios/
examples/
  basic_stages/
  analysis_with_cleaner/
  long_tool_loop/
benchmarks/
```

Use one ReAct runner over provider adapters. Adapters normalize requests, outputs,
tool calls, usage, and errors, while preserving their provider's required replay
blocks. They do not execute application tools. Capability flags expose context
counting, structured output, streaming, and replay limitations.

## 4. Expected context for every stage

### Separate execution context from model context

ExecutionContext contains resource handles, tool dispatch, artifact access, the
budget ledger, a bound logger, and invocation identifiers. It is not automatically
serialized into the prompt. Provider configuration and credentials remain outside
model context.

StageContext is the validated, renderable input selected for one stage. Its
contract declares:

| Property | Meaning |
| --- | --- |
| input_model | Types and constraints of fields accepted on stage entry. |
| required_fields | Fields that must be present before the first provider call. |
| optional_fields | Fields allowed to be absent, with explicit defaults if any. |
| protected_fields | Values protected from compression while the relevant policy is active. They may still change through declared updates. |
| writable_fields | Fields this stage can update, with replace/merge/append rules. |
| resource_dependencies | Resource versions relevant to its evidence and derived entries. |
| output_model | Validated result accepted by completion. |
| handoff_projection | Explicit mapping of selected output/state into the next stage. |
| policies | Optional rules applied to this stage's active context. |

Schemas and configured paths must agree at construction time. Unknown paths,
conflicting policies, missing required values, and incompatible handoff types
produce actionable errors. A missing required input fails before any model call.

A protected value must fit its declared allocation. Protection does not create
unlimited model capacity. The compiler must return ContextBudgetExceeded if
required content cannot fit; it cannot silently summarize a protected field.

### Reference stages

These are application examples, not fixed stages built into the framework. Users
must be able to define a new stage without changing core.

| Stage | Expected model input | Protected/current state | Allowed updates | Output and visibility |
| --- | --- | --- | --- | --- |
| Exploration | Task, resource catalog, field descriptions, current revisions, declared constraints; selected prior evidence metadata if available. | Task constraints, known data meanings, unresolved ambiguities, and revision snapshot. | Observations, working interpretations labeled as assumptions, and suggested analysis questions. | A typed exploration handoff containing context, questions, and limitations. Analysis sees this projection, not an automatic copy of every exploration exchange. |
| Analysis | Task, exploration handoff, current resource versions, selected evidence index, existing current findings when resuming, and available tool/substage descriptions. | Metric definitions, populations, periods, units, denominators, required constraints, and current findings with evidence references. | Keyed findings, assumptions, open questions, next actions, and declared resource changes through tools. | Current supported findings, unresolved required issues, and status. Writer input is explicitly projected from this result. |
| Cleaner, as an analysis substage | One preparation task, relevant source/target fields, catalog slice, allowed transformation rules, resource handles represented as descriptors, and current revisions. | The delegated task, preservation constraints, declared formats, and unresolved parse ambiguities. | Only permitted resource transformations and their own diagnostic entries. No unrelated analytical conclusions or access to the parent's full conversation. | Typed summary, applied changes, current revisions, evidence handles, failures/limitations, and completion status. |
| Writing | Selected current findings, their essential qualifications and measure definitions, requested language/audience, and formatting requirements. | Supported measurements, counting bases, scope, uncertainties, and required presentation constraints. | Draft prose and organization; changes to analytical facts require an explicit request back to analysis if the application enables that path. | Report text or a typed report. No implicit resource mutation tools or full analysis/cleaner transcripts. |

At a handoff, the receiving stage validates its expected input independently.
Field selection is a declared contract even with context optimization disabled;
turning policies off does not grant stages access to all application state.

## 5. Optional context policies

### Configuration and precedence

The default is no context reduction. A basic stage must run without configuring
memory, a summarizer, an artifact backend, or a policy.

1. Runner configuration provides default policies, initially disabled.
2. A stage can inherit the runner configuration or explicitly enable/disable its
   own policy pipeline.
3. Each configured policy has an enabled switch. Enabling a pipeline does not
   implicitly enable absent or individually disabled policies.
4. A per-run apply_context_policies override can force the pipeline on or off for
   that run and all descendant stages. An unset override respects stage settings.
   Force-on still uses only explicitly configured individual policies.
5. Conflicting field rules fail validation rather than relying on unspecified order.

Illustrative target configuration, not currently executable:

```python
runner = Runner(
    provider=provider,
    context_policies=ContextPolicies(enabled=False),
    verbose=False,
)

analysis = Stage(
    name="analysis",
    input_model=AnalysisInput,
    output_model=AnalysisOutput,
    tools=[aggregate, clean_data],
    context_policies=ContextPolicies(
        enabled=True,
        protected_fields=["task", "constraints", "metric_definitions"],
        artifact_offload=ArtifactOffload(enabled=True),
        history=Summarize(enabled=False),
    ),
)

# Explicit baseline run: no context policy transformations, including in children.
result = await runner.run(
    analysis, prepared_input, apply_context_policies=False, verbose=True
)
```

In off mode, the model receives the declared stage input plus its uncompressed
local transcript. No policy may silently offload, summarize, filter, or evict
content. Required input validation, tool permissions, output validation, valid
provider histories, max-call limits, deadlines, and context-capacity checks remain
active. Capacity exhaustion produces a typed error instead of hidden compression.

Disabling one policy leaves its source content available to the remaining
configured pipeline. For example, disabling summarization does not implicitly
discard old messages. Deterministic offloading can still be enabled separately.
If the configured reductions cannot make the request fit, stop explicitly.

### Policy behaviors

| Policy | Applied behavior | Disabled behavior |
| --- | --- | --- |
| Protected fields | Preserve selected values exactly through reductions; explicit valid state updates remain allowed. | No special compression protection, while required contract fields still cannot be silently removed. |
| Structured updates | Apply validated keyed state patches with explicit replace/merge/append/supersede/retract semantics. | No automatic extraction or model-driven memory updates; application-supplied stage state is still usable. |
| Artifact offloading | Store complete results and place a bounded tool-specific view and retrieval handle in context. | Keep the full result in the active transcript, subject to hard capacity limits. |
| Retrieval | Load requested evidence paths/pages or selected metadata within the current allocation. | No automatic retrieval; explicit application tools may still read evidence. |
| History summarization | Replace eligible older complete exchanges with a source-anchored checkpoint, retaining recent complete batches. | Keep those exchanges unchanged unless another explicitly enabled policy handles them. |
| Context selection | Choose optional working entries relevant to the stage/task within allocation. | Include the state selected by the stage contract without additional relevance filtering. |

Keep artifact storage and execution accounting independent from whether their
context transformations are enabled. A resource mutation can make supplied
evidence stale even when history compression is disabled.

### Request lifecycle

Before every model request, apply committed state changes, resolve current
dependencies, compile the stage view, render provider-specific content, and
measure the full request. Count instructions, schemas, replay blocks, selected
fields, retrieved content, and messages; reserve response capacity.

When enabled, reduce in this order: bounded tool projections, redundant payload
removal, optional-state selection, exact retrieval, then optional narrative
summarization. Re-render and measure after each pass. Keep required user
constraints at their original authority; derived tool content remains data.

Do not split assistant tool-call batches from their results. Use only replay
transformations supported by the adapter. Native opaque provider compaction must
not be mistaken for portable memory or used to transfer hidden state to a
different provider.

Token estimates are labeled as estimates. Unknown provider limits require explicit
configuration. An initial 80% trigger/60% target can be benchmarked, but is not a
universal default or a guarantee that a provider will accept heuristic counts.
Summaries have their own bounded input/output budget and consume run usage.

## 6. Working state, evidence, and context updates

Keep the complete evidence/event record, current working state, and model prompt
as separate objects. The event record can grow while the prompt stays bounded.
In-memory storage is the first backend and must report its non-durable nature.

Evidence records include execution identity, tool name/version, validated
parameters, resource versions read/written, artifact location/hash, result shape,
and a compact deterministic projection. Identical bytes may share storage but
distinct executions retain distinct identities.

Working entries have a stable key and version, kind, value, source references
including exact paths, declared dependencies, scope, and status. Distinguish facts,
findings, assumptions, decisions, open questions, and next actions. Values such as
money, units, populations, and denominators should be typed where possible.

Support explicit expected-version updates and withdrawals. Preserve conflicts
instead of silently selecting whichever statement arrived last. A later tool
result does not automatically become a validated finding.

Start with one revision per mutable resource. Declared writes make dependent
entries stale; finer column dependencies can be added later. Historical evidence
remains retrievable. Completion validators can require current references for
selected outputs. References validate lineage and revision, not the semantic truth
of arbitrary model-written prose.

Avoid making another LLM responsible for every memory update. Tools supply exact
observations deterministically; model proposals handle synthesis with validation.
Optional automatic extraction must be evaluated for omissions and invented facts.
Summaries that depend on invalidated evidence must be refreshed or marked
historical so they cannot reintroduce stale conclusions as current facts.

## 7. Substages, including cleaner inside analysis

Expose a StageTool or equivalent adapter that lets an allowed parent call a
registered child stage using typed arguments.

```text
analysis invocation
  -> clean_data(task, fields, transformation constraints)
       -> new cleaner invocation with selected input and private history
       -> permitted inspection/transformation tools
       -> validated cleaner result and actual resource revisions
  <- summary, changes, evidence handles, status, limitations
  -> invalidate affected findings and continue the parent analysis loop
```

- Each child invocation gets its own stage_invocation_id, parent_invocation_id,
  path/depth, local history, context contract, and resolved policies.
- Pass only the child input projection. Do not automatically copy the parent's
  transcript, findings, unrelated tools, or unrestricted execution context.
- Share explicitly granted resource/artifact handles and a single run budget
  ledger. Child model calls, retries, summaries, and tool work count once toward
  workflow totals and can also have smaller local caps.
- Fresh cleaner calls are isolated by default. Reusing child state requires an
  explicit application option and identity; repeated calls do not accidentally
  share prior child history.
- Enforce maximum depth and reject unconfigured recursive cycles.
- Mutating child tools serialize writes to the same resource. The parent pauses
  dependent work until the child settles and actual revisions are reconciled.
- Return actual post-execution revisions from the runtime rather than trusting a
  model-generated revision field.
- Child partial/failure results expose completed changes and evidence. A failed
  child may already have committed mutations; update the parent's resource state
  and invalidations even if the child did not complete.
- Default child failure propagation stops the parent with a typed SubstageError.
  Applications can explicitly request a structured tool-error return or an allowed
  partial handoff so the parent can choose a new action.
- Parent cancellation cancels/drains children and propagates cancellation after
  cleanup. Blocking external operations that cannot be cancelled are reported as
  unresolved; cancellation is not represented as successful completion.

## 8. Structured logging and verbose control

Use structlog from the first runtime milestone. The library obtains/binds a logger
but does not reconfigure the host application's global logging on import. Provide
an explicit example configuration for console rendering in development and JSON
in deployed applications.

Public configuration includes verbose: bool = False on Runner. Stages may use a
nullable override, and a run can override verbosity for itself and descendants.
Precedence is run override, then stage override, then runner default. A child with
no explicit setting inherits the parent's effective setting.

| Setting | Events emitted |
| --- | --- |
| verbose=False | Run/stage terminal summaries, warnings, failed operations, scheduled retries, and errors. |
| verbose=True | The above plus model/tool lifecycle metadata, policy application/skips, context allocations, compaction receipts, and child-stage boundaries. |

Verbose events use DEBUG by default, so applications must also enable that level
in their logging configuration. The verbose flag does not override a host's sink
or filter. Neither setting logs credentials, raw prompts, tool payloads, or entire
datasets. Any future payload tracing must be a separate explicit option with
redaction and retention controls.

Use stable event names and a schema version. Bind run_id, stage_name,
stage_invocation_id, parent_invocation_id, stage_path, tool_call_id, attempt,
provider/model, duration_ms, status, error_code, and applicable token counts.
Unknown usage is null/unknown rather than zero. Keep local and run-total usage
distinct so parent summaries do not double-count child work.

Initial events: run.completed, run.failed, stage.completed, stage.failed,
provider.retry_scheduled, tool.failed, context.policy_applied,
context.policy_skipped, context.compacted, and substage.started/completed/failed.
Record one terminal event per invocation, with one traceback at the failure owner
rather than duplicate tracebacks at every wrapping layer.

Use scoped bindings and restore them on exit; concurrent runs and nested stages
must not leak identifiers into each other. Carry identifiers explicitly across
sync/thread boundaries instead of assuming every execution method propagates
context variables identically.

References: [structlog context variables](https://www.structlog.org/en/stable/contextvars.html)
and [logging practices](https://www.structlog.org/en/stable/logging-best-practices.html).

## 9. Error handling and recovery

Define a StagifyError hierarchy carrying a stable code, safe message, operation
identity, and structured details. Preserve original causes for debugging. The
boundary exposed to a model contains only actionable, sanitized feedback.

| Error/failure | Default handling | Optional recovery |
| --- | --- | --- |
| ConfigurationError / PolicyConfigurationError | Fail before execution with the invalid option/path. | Caller fixes configuration. |
| ContextValidationError | Fail stage entry; list missing/invalid fields without exposing unrelated values. | Caller supplies valid input. |
| ToolInputError | Return structured feedback to the model; create no successful evidence or mutation. | Model corrects arguments within the remaining budget. |
| Declared business/tool failure | Return the tool's safe code and known execution outcome if recoverable. | Explicit tool/application recovery policy. |
| ProviderTransientError | Retry only the provider request within attempt/deadline limits; respect retry-after hints. | Bounded backoff with jitter; optional configured fallback provider at a supported boundary. |
| ProviderAuthenticationError / permanent quota error | Stop promptly; do not repeatedly retry unchanged credentials or exhausted quota. | Caller corrects configuration/account state. |
| ProviderOutputError | Reject malformed calls, duplicate IDs, invalid replay, or unrecognized tools before executing any call. | Explicit bounded provider re-request, only when no tool from that response executed. |
| StageCompletionError | Reject invalid output or required stale/missing evidence. | Configurable bounded validation feedback; no invalid completion is committed. |
| ContextBudgetExceeded | Stop with recoverable state and the oversized required components. | Caller changes allocation or explicitly enables another reduction policy. |
| StateConflictError | Reject stale expected-version writes; preserve committed state. | Re-read state and propose an explicit update. |
| ArtifactNotFound / invalid pointer | Return a precise retrieval error without fabricating evidence. | Correct the reference, retrieve a valid page, or recompute if authorized. |
| SubstageError | Include parent/child identity, child status, actual revisions, and known mutations. | Configured tool-error return or explicitly allowed partial child result. |
| RunLimitExceeded / timeout | Terminate with a typed incomplete outcome and saved state. | Partial output only when the stage's contract permits it. |
| Unexpected tool exception | Stop; preserve cause and known execution outcome. | No generic retry of an unclassified side effect. |
| Cancellation | Cleanup, record cancellation once, and propagate cancellation. | Resume only through an explicit recovery mechanism. |

Provider retries must never rerun already executed tools. Disable hidden SDK
retries where possible or make their effects visible in accounting. Only tools
declared safe/idempotent may have automatic tool retries, with a separate cap.

For multiple calls in one response, validate all call envelopes first. Record each
execution result. If later work fails, expose which earlier calls committed;
preserving valid provider history must not manufacture successful tool results.
Interrupted or ambiguous external writes require reconciliation.

Use explicit result statuses: completed, partial, failed, cancelled. Partial
results include current supported output, remaining work, termination reason,
usage, and any unresolved mutation. Never relabel a partial run as completed.
No generic exactly-once guarantee or automatic rollback of arbitrary external
services is claimed.

## 10. Milestones and acceptance gates

| Milestone | Deliverables | Exit gate |
| --- | --- | --- |
| M0: repository and package | Independent source folder, plan, README, license, uv metadata/lock, archive checks, and CI. | Clean wheel import outside the checkout; no application files included; initial GitHub commit pushed. |
| M1: core contracts, errors, logs | Pydantic contracts, Provider protocol, tool/stage declarations, errors, structured event schema, verbose handling, and deterministic provider fixtures. | Invalid configurations fail early; JSON logs correlate isolated concurrent runs; verbose changes detail without exposing payloads. |
| M2: tool and stage runtime | Shared ReAct runner, sync/async tool dispatch, validation, completion, retries, usage, limits, cancellation, and typed result statuses. | A two-stage non-ERP example works without provider credentials; argument repairs, fatal errors, and exhausted budgets follow their contracts. |
| M3: stage context and policy switches | Expected input/handoff schemas, renderable context, protected field rules, override resolution, baseline off mode, and full request accounting. | Missing inputs fail before model calls; all off/on/inherit combinations are deterministic; disabled policies do not rewrite history. |
| M4: evidence and deterministic reductions | In-memory artifact store, bounded reads/pages, working entries, update rules, declared resource revisions, invalidation, tool projections, and receipts. | Exact old evidence is retrievable; stale findings cannot pass required-current validators; growing indexes and results stay bounded when policies are enabled. |
| M5: optional history summaries | Bounded source-anchored summarizer input/output, checkpoint validation/commit, protected-state preservation, and failure behavior. | Several reductions retain required facts and qualifiers; summary failure preserves committed state; disabled summaries make no summarizer calls. |
| M6: substages | Child-stage tool, private child context/history, explicit shared resources, aggregate budgets, depth checks, error propagation, and cancellation. | Analysis invokes two fresh cleaner runs and continues correctly; revisions reconcile even after child partial/failure; logs preserve the invocation tree. |
| M7: provider and application integration | Google adapter extra, provider replay/capability tests, opt-in live tests, and an external analysis application integration. | Core imports without SDK extras; scripted adapter contracts pass; the original application's behavior is compared before migration. |
| M8: comparison and first alpha | Benchmarks, stable examples/docs, compatibility checks, dependency ranges, version/release procedure, and PyPI Trusted Publishing setup. | Comparative results published honestly; Git installation works; a reviewed alpha can be published under a confirmed available PyPI name. |

Dependencies are M0 -> M1 -> M2 -> M3 -> M4 -> M5. M6 depends on M2-M4 and must
also compose with M5 before release. M7 depends on M2-M4; M8 requires all prior
acceptance gates. Logging and error handling are implemented continuously, not
deferred to the end.

Add core dependencies with M1. Add the Google SDK only with M7's optional extra.
Add functional unit/scenario tests with executable behavior; the foundation's CI
currently checks packaging only and must not advertise a completed agent test suite.

## 11. Verification scenarios

Use scripted deterministic provider responses for runtime invariants. Add
model-driven evaluation for information retention and reasoning quality; structural
tests alone cannot establish those properties.

- One initial user request with at least 100 tool batches and no intervening user turn.
- Early constraints and denominators used correctly after several reductions.
- One tool output larger than the context allocation, with exact paged recovery.
- Resource mutation making a finding and its dependent summary stale.
- Missing expected stage context, invalid handoff types, and prohibited state updates.
- Policy off at runner/stage/run levels; one policy disabled while others remain on.
- Protected fields exceeding allocation, producing an explicit error.
- Failed/malformed summarization preserving the prior committed checkpoint.
- Multi-call responses retaining complete call/result pairs and native replay blocks.
- Analysis -> cleaner -> analysis with fresh child contexts and correct actual revisions.
- Child failure after a successful mutation; parent stale-state reconciliation.
- Parent/child shared budget exhaustion and timeout/cancellation propagation.
- Authentication errors failing promptly and transient errors honoring bounded retry.
- Mutating tools not being duplicated by provider retries or automatic resume.
- Concurrent runs producing isolated structlog identifiers with verbose both off and on.
- Wheel installation and a complete non-ERP example on Python 3.12-3.14.

Compare the same tasks, model settings, tool results, and total budgets using:
full history where it fits; recent-history trimming; a rolling summary; a
configured existing framework with comparable retrieval; and Stagify with policies
off, deterministic policies on, and summaries on.

Measure task accuracy, retention of required values and qualifiers, stale claim
acceptance, duplicate tool work, retrieval success, provider-history rejection,
prompt size per step, total tokens including summaries/retries, latency, and
configuration effort. Report failures and unknown counts, not just averages.

## 12. Repository and release workflow

The new repository contains framework source and synthetic examples only. Study
the original application's generic runners and tests during extraction; do not
copy its datasets, credentials, ERP integrations, or business-specific configuration.
No dependency points back to that application's filesystem or private repository.

Commit uv.lock for repeatable development/CI; published library metadata declares
supported dependency ranges rather than imposing that development lock on consumers.
Use a build backend range compatible with the checked-in uv toolchain.

Initially install from the public Git repository. A GitHub repository does not
reserve the PyPI package name. Before the first registry release, verify the name,
set up project ownership/Trusted Publishing, document the supported API, and run
archive plus clean-environment installation checks.

CI runs on pushes and pull requests, with read-only repository permissions. Add
functional tests as milestones land. Publishing is a separate future release job,
not an automatic side effect of this bootstrap or every push to main.

The initial source version is 0.1.0a0 and indicates planning status. It is not a
claim that the framework is already usable. Do not publish an empty placeholder
package merely to claim a name.

## 13. First implementation task

Begin M1 with a small executable contract slice: a typed tool, two simple stages,
a scripted provider fixture, the error/result contracts, and structlog events with
verbose control. Confirm the desired developer API using that example before
adding the context-policy machinery.

Keep the remaining milestone checklists open until their acceptance gates pass.
