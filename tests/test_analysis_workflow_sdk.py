import asyncio
import runpy
from pathlib import Path

import httpx
from google import genai

from stagify import RunContext, RunLimits, Runner
from stagify.providers.google import GoogleProvider

ROOT = Path(__file__).resolve().parents[1]


def test_reference_workflow_uses_real_interactions_sdk_with_simulated_http():
    example = runpy.run_path(str(ROOT / "examples/analysis_workflow.py"))
    simulator = runpy.run_path(str(ROOT / "scripts/simulate_gemini.py"))
    simulation = simulator["GeminiSimulation"]("analysis_workflow")

    async def run():
        http = httpx.AsyncClient(transport=httpx.MockTransport(simulation))
        client = genai.Client(
            api_key="simulated-no-network",
            http_options={"httpx_async_client": http, "retry_options": {"attempts": 0}},
        )
        provider = GoogleProvider(
            "gemini-3.8-flash",
            client=client,
            temperature=None,
            top_p=None,
        )
        context = RunContext(resources={"sales": [{"amount": " 10.5 "}, {"amount": "13.5"}]})
        try:
            async with Runner(provider, limits=RunLimits(max_model_calls=20)) as runner:
                result = await runner.run(
                    example["build_workflow"](),
                    {"task": "Analyze recorded sales."},
                    context=context,
                )
            assert result.status == "completed"
            assert "24.0" in result.output
            assert result.usage.total.model_calls == len(simulation.requests) == 8
            assert result.usage.total.input_tokens == 800
            assert result.usage.total.output_tokens == 160
            analysis = result.steps["analysis"]
            assert analysis.usage.own.model_calls == 4
            assert analysis.usage.children.model_calls == 2
            assert analysis.context["revision"] == 1
            assert analysis.children[0].history[0].content["revision"] == 0
            assert context.memory.values(context.revisions) == {"revenue": "24.0"}
        finally:
            await client.aio.aclose()
            await http.aclose()

    asyncio.run(run())
    analysis = next(
        request
        for request in simulation.requests
        if request["system_instruction"].startswith("Call clean_data")
    )
    cleaner = next(tool for tool in analysis["tools"] if tool["name"] == "clean_data")
    complete = next(tool for tool in analysis["tools"] if tool["name"] == "complete_stage")
    assert set(cleaner["parameters"]["properties"]) == {"task"}
    assert complete["parameters"]["properties"] == {}
    assert any(
        step.get("signature") == "simulated-opaque-signature"
        for request in simulation.requests
        for step in request["input"]
    )
