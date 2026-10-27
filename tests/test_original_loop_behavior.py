import asyncio

from pydantic import BaseModel

from stagify import ModelResponse, RunLimits, Runner, Stage, ToolCall, tool
from stagify.testing import ScriptedProvider


class Input(BaseModel):
    task: str


class Output(BaseModel):
    text: str


class Empty(BaseModel):
    pass


@tool
def inspect_data(args: Empty, ctx):
    return {"value": 7}


def test_original_last_request_completion_restriction_and_budget_instruction():
    provider = ScriptedProvider(
        [
            ModelResponse(
                calls=(ToolCall("inspect", "inspect_data", {}),), status="requires_action"
            ),
            ModelResponse(
                calls=(ToolCall("done", "complete_stage", {"text": "done"}),),
                status="requires_action",
            ),
        ]
    )
    stage = Stage("analysis", "Original instructions.", Input, Output, tools=[inspect_data])
    result = asyncio.run(
        Runner(provider, limits=RunLimits(max_model_calls=2)).run(stage, {"task": "x"})
    )
    assert result.status == "completed"
    assert {t.name for t in provider.requests[0].tools} == {"inspect_data", "complete_stage"}
    assert {t.name for t in provider.requests[1].tools} == {"complete_stage"}
    assert (
        "Remaining provider requests: 2, including final submission."
        in provider.requests[0].instructions
    )
    assert (
        "Remaining provider requests: 1, including final submission."
        in provider.requests[1].instructions
    )
