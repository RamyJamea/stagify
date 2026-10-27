<div class="hero" markdown>
<div class="hero-copy" markdown>

<span class="eyebrow">Stagify · Python framework · v0.1.1</span>

# Give every stage the context it needs.

Build agent workflows with typed tools, isolated substages, and explicit context policies. Keep original evidence available while long tool loops use smaller request views.

<div class="hero-actions" markdown>

[Get started](getting-started/quickstart.md){ .md-button .md-button--primary }
[Explore context](guides/context-management.md){ .md-button }

</div>
</div>
<div class="hero-art" markdown>

![The Stagify crew: four hand-drawn penguins working together.](assets/brand/stagify-mark.png){ width="420" height="350" }

</div>
</div>

```bash
uv add stagify
```

Python 3.12+ · [PyPI](https://pypi.org/project/stagify/) · [GitHub](https://github.com/RamyJamea/stagify) · MIT

<div class="doc-grid" markdown>
<div class="doc-card" markdown>

### Design explicit stages

Validate each stage's inputs and output. Expose a cleaner as a tool inside analysis, with its own instructions and transcript. [Build with substages →](guides/substages.md)

</div>
<div class="doc-card" markdown>

### Control context growth

Choose artifact offloading, history summaries, or an unchanged transcript. Preserve stage inputs exactly and inspect compaction receipts. [Choose policies →](guides/context-management.md)

</div>
<div class="doc-card" markdown>

### Keep findings connected to evidence

Store exact tool outputs, retrieve selected fields, and invalidate working findings when their source resources change. [Understand evidence →](guides/evidence-memory.md)

</div>
<div class="doc-card" markdown>

### Account for the whole run

Inspect stage and descendant token usage, shared limits, typed failures, and structured events. [Read usage totals →](guides/usage.md)

</div>
</div>

## Follow a complete workflow

Start with [a stage that runs without API credentials](getting-started/quickstart.md). Then follow [analysis with a cleaner](tutorials/analysis-with-cleaner.md) and [a long tool loop](tutorials/long-tool-loop.md), which demonstrates offloading, summarization, and a policies-disabled comparison. Connect [Gemini Interactions](guides/providers.md) when you are ready to use a model.

## Know the boundaries

Stagify 0.1.1 is an alpha release. State is in memory, token sizing is estimated, and Gemini Interactions is the only bundled model adapter. Summaries can lose information; evidence references establish provenance, not the truth of a model's claims. Read the [supported features and limitations](STATUS.md) before designing a deployment.

Stage context, compression, and protected information also exist in other frameworks. Stagify brings them together through explicit stage contracts, evidence revisions, and usage accounting. The [prior-art notes](RESEARCH.md) explain the overlap.
