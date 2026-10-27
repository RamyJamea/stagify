"""Run documentation examples through the real Gemini SDK with simulated HTTP responses.

No Gemini request leaves this process. Responses and usage are fixtures, not model output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import runpy
from pathlib import Path
from unittest.mock import patch

import httpx
from google import genai

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {"basic", "gemini", "analysis_with_cleaner", "long_tool_loop"}
MODEL = "gemini-3.8-flash"


class GeminiSimulation:
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.requests: list[dict] = []
        self.parent_step = 0
        self.summary_calls = 0
        self.offloaded_messages = 0

    @staticmethod
    def tool_results(payload: dict) -> list[tuple[str, dict]]:
        return [
            (step["name"], json.loads(step["result"][0]["text"]))
            for step in payload["input"]
            if step.get("type") == "function_result"
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path.endswith("/interactions")
        payload = json.loads(request.content)
        assert payload["model"] == MODEL
        assert payload["store"] is False and payload["stream"] is False
        assert "temperature" not in payload["generation_config"]
        assert "top_p" not in payload["generation_config"]
        self.requests.append(payload)
        results = self.tool_results(payload)
        self.offloaded_messages += sum(bool(value.get("offloaded")) for _, value in results)
        instructions = payload.get("system_instruction", "")

        if instructions.startswith("Summarize historical"):
            self.summary_calls += 1
            data = json.loads(payload["input"][0]["content"][0]["text"])
            ids = [
                event["content"]["evidence_id"]
                for event in data["events_data"]
                if isinstance(event["content"], dict) and event["content"].get("evidence_id")
            ]
            text = (
                data["previous_summary_data"]
                + " Historical batch observations; evidence IDs: "
                + ", ".join(ids)
                + ". Use current compute_total evidence for the final total."
            )
            steps = [{"type": "model_output", "content": [{"type": "text", "text": text}]}]
            status = "completed"
        else:
            name, arguments = self.select_call(instructions, results)
            assert name in {tool["name"] for tool in payload["tools"]}
            steps = [
                {"type": "thought", "signature": "simulated-opaque-signature"},
                {
                    "type": "function_call",
                    "id": f"simulated-call-{len(self.requests)}",
                    "name": name,
                    "arguments": arguments,
                },
            ]
            status = "requires_action"
        return httpx.Response(
            200,
            json={
                "id": f"simulated-interaction-{len(self.requests)}",
                "model": MODEL,
                "status": status,
                "steps": steps,
                "usage": {"total_input_tokens": 100, "total_output_tokens": 20},
            },
        )

    def select_call(self, instructions: str, results: list[tuple[str, dict]]) -> tuple[str, dict]:
        if self.scenario == "basic":
            return "complete_stage", {"text": "HELLO STAGIFY"}
        if self.scenario == "gemini":
            return ("double", {"value": 21}) if not results else ("complete_stage", {"value": 42})
        if instructions.startswith("Prepare"):
            return (
                (
                    "normalize_amounts"
                    if self.scenario == "analysis_with_cleaner"
                    else "normalize",
                    {},
                )
                if not results
                else ("complete_stage", {"text": "Amounts normalized; all rows retained."})
            )
        if self.scenario == "analysis_with_cleaner":
            if not results:
                return "clean_data", {"task": "Normalize sales amount strings."}
            name, value = results[-1]
            if name == "clean_data":
                return "total_sales", {}
            if name == "total_sales":
                return "save_memory", {
                    "key": "revenue",
                    "value": value["data"]["total"],
                    "evidence_ids": [value["evidence_id"]],
                }
            return "complete_stage", {"text": "Total sales are 24.0 across both rows."}

        step = self.parent_step
        self.parent_step += 1
        if step == 0:
            return "clean_data", {"task": "Normalize all amounts; retain rows."}
        if step <= 12:
            return "read_batch", {"offset": (step - 1) * 5}
        if step == 13:
            return "compute_total", {}
        if step == 14:
            value = next(value for name, value in reversed(results) if name == "compute_total")
            return "save_memory", {
                "key": "revenue",
                "value": value["data"]["total"],
                "evidence_ids": [value["evidence_id"]],
            }
        return "complete_stage", {"text": "Total sales: 1830.0 across 60 rows."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", type=Path)
    args = parser.parse_args()
    example = args.example.resolve()
    if example.parent != ROOT / "examples" or example.stem not in SCENARIOS:
        parser.error(
            "Choose basic.py, gemini.py, analysis_with_cleaner.py, or long_tool_loop.py under examples/"
        )
    simulations: list[GeminiSimulation] = []
    http_clients: list[httpx.AsyncClient] = []
    original_client = genai.Client

    class SimulatedClient(original_client):
        def __init__(self, *client_args, **kwargs):
            simulation = GeminiSimulation(example.stem)
            simulations.append(simulation)
            http_client = httpx.AsyncClient(transport=httpx.MockTransport(simulation))
            http_clients.append(http_client)
            options = dict(kwargs.get("http_options") or {})
            options["httpx_async_client"] = http_client
            kwargs["http_options"] = options
            super().__init__(*client_args, **kwargs)

    print(f"SIMULATED Gemini Interactions responses for {MODEL}; no live API calls.", flush=True)
    try:
        with (
            patch.object(genai, "Client", SimulatedClient),
            patch.dict(os.environ, {"GEMINI_API_KEY": "simulated-key-no-network"}),
        ):
            runpy.run_path(str(example), run_name="__main__")
    finally:
        for http_client in http_clients:
            asyncio.run(http_client.aclose())
    assert simulations and all(simulation.requests for simulation in simulations)
    if example.stem == "long_tool_loop":
        assert simulations[0].summary_calls > 0
        assert simulations[0].offloaded_messages > 0
    print(
        f"Verified {sum(len(s.requests) for s in simulations)} simulated Interactions HTTP requests "
        "through the real Google SDK and Stagify adapter. Usage values are fixtures."
    )


if __name__ == "__main__":
    main()
