import pytest

from stagify import RunContext, TokenUsage, ToolContext
from stagify.errors import EvidenceError, StateConflictError, ToolInputError
from stagify.usage import UsageLedger


def test_exact_pointer_pagination_and_bounds():
    ctx = RunContext()
    e = ctx.artifacts.record(
        run_id="r",
        stage_id="s",
        tool_name="t",
        arguments={},
        versions={},
        data={"a/b": {"x~y": [10, 20, 30]}},
    )
    page = ctx.artifacts.read(e.id, "/a~1b/x~0y", offset=1, limit=1)
    assert page["data"] == [20]
    assert page["next_offset"] == 2
    for pointer in ("/missing", "/a~1b/x~0y/-1", "/a~1b/x~0y/9"):
        with pytest.raises(EvidenceError):
            ctx.artifacts.read(e.id, pointer)
    with pytest.raises(EvidenceError):
        ctx.artifacts.read(e.id, limit=0)


def test_evidence_storage_dedup_does_not_erase_execution_identity():
    ctx = RunContext()
    kwargs = dict(run_id="r", stage_id="s", tool_name="t", arguments={}, versions={}, data=7)
    first = ctx.artifacts.record(**kwargs)
    second = ctx.artifacts.record(**kwargs)
    assert first.id != second.id
    assert first.content_hash == second.content_hash


def test_memory_update_requires_version_and_preserves_old_events():
    ctx = RunContext(resources={"sales": []})
    e = ctx.artifacts.record(
        run_id="r", stage_id="s", tool_name="t", arguments={}, versions={"sales": 0}, data=10
    )
    tool = ToolContext(
        ctx,
        run_id="r",
        stage_id="s",
        allowed_resources=frozenset({"sales"}),
        writable_resources=frozenset(),
    )
    one = tool.save("total", 10, evidence_ids=(e.id,))
    with pytest.raises(StateConflictError):
        tool.save("total", 11, evidence_ids=(e.id,))
    two = tool.save("total", 11, evidence_ids=(e.id,), expected_version=one.version)
    assert two.version == 2
    assert ctx.memory.events[0].value == 10
    ctx.revisions["sales"] += 1
    with pytest.raises(EvidenceError):
        tool.save("new", 10, evidence_ids=(e.id,))
    with pytest.raises(ToolInputError):
        tool.touch("sales")
    with pytest.raises(ToolInputError):
        tool.resource("unknown")


def test_usage_subsets_are_not_added_to_provider_total():
    ledger = UsageLedger(10, 10)
    root = ledger.start_request("root", (), "agent", "fake", None)
    root.usage = TokenUsage(
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        cached_input_tokens=80,
        reasoning_tokens=10,
    )
    child = ledger.start_request("child", ("root",), "summarize", "fake", None)
    child.usage = TokenUsage(input_tokens=50, output_tokens=10, total_tokens=60)
    grandchild = ledger.start_request("grandchild", ("root", "child"), "agent", "fake", None)
    grandchild.usage = TokenUsage(input_tokens=5, output_tokens=1)
    usage = ledger.for_stage("root")
    assert usage.total.total_tokens == 186
    assert usage.children.total_tokens == 66
    assert usage.own.total_tokens == 120
    assert ledger.for_stage("child").total.total_tokens == 66
    assert usage.total.complete


def test_unreported_failed_requests_make_totals_incomplete():
    ledger = UsageLedger(10, 10)
    ledger.start_request("root", (), "agent", "fake", None)
    totals = ledger.for_stage("root").total
    assert totals.input_tokens is None
    assert totals.total_tokens is None
    assert not totals.complete
