"""A complete typed tool loop without model credentials."""

import asyncio

from pydantic import BaseModel

from stagify import ModelResponse, Runner, Stage, TokenUsage, ToolCall, ToolContext, tool
from stagify.testing import ScriptedProvider


class Question(BaseModel):
    task: str


class Number(BaseModel):
    value: int


class Answer(BaseModel):
    value: int


@tool
def double(args: Number, ctx: ToolContext):
    """Double one integer."""
    return {"value": args.value * 2}


async def main():
    provider = ScriptedProvider(
        [
            ModelResponse(
                calls=(ToolCall("double-1", "double", {"value": 21}),),
                usage=TokenUsage(input_tokens=100, output_tokens=20),
            ),
            ModelResponse(
                calls=(ToolCall("finish-1", "complete_stage", {"value": 42}),),
                usage=TokenUsage(input_tokens=100, output_tokens=20),
            ),
        ]
    )
    stage = Stage("analysis", "Answer using the available tools.", Question, Answer, tools=[double])
    result = await Runner(provider).run(stage, {"task": "What is double 21?"})
    assert result.output.value == 42
    assert result.usage.total.model_calls == 2
    assert result.usage.total.total_tokens == 240
    print("Answer:", result.output.value)
    print("Model calls:", result.usage.total.model_calls)
    print("Tokens:", result.usage.total.total_tokens)


if __name__ == "__main__":
    asyncio.run(main())
