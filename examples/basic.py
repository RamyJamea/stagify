"""Two typed Gemini stages with an explicit handoff."""

import asyncio
import os

from pydantic import BaseModel

from stagify import RunLimits, Runner, Stage
from stagify.providers.google import GoogleProvider


class Request(BaseModel):
    text: str


class Reply(BaseModel):
    text: str


async def main():
    draft = Stage("draft", "Convert the supplied text to uppercase.", Request, Reply)
    review = Stage("review", "Return the supplied uppercase text unchanged.", Request, Reply)
    async with GoogleProvider(
        model="gemini-3.8-flash",
        api_key=os.environ["GEMINI_API_KEY"],
        temperature=None,
        top_p=None,
    ) as provider:
        runner = Runner(provider, limits=RunLimits(max_model_calls=8, timeout_seconds=60))
        first = await runner.run(draft, {"text": "hello stagify"})
        second = await runner.run(review, {"text": first.output.text})
        assert second.output.text == "HELLO STAGIFY"
        print(second.output.text)
        print("Review stage Gemini usage:", second.usage.total.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
