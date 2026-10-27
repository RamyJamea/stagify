import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel, ConfigDict

from stagify import ModelResponse, Runner, Stage, ToolCall
from stagify.errors import (
    ProviderOutputError,
    ProviderTransientError,
    StageCompletionError,
    StageModelLimitExceeded,
    SubstageError,
)
from stagify.testing import ScriptedProvider


class Input(BaseModel):
    task: str


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


def complete(identity="done"):
    return ModelResponse(calls=(ToolCall(identity, "complete_stage", {}),))


def test_child_uses_its_own_provider_and_output_allocation():
    parent = ScriptedProvider(
        [
            ModelResponse(calls=(ToolCall("child", "clean_data", {"task": "clean"}),)),
            complete(),
        ]
    )
    cleaner = ScriptedProvider([complete("cleaned")])
    child = Stage("clean", "Clean.", Input, Empty, provider=cleaner, max_output_tokens=128)
    stage = Stage("analyze", "Analyze.", Input, Empty, tools=(child.as_tool(name="clean_data"),))
    result = asyncio.run(Runner(parent).run(stage, {"task": "report"}))
    assert len(parent.requests) == 2
    assert len(cleaner.requests) == 1
    assert cleaner.requests[0].max_output_tokens == 128
    assert result.children[0].status == "completed"
    assert result.usage.total.model_calls == 3


def test_provider_failure_on_last_allowed_request_never_becomes_partial():
    error = ProviderTransientError(retry_after=0)
    provider = ScriptedProvider([error])
    stage = Stage("analyze", "Analyze.", Input, Empty, max_model_calls=1, allow_partial=True)
    with pytest.raises(ProviderTransientError) as caught:
        asyncio.run(Runner(provider).run(stage, {"task": "report"}))
    assert caught.value is error
    assert caught.value.result.status == "failed"
    assert len(provider.requests) == 1


def test_only_final_unsubmitted_response_is_a_stage_budget_failure():
    stage = Stage("analyze", "Analyze.", Input, Empty, max_model_calls=1)
    provider = ScriptedProvider([ModelResponse(text="Unsubmitted findings.")])
    with pytest.raises(StageModelLimitExceeded) as caught:
        asyncio.run(Runner(provider).run(stage, {"task": "report"}))
    assert caught.value.result.stage_name == "analyze"
    provider = ScriptedProvider([ModelResponse(text="Premature exit.")])
    with pytest.raises(ProviderOutputError):
        asyncio.run(
            Runner(provider).run(
                Stage("analyze", "Analyze.", Input, Empty, max_model_calls=2), {"task": "report"}
            )
        )


def test_invalid_final_completion_does_not_become_budget_exhaustion():
    stage = Stage("analyze", "Analyze.", Input, Empty, max_model_calls=1, max_completion_repairs=0)
    provider = ScriptedProvider(
        [ModelResponse(calls=(ToolCall("bad", "complete_stage", {"findings": "replacement"}),))]
    )
    with pytest.raises(StageCompletionError):
        asyncio.run(Runner(provider).run(stage, {"task": "report"}))


def test_cleaner_budget_failure_remains_a_child_error():
    cleaner = ScriptedProvider([ModelResponse(text="Unsubmitted cleaning.")])
    child = Stage("clean", "Clean.", Input, Empty, max_model_calls=1, provider=cleaner)
    parent = ScriptedProvider(
        [ModelResponse(calls=(ToolCall("child", "clean_data", {"task": "clean"}),))]
    )
    stage = Stage("analyze", "Analyze.", Input, Empty, tools=(child.as_tool(name="clean_data"),))
    with pytest.raises(SubstageError) as caught:
        asyncio.run(Runner(parent).run(stage, {"task": "report"}))
    assert isinstance(caught.value.__cause__, StageModelLimitExceeded)


def test_pacing_applies_to_retries_and_child_requests():
    parent = ScriptedProvider(
        [
            ProviderTransientError(retry_after=0),
            ModelResponse(calls=(ToolCall("child", "clean_data", {"task": "clean"}),)),
            complete(),
        ]
    )
    cleaner = ScriptedProvider([complete("cleaned")])
    child = Stage("clean", "Clean.", Input, Empty, provider=cleaner)
    stage = Stage("analyze", "Analyze.", Input, Empty, tools=(child.as_tool(name="clean_data"),))
    with patch("stagify.runner.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(Runner(parent, min_interval_seconds=0.25).run(stage, {"task": "report"}))
    assert sum(call.args == (0.25,) for call in sleep.call_args_list) == 4
