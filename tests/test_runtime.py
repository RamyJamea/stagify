import asyncio

import pytest
from pydantic import BaseModel, ConfigDict
from structlog.testing import capture_logs

from stagify import (
    ArtifactOffload,
    ContextPolicies,
    ModelResponse,
    RunContext,
    RunLimits,
    Runner,
    Stage,
    Summarize,
    TokenUsage,
    ToolCall,
    tool,
)
from stagify.errors import (
    ConfigurationError,
    ContextBudgetExceeded,
    ContextValidationError,
    ProviderAuthenticationError,
    ProviderOutputError,
    ProviderTransientError,
    RunLimitExceeded,
    StageCompletionError,
    StageTimeoutError,
    SubstageError,
)
from stagify.testing import ScriptedProvider


class Input(BaseModel):
    task: str


class Output(BaseModel):
    text: str


class Number(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: int


class Empty(BaseModel):
    pass


USAGE = TokenUsage(input_tokens=10, output_tokens=5, cached_input_tokens=2, reasoning_tokens=1)


def call(name, args, identity):
    return ModelResponse(calls=(ToolCall(identity, name, args),), usage=USAGE)


def done(text="done", identity="done"):
    return call("complete_stage", {"text": text}, identity)


@tool
def double(args: Number, ctx):
    return {"value": args.number * 2}


def stage(**kwargs):
    return Stage(
        name="analysis",
        instructions="Perform the task.",
        input_model=Input,
        output_model=Output,
        **kwargs,
    )


def test_typed_tool_completion_and_usage():
    provider = ScriptedProvider([call("double", {"number": 4}, "one"), done()])
    context = RunContext()
    result = asyncio.run(
        Runner(provider).run(stage(tools=[double]), {"task": "double"}, context=context)
    )
    assert result.output == Output(text="done")
    assert result.status == "completed"
    assert result.usage.own.input_tokens == 20
    assert result.usage.total.total_tokens == 30
    assert result.usage.total.cached_input_tokens == 4
    assert result.usage.total.tool_calls == 2
    assert context.artifacts.get(result.evidence_ids[0]).data == {"value": 8}
    assert provider.requests[1].messages[-1].content["data"] == {"value": 8}


def test_plain_text_stage_and_explicit_handoff():
    provider = ScriptedProvider(
        [ModelResponse(text="hello", usage=USAGE), ModelResponse(text="HELLO", usage=USAGE)]
    )
    first = Stage(name="first", instructions="Draft.", input_model=Input)
    second = Stage(name="second", instructions="Revise.", input_model=Input)

    async def run():
        runner = Runner(provider)
        a = await runner.run(first, {"task": "draft"})
        return await runner.run(second, {"task": a.output})

    assert asyncio.run(run()).output == "HELLO"
    assert provider.requests[1].messages[0].content == {"task": "hello"}
    assert len(provider.requests[1].messages) == 1


def test_argument_error_is_feedback_not_evidence_or_execution():
    provider = ScriptedProvider(
        [call("double", {"number": "bad"}, "one"), call("double", {"number": 4}, "two"), done()]
    )
    result = asyncio.run(Runner(provider).run(stage(tools=[double]), {"task": "double"}))
    assert len(result.evidence_ids) == 1
    assert provider.requests[1].messages[-1].content["code"] == "invalid_tool_input"
    assert "bad" not in provider.requests[1].messages[-1].content["message"]


def test_missing_context_fails_before_provider_request():
    provider = ScriptedProvider([])
    with pytest.raises(ContextValidationError) as error:
        asyncio.run(Runner(provider).run(stage(), {}))
    assert provider.requests == []
    assert error.value.result.status == "failed"
    assert error.value.result.usage.total.model_calls == 0


@pytest.mark.parametrize(
    "calls",
    [
        (ToolCall("x", "missing", {}),),
        (ToolCall("x", "double", {"number": 1}), ToolCall("x", "double", {"number": 2})),
        (ToolCall("a", "complete_stage", {"text": "ok"}), ToolCall("b", "double", {"number": 2})),
    ],
)
def test_invalid_response_executes_no_tools(calls):
    provider = ScriptedProvider([ModelResponse(calls=calls, usage=USAGE)])
    with pytest.raises(ProviderOutputError) as error:
        asyncio.run(Runner(provider).run(stage(tools=[double]), {"task": "work"}))
    assert error.value.result.evidence_ids == []
    assert error.value.result.usage.total.tool_calls == 0


def test_completion_repair_has_a_bound():
    provider = ScriptedProvider([call("complete_stage", {}, "bad"), done(identity="good")])
    result = asyncio.run(Runner(provider).run(stage(), {"task": "work"}))
    assert result.output.text == "done"
    assert result.usage.total.model_calls == 2
    provider = ScriptedProvider([call("complete_stage", {}, "bad")])
    with pytest.raises(StageCompletionError):
        asyncio.run(Runner(provider).run(stage(max_completion_repairs=0), {"task": "work"}))


def test_transient_retry_does_not_reexecute_completed_tools():
    provider = ScriptedProvider(
        [
            call("double", {"number": 3}, "one"),
            ProviderTransientError(retry_after=0),
            done(),
        ]
    )
    result = asyncio.run(Runner(provider).run(stage(tools=[double]), {"task": "work"}))
    assert len(result.evidence_ids) == 1
    assert result.usage.total.model_calls == 3
    assert result.usage.total.input_tokens is None
    assert not result.usage.total.complete


def test_authentication_failure_is_not_retried():
    provider = ScriptedProvider([ProviderAuthenticationError("Credentials rejected")])
    with pytest.raises(ProviderAuthenticationError) as error:
        asyncio.run(Runner(provider).run(stage(), {"task": "work"}))
    assert len(provider.requests) == 1
    assert error.value.result.usage.total.model_calls == 1


def test_substage_is_a_tool_with_private_context_and_aggregated_usage():
    cleaner = Stage(name="cleaner", instructions="Clean.", input_model=Input, output_model=Output)
    parent = stage(tools=[cleaner.as_tool(name="clean_data")])
    provider = ScriptedProvider(
        [
            call("clean_data", {"task": "one preparation job"}, "delegate"),
            done("cleaned", "child_done"),
            done("report", "parent_done"),
        ]
    )
    result = asyncio.run(Runner(provider).run(parent, {"task": "analyze privately"}))
    assert result.output.text == "report"
    assert len(result.children) == 1
    child = result.children[0]
    assert child.parent_invocation_id == result.invocation_id
    assert child.usage.total.model_calls == 1
    assert result.usage.own.input_tokens == 20
    assert result.usage.children.input_tokens == 10
    assert result.usage.total.input_tokens == 30
    assert result.usage.total.model_calls == 3
    assert provider.requests[1].messages[0].content == {"task": "one preparation job"}
    assert len(provider.requests[1].messages) == 1
    assert "usage" not in provider.requests[2].messages[-1].content


def test_children_cannot_escape_the_shared_model_budget():
    child = Stage(name="child", instructions="Work.", input_model=Input, output_model=Output)
    provider = ScriptedProvider([call("child", {"task": "child"}, "sub"), done("child")])
    with pytest.raises(RunLimitExceeded) as error:
        asyncio.run(
            Runner(provider, limits=RunLimits(max_model_calls=2)).run(
                stage(tools=[child.as_tool()]), {"task": "parent"}
            )
        )
    assert error.value.result.usage.total.model_calls == 2
    assert len(error.value.result.children) == 1


def test_repeated_child_calls_get_fresh_histories():
    child = Stage(name="child", instructions="Work.", input_model=Input, output_model=Output)
    provider = ScriptedProvider(
        [
            call("child", {"task": "a"}, "sub1"),
            done("a", "c1"),
            call("child", {"task": "b"}, "sub2"),
            done("b", "c2"),
            done(),
        ]
    )
    result = asyncio.run(Runner(provider).run(stage(tools=[child.as_tool()]), {"task": "parent"}))
    assert len(result.children) == 2
    assert result.children[0].invocation_id != result.children[1].invocation_id
    assert len(provider.requests[3].messages) == 1


def test_mutating_child_failure_reconciles_actual_revision():
    @tool(writes={"sales"})
    def mutate(args: Empty, ctx):
        ctx.resource("sales").append(1)
        raise RuntimeError("private data must not appear in the model response")

    child = Stage(
        name="child",
        instructions="Prepare.",
        input_model=Input,
        output_model=Output,
        tools=[mutate],
    )
    provider = ScriptedProvider(
        [
            call("child", {"task": "prepare"}, "sub"),
            call("mutate", {}, "mutate"),
            done(),
        ]
    )
    context = RunContext(resources={"sales": []})
    result = asyncio.run(
        Runner(provider).run(
            stage(tools=[child.as_tool(on_error="return")]), {"task": "parent"}, context=context
        )
    )
    assert context.revisions["sales"] == 1
    assert result.children[0].status == "failed"
    assert result.usage.total.model_calls == 3
    assert provider.requests[-1].messages[-1].content["resource_versions"] == {"sales": 1}
    assert "private data" not in str(provider.requests[-1].messages[-1].content)


def test_child_failure_default_is_typed():
    child = Stage(name="child", instructions="Prepare.", input_model=Input, output_model=Output)
    provider = ScriptedProvider(
        [call("child", {"task": "prepare"}, "sub"), ProviderAuthenticationError("failed")]
    )
    with pytest.raises(SubstageError) as error:
        asyncio.run(Runner(provider).run(stage(tools=[child.as_tool()]), {"task": "parent"}))
    assert error.value.result.children[0].status == "failed"


def test_allow_partial_does_not_fabricate_completion():
    provider = ScriptedProvider([call("complete_stage", {}, "one")])
    result = asyncio.run(
        Runner(provider, limits=RunLimits(max_model_calls=1)).run(
            stage(tools=[double], allow_partial=True), {"task": "work"}
        )
    )
    assert result.status == "partial"
    assert result.output is None
    assert result.error.code == "run_limit_exceeded"


def test_timeout_and_cancellation_preserve_result_and_mutation_status():
    @tool(writes={"sales"})
    async def wait(args: Empty, ctx):
        await asyncio.sleep(5)

    context = RunContext(resources={"sales": []})
    provider = ScriptedProvider([call("wait", {}, "wait")])
    with pytest.raises(StageTimeoutError):
        asyncio.run(
            Runner(provider).run(
                stage(tools=[wait], timeout_seconds=0.01), {"task": "work"}, context=context
            )
        )
    assert context.last_result.status == "failed"
    assert context.revisions["sales"] == 1

    async def cancel():
        provider = ScriptedProvider([call("wait", {}, "wait")])
        context = RunContext(resources={"sales": []})
        task = asyncio.create_task(
            Runner(provider).run(stage(tools=[wait]), {"task": "work"}, context=context)
        )
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert context.last_result.status == "cancelled"
        assert not context._active

    asyncio.run(cancel())


def test_verbose_changes_detail_and_keeps_payloads_out_of_logs():
    for verbose in (False, True):
        with capture_logs() as logs:
            asyncio.run(
                Runner(ScriptedProvider([done()]), verbose=verbose).run(
                    stage(), {"task": "TOP_SECRET_PAYLOAD"}
                )
            )
        assert any(e["event"] == "stage.completed" for e in logs)
        assert any(e["event"] == "provider.request" for e in logs) == verbose
        assert "TOP_SECRET_PAYLOAD" not in str(logs)


def test_context_is_not_reduced_when_policies_are_disabled():
    @tool
    def large(args: Empty, ctx):
        return {"rows": list(range(1000))}

    policies = ContextPolicies(
        enabled=True, artifact_offload=ArtifactOffload(enabled=True, max_chars=600)
    )
    provider = ScriptedProvider([call("large", {}, "large"), done()])
    asyncio.run(
        Runner(provider).run(
            stage(tools=[large], context_policies=policies),
            {"task": "work"},
            apply_context_policies=False,
        )
    )
    assert len(provider.requests[1].messages[-1].content["data"]["rows"]) == 1000
    assert "offloaded" not in provider.requests[1].messages[-1].content


def test_offload_retains_exact_source_and_original_transcript():
    @tool
    def large(args: Empty, ctx):
        return {"rows": list(range(1000))}

    policies = ContextPolicies(
        enabled=True, artifact_offload=ArtifactOffload(enabled=True, max_chars=600)
    )
    provider = ScriptedProvider([call("large", {}, "large"), done()])
    context = RunContext()
    result = asyncio.run(
        Runner(provider).run(
            stage(tools=[large], context_policies=policies), {"task": "work"}, context=context
        )
    )
    visible = provider.requests[1].messages[-1].content
    assert visible["offloaded"] is True
    assert "data" not in visible
    assert len(result.history[2].content["data"]["rows"]) == 1000
    page = context.artifacts.read(visible["evidence_id"], "/rows", offset=990, limit=10)
    assert page["data"] == list(range(990, 1000))


def test_protected_input_that_cannot_fit_is_an_explicit_error():
    provider = ScriptedProvider([])
    policies = ContextPolicies(
        enabled=True, protected_fields=("task",), history=Summarize(enabled=True)
    )
    with pytest.raises(ContextBudgetExceeded):
        asyncio.run(
            Runner(provider, limits=RunLimits(max_input_tokens=300)).run(
                stage(context_policies=policies), {"task": "must remain exact" * 1000}
            )
        )
    assert not provider.requests


def test_one_hundred_tool_batches_compact_inside_one_user_request():
    count = 0

    @tool
    def observe(args: Number, ctx):
        return {"value": args.number, "details": "measurement " * 30}

    def respond(request):
        nonlocal count
        if request.instructions.startswith("Summarize"):
            return ModelResponse(
                text="Prior observations remain available through their evidence handles.",
                usage=USAGE,
            )
        count += 1
        if count <= 105:
            return call("observe", {"number": count}, f"observe-{count}")
        return done()

    provider = ScriptedProvider(respond)
    policies = ContextPolicies(
        enabled=True,
        protected_fields=("task",),
        history=Summarize(enabled=True, recent_batches=1, max_input_tokens=2500),
    )
    result = asyncio.run(
        Runner(
            provider,
            limits=RunLimits(max_model_calls=300, max_tool_calls=120, max_input_tokens=3000),
        ).run(
            stage(tools=[observe], context_policies=policies),
            {"task": "Keep the denominator 100 exact"},
        )
    )
    assert count == 106
    assert result.compactions
    assert result.usage.by_purpose["summarize"].model_calls > 0
    assert len(result.evidence_ids) == 105
    assert all(
        r.messages[0].content["task"] == "Keep the denominator 100 exact"
        for r in provider.requests
        if not r.instructions.startswith("Summarize")
    )


def test_unknown_or_invalid_contract_settings_fail_early():
    with pytest.raises(ConfigurationError):
        stage(context_fields=())
    with pytest.raises(ConfigurationError):
        stage(context_policies=ContextPolicies(protected_fields=("unknown",)))
    with pytest.raises(ConfigurationError):
        stage(tools=[double, double])
    with pytest.raises(ValueError):
        RunLimits(max_model_calls=0)


def test_resource_mutation_blocks_stale_required_findings():
    @tool(writes={"sales"})
    def mutate(args: Empty, ctx):
        ctx.resource("sales").append(1)
        return {"changed": True}

    context = RunContext(resources={"sales": []})
    evidence = context.artifacts.record(
        run_id="before",
        stage_id="before",
        tool_name="read",
        arguments={},
        versions={"sales": 0},
        data={"total": 100},
    )
    context.memory.update("total", 100, evidence_ids=(evidence.id,), dependencies={"sales": 0})
    provider = ScriptedProvider(
        [call("mutate", {}, "mut"), done(identity="c1"), done(identity="c2")]
    )
    with pytest.raises(StageCompletionError):
        asyncio.run(
            Runner(provider).run(
                stage(tools=[mutate], required_memory=("total",)), {"task": "work"}, context=context
            )
        )
    assert context.memory.entries["total"].status(context.revisions) == "stale"
