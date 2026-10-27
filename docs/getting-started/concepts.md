# Core concepts

Stagify runs a ReAct loop: a provider chooses tools, the runtime executes them, and results return to the provider until the stage completes or reaches a limit.

| Concept | Responsibility |
| --- | --- |
| `Stage` | Instructions, validated input/output contracts, tools, and local settings |
| `Tool` | A typed application operation with declared resource access |
| `StageTool` | A stage exposed as a callable tool through `stage.as_tool()` |
| `Provider` | Translate normalized requests and responses to a model API |
| `Runner` | Execute stages, compile request context, enforce budgets, return results |
| `RunContext` | Application resources, revisions, artifacts, working memory, and result snapshots |
| `ToolContext` | A tool's declared resource access and evidence/memory helpers |
| `StageResult` | Output, status, history, children, compactions, and usage |

## Three forms of information

**Canonical history** is the full local transcript retained for an invocation. A child stage starts a fresh transcript; it does not inherit the parent's entire conversation.

**Request context** is the view sent to the provider. It contains the selected, validated stage input and may include working memory, a summary of older batches, recent history, and artifact references. Policies change this view while the canonical history remains available.

**Evidence and working state** are shared through `RunContext`. Evidence stores exact tool outputs. Working entries store replaceable findings with evidence references and resource revisions. A changed resource can make a finding stale.

## What crosses a substage boundary?

The parent submits the child's declared input. The child runs with its own instructions, tools, transcript, and policies. The parent then receives a result envelope containing output, status, invocation ID, evidence IDs, and resource revisions. The developer can inspect the child's full result through `result.children`.

Resources, artifacts, memory, and run limits are shared through the run context. Resource declarations restrict the runtime's ordinary access paths; they do not sandbox arbitrary Python code.

## Defaults are explicit

Compression and offloading are disabled by default. Memory tools require `memory=True`. `verbose=False` still emits terminal summaries, warnings, and errors. Root and child invocations share call limits, and nested requests count toward the returned usage totals.

See [context policies](../guides/context-management.md) for precedence and [limits](../guides/errors.md) for stopping behavior.
