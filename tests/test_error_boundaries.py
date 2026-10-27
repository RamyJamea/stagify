import asyncio

import pytest
from pydantic import BaseModel

from stagify import Runner, Stage
from stagify.errors import ConfigurationError, ProviderTransientError, StageExecutionError
from stagify.testing import ScriptedProvider


class Input(BaseModel):
    task: str


@pytest.mark.parametrize("delay", [float("inf"), float("nan"), -1, "invalid"])
def test_invalid_retry_hints_fail_promptly(delay):
    provider = ScriptedProvider([ProviderTransientError(retry_after=delay)])
    with pytest.raises(ConfigurationError):
        asyncio.run(Runner(provider).run(Stage("test", "Test.", Input), {"task": "x"}))


def test_unexpected_provider_failure_is_a_stage_error_with_cause_and_snapshot():
    provider = ScriptedProvider([ValueError("private SDK configuration details")])
    with pytest.raises(StageExecutionError) as error:
        asyncio.run(Runner(provider).run(Stage("test", "Test.", Input), {"task": "x"}))
    assert isinstance(error.value.__cause__, ValueError)
    assert error.value.result.status == "failed"
    assert "private SDK" not in str(error.value)


def test_invalid_partial_output_still_has_a_typed_failure_snapshot():
    from stagify import ModelResponse, RunLimits, ToolCall
    from stagify.errors import StageCompletionError

    class Output(BaseModel):
        text: str

    stage = Stage(
        "test",
        "Test.",
        Input,
        Output,
        allow_partial=True,
        partial_output=lambda ctx: {"wrong_field": True},
    )
    provider = ScriptedProvider(
        [ModelResponse(calls=(ToolCall("complete", "complete_stage", {}),))]
    )
    with pytest.raises(StageCompletionError) as error:
        asyncio.run(Runner(provider, limits=RunLimits(max_model_calls=1)).run(stage, {"task": "x"}))
    assert error.value.result.status == "failed"
