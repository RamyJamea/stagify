import asyncio

import pytest
from pydantic import BaseModel
from structlog.testing import capture_logs

from stagify import ModelResponse, RunContext, RunLimits, Runner, Stage, TokenUsage, ToolCall, tool
from stagify.errors import ConfigurationError, RunLimitExceeded
from stagify.testing import ScriptedProvider


class Input(BaseModel):
    task: str
    optional: str = "not needed"


class Output(BaseModel):
    text: str


class Empty(BaseModel):
    pass


def done():
    return ModelResponse(
        calls=(ToolCall("complete", "complete_stage", {"text": "done"}),),
        usage=TokenUsage(input_tokens=1, output_tokens=1),
    )


def test_stage_optional_field_projection_and_result_json():
    provider = ScriptedProvider([done()])
    stage = Stage("example", "Example.", Input, Output, context_fields=("task",))
    result = asyncio.run(Runner(provider).run(stage, {"task": "required", "optional": "excluded"}))
    assert provider.requests[0].messages[0].content == {"task": "required"}
    assert '"completed"' in result.model_dump_json()


def test_two_concurrent_runs_do_not_mix_log_identifiers():
    async def run():
        runner = Runner(ScriptedProvider(lambda request: done()), verbose=True)
        stage = Stage("example", "Example.", Input, Output)
        return await asyncio.gather(
            runner.run(stage, {"task": "a"}), runner.run(stage, {"task": "b"})
        )

    with capture_logs() as logs:
        results = asyncio.run(run())
    ids = {result.run_id for result in results}
    assert len(ids) == 2
    stage_events = [event for event in logs if event["event"] == "stage.completed"]
    assert {event["run_id"] for event in stage_events} == ids
    assert len({event["stage_invocation_id"] for event in stage_events}) == 2


def test_run_verbose_overrides_stage_default():
    stage = Stage("example", "Example.", Input, Output, verbose=False)
    with capture_logs() as logs:
        asyncio.run(
            Runner(ScriptedProvider([done()]), verbose=False).run(
                stage, {"task": "x"}, verbose=True
            )
        )
    assert any(event["event"] == "provider.request" for event in logs)


def test_read_evidence_and_save_memory_are_working_tools():
    @tool(reads={"sales"})
    def measure(args: Empty, ctx):
        return {"value": len(ctx.resource("sales"))}

    step = 0

    def respond(request):
        nonlocal step
        step += 1
        tools = [message.content for message in request.messages if message.role == "tool"]
        if step == 1:
            name, args = "measure", {}
        elif step == 2:
            name, args = (
                "read_evidence",
                {"evidence_id": tools[0]["evidence_id"], "pointer": "/value"},
            )
        elif step == 3:
            name, args = (
                "save_memory",
                {"key": "count", "value": 3, "evidence_ids": [tools[0]["evidence_id"]]},
            )
        else:
            name, args = "complete_stage", {"text": "done"}
        return ModelResponse(
            calls=(ToolCall(str(step), name, args),),
            usage=TokenUsage(input_tokens=1, output_tokens=1),
        )

    context = RunContext(resources={"sales": [1, 2, 3]})
    stage = Stage(
        "example",
        "Example.",
        Input,
        Output,
        tools=[measure],
        memory=True,
        required_memory=("count",),
    )
    result = asyncio.run(
        Runner(ScriptedProvider(respond)).run(stage, {"task": "x"}, context=context)
    )
    assert result.status == "completed"
    assert len(result.evidence_ids) == 1
    assert context.memory.entries["count"].value == 3


def test_caller_cannot_reuse_active_run_context():
    context = RunContext()
    context._active = True
    with pytest.raises(ConfigurationError):
        asyncio.run(
            Runner(ScriptedProvider([])).run(Stage("x", "x", Input), {"task": "x"}, context=context)
        )


def test_provider_retry_budget_is_bounded():
    from stagify.errors import ProviderTransientError

    provider = ScriptedProvider(lambda _: ProviderTransientError(retry_after=0))
    with pytest.raises(RunLimitExceeded) as error:
        asyncio.run(
            Runner(provider, limits=RunLimits(max_model_calls=2)).run(
                Stage("x", "x", Input), {"task": "x"}
            )
        )
    assert error.value.result.usage.total.model_calls == 2
