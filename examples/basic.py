"""Two typed stages with an explicit handoff; no API key required."""

import asyncio

from pydantic import BaseModel

from stagify import ModelResponse, Runner, Stage, TokenUsage, ToolCall
from stagify.testing import ScriptedProvider


class Request(BaseModel):
    text: str


class Reply(BaseModel):
    text: str


def respond(request):
    value = request.messages[0].content["text"]
    return ModelResponse(
        calls=(ToolCall("finish", "complete_stage", {"text": value.upper()}),),
        usage=TokenUsage(input_tokens=100, output_tokens=20),
    )


async def main():
    runner = Runner(ScriptedProvider(respond))
    draft = Stage("draft", "Draft the text.", Request, Reply)
    review = Stage("review", "Review the text.", Request, Reply)
    first = await runner.run(draft, {"text": "hello stagify"})
    second = await runner.run(review, {"text": first.output.text})
    assert second.output.text == "HELLO STAGIFY"
    print(second.output.text)
    print("Synthetic example usage:", second.usage.total.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
