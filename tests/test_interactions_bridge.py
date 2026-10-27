import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel

from stagify import Message, ModelRequest, Runner, Stage, TokenUsage, ToolSpec
from stagify.providers.google import GoogleProvider


class Step(BaseModel):
    type: str
    signature: str | None = None
    id: str | None = None
    name: str | None = None
    arguments: dict | None = None


def response(status="requires_action", steps=None, text=""):
    return SimpleNamespace(
        id="request",
        status=status,
        output_text=text,
        usage=SimpleNamespace(
            total_input_tokens=100,
            total_output_tokens=20,
            total_cached_tokens=80,
            total_thought_tokens=10,
            total_tool_use_tokens=3,
        ),
        steps=steps
        if steps is not None
        else [
            Step(type="thought", signature="original-opaque-signature"),
            Step(type="function_call", id="a", name="lookup", arguments={"q": "x"}),
            Step(type="function_call", id="b", name="lookup", arguments={"q": "y"}),
        ],
    )


def test_packaging_bridge_uses_interactions_and_preserves_replay_and_all_usage():
    create = AsyncMock(return_value=response())
    client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
    provider = GoogleProvider("gemini-3.1-flash-lite", client=client)
    request = ModelRequest(
        "Original instructions",
        (Message("user", "task"),),
        (ToolSpec("lookup", "Lookup.", {"type": "object"}),),
        max_output_tokens=256,
    )
    result = asyncio.run(provider.generate(request))
    assert result.status == "requires_action"
    assert result.usage == TokenUsage(
        input_tokens=100,
        output_tokens=20,
        cached_input_tokens=80,
        reasoning_tokens=10,
        tool_tokens=3,
    )
    kwargs = create.call_args.kwargs
    assert kwargs["store"] is False
    assert kwargs["stream"] is False
    assert kwargs["generation_config"] == {
        "temperature": 0.0,
        "top_p": 1.0,
        "thinking_level": "low",
        "max_output_tokens": 256,
    }
    assert kwargs["input"][0] == {
        "type": "user_input",
        "content": [{"type": "text", "text": "task"}],
    }
    assert kwargs["tools"][0]["type"] == "function"
    replay = ModelRequest(
        "Original instructions",
        (
            request.messages[0],
            Message("assistant", calls=result.calls, native=result.native),
            Message("tool", {"ok": True, "data": 1}, call_id="a", name="lookup"),
            Message("tool", {"ok": True, "data": 2}, call_id="b", name="lookup"),
        ),
    )
    payload = provider._content(replay)
    assert payload[1] == {"type": "thought", "signature": "original-opaque-signature"}
    assert [item["id"] for item in payload if item["type"] == "function_call"] == ["a", "b"]
    assert [item["call_id"] for item in payload if item["type"] == "function_result"] == ["a", "b"]
    assert all(
        item["result"][0]["type"] == "text" for item in payload if item["type"] == "function_result"
    )


def test_runner_accepts_the_existing_requires_action_status():
    class Input(BaseModel):
        task: str

    class Output(BaseModel):
        text: str

    create = AsyncMock(
        return_value=response(
            status="requires_action",
            steps=[
                Step(
                    type="function_call",
                    id="complete",
                    name="complete_stage",
                    arguments={"text": "done"},
                )
            ],
        )
    )
    provider = GoogleProvider(
        "gemini-3.1-flash-lite",
        client=SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create))),
    )
    result = asyncio.run(Runner(provider).run(Stage("test", "Test.", Input, Output), {"task": "x"}))
    assert result.output.text == "done"
    assert result.usage.total.tool_tokens == 3
