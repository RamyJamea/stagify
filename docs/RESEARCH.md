# Research and positioning

Updated 27 October 2026.

Stagify aims to make staged context management straightforward to configure,
inspect, and test. Its proposed capabilities are not established technical
novelties. In particular, all three capabilities below already exist:

| Capability | Existing example |
| --- | --- |
| Context scoped to individual stages/agents | [LangGraph subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs) support separate state schemas, histories, and explicit input/output mapping. |
| Compression inside a long tool loop | [Pydantic AI Harness](https://pydantic.dev/docs/ai/harness/compaction/) applies strategies before model requests, including within a run. |
| Content protected from compression | [Pydantic AI pinning](https://pydantic.dev/docs/ai/harness/compaction/#pinning-content-that-survives-compaction) preserves selected content across built-in compaction strategies. |

Other relevant precedents:

- [Letta memory blocks](https://www.letta.com/blog/memory-blocks/): editable,
  bounded memory used to compile requests.
- [ACE](https://arxiv.org/abs/2510.04618): structured incremental context updates.
- [ReSum](https://arxiv.org/abs/2509.13313): continuing long search trajectories
  through periodic context summarization.
- [ACON](https://arxiv.org/abs/2510.00615): evaluating and improving observation
  and history compression based on task outcomes.
- [Graphiti/Zep provenance](https://www.getzep.com/blog/how-zep-tracks-provenance-in-agent-memory/):
  source associations maintained across fact updates and invalidation.

The product hypothesis is an integrated, small API for stage context contracts,
optional policies, nested stages, and evidence validity. Existing frameworks can
implement these behaviors. We must measure developer effort, retention, error
behavior, task correctness, latency, and total token cost before claiming an
advantage.

Operational references:

- [uv library projects](https://docs.astral.sh/uv/concepts/projects/init/)
- [uv build backend](https://docs.astral.sh/uv/concepts/build-backend/)
- [uv GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)
- [uv publishing](https://docs.astral.sh/uv/guides/package/)
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
