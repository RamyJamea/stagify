import asyncio

import pytest
from pydantic import BaseModel

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
from stagify.errors import ContextBudgetExceeded, ProviderAuthenticationError
from stagify.testing import ScriptedProvider


class Input(BaseModel):
    task: str


class Empty(BaseModel):
    pass


@tool
def large(args: Empty, ctx):
    return {"rows": list(range(1000))}


def responses():
    usage = TokenUsage(input_tokens=10, output_tokens=2)
    return [
        ModelResponse(calls=(ToolCall("large", "large", {}),), usage=usage),
        ModelResponse(text="done", usage=usage),
    ]


@pytest.mark.parametrize(
    "runner_enabled, stage_enabled, override, offloaded",
    [
        (False, None, None, False),
        (True, None, None, True),
        (True, False, None, False),
        (False, True, None, True),
        (True, True, False, False),
        (False, False, True, True),
    ],
)
def test_policy_precedence(runner_enabled, stage_enabled, override, offloaded):
    def policy(enabled):
        return ContextPolicies(
            enabled=enabled, artifact_offload=ArtifactOffload(enabled=True, max_chars=600)
        )

    provider = ScriptedProvider(responses())
    stage = Stage(
        "test",
        "Test.",
        Input,
        tools=[large],
        context_policies=policy(stage_enabled) if stage_enabled is not None else None,
    )
    asyncio.run(
        Runner(provider, context_policies=policy(runner_enabled)).run(
            stage, {"task": "work"}, apply_context_policies=override
        )
    )
    assert provider.requests[-1].messages[-1].content.get("offloaded", False) == offloaded


def test_individual_disabled_policy_does_not_become_enabled_by_run_override():
    provider = ScriptedProvider(responses())
    stage = Stage(
        "test", "Test.", Input, tools=[large], context_policies=ContextPolicies(enabled=False)
    )
    asyncio.run(Runner(provider).run(stage, {"task": "work"}, apply_context_policies=True))
    assert len(provider.requests[-1].messages[-1].content["data"]["rows"]) == 1000


def test_summary_failure_preserves_the_complete_source_history():
    count = 0

    def handler(request):
        nonlocal count
        if request.instructions.startswith("Summarize"):
            raise ProviderAuthenticationError("summarizer unavailable")
        count += 1
        return ModelResponse(
            calls=(ToolCall(str(count), "large", {}),),
            usage=TokenUsage(input_tokens=10, output_tokens=2),
        )

    context = RunContext()
    stage = Stage(
        "test",
        "Test.",
        Input,
        tools=[large],
        context_policies=ContextPolicies(
            enabled=True, history=Summarize(enabled=True, recent_batches=0, max_input_tokens=5000)
        ),
    )
    with pytest.raises(ProviderAuthenticationError) as error:
        asyncio.run(
            Runner(ScriptedProvider(handler), limits=RunLimits(max_input_tokens=5000)).run(
                stage, {"task": "preserve"}, context=context
            )
        )
    assert error.value.result.compactions == []
    assert len(error.value.result.history[2].content["data"]["rows"]) == 1000
    assert error.value.result.usage.by_purpose["summarize"].model_calls == 1


def test_policies_off_still_enforces_context_capacity():
    provider = ScriptedProvider(responses())
    stage = Stage("test", "Test.", Input, tools=[large])
    with pytest.raises(ContextBudgetExceeded):
        asyncio.run(
            Runner(provider, limits=RunLimits(max_input_tokens=1500)).run(stage, {"task": "work"})
        )
    assert len(provider.requests) == 1
