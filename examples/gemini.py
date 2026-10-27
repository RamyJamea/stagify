"""Live Gemini Interactions example; requires environment credentials and model access."""

import asyncio
import os

from pydantic import BaseModel

from stagify import RunLimits, Runner, Stage, ToolContext, tool
from stagify.providers.google import GoogleProvider


class Question(BaseModel):
    task: str


class Number(BaseModel):
    value: int


class Answer(BaseModel):
    value: int


@tool
def double(args: Number, ctx: ToolContext):
    """Double one integer exactly."""
    return {"value": args.value * 2}


async def main():
    stage = Stage(
        "analysis",
        "Use double to calculate the answer, then submit complete_stage.",
        Question,
        Answer,
        tools=[double],
    )
    async with GoogleProvider(
        model=os.environ["GEMINI_MODEL"],
        api_key=os.environ["GEMINI_API_KEY"],
    ) as provider:
        runner = Runner(provider, limits=RunLimits(max_model_calls=8, timeout_seconds=60))
        result = await runner.run(stage, {"task": "What is double 21?"})
        print(result.output.model_dump())
        print(result.usage.total.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
