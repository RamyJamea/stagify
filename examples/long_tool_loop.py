"""A cleaner, twelve batch reads, and bounded context; all provider usage is synthetic."""

import asyncio
from decimal import Decimal

from pydantic import BaseModel, Field

from stagify import (
    ArtifactOffload,
    ContextPolicies,
    ModelResponse,
    RunContext,
    RunLimits,
    Runner,
    Stage,
    Summarize,
    TokenUsage,
    ToolCall,
    ToolContext,
    tool,
)
from stagify.errors import ContextBudgetExceeded
from stagify.testing import ScriptedProvider


class Task(BaseModel):
    task: str


class Report(BaseModel):
    text: str


class Empty(BaseModel):
    pass


class Page(BaseModel):
    offset: int = Field(ge=0)
    limit: int = Field(default=5, ge=1, le=5)


@tool(writes={"sales"})
def normalize(args: Empty, ctx: ToolContext):
    """Normalize amount strings while retaining every sales row."""
    rows = ctx.resource("sales")
    amounts = [str(Decimal(row["amount"].strip())) for row in rows]
    for row, amount in zip(rows, amounts, strict=True):
        row["amount"] = amount
    return {"normalized_rows": len(rows)}


@tool(reads={"sales"}, projection=lambda result: {"rows": len(result["rows"])})
def read_batch(args: Page, ctx: ToolContext):
    """Read at most five sales rows, including their long source notes."""
    return {"rows": ctx.resource("sales")[args.offset : args.offset + args.limit]}


@tool(reads={"sales"})
def compute_total(args: Empty, ctx: ToolContext):
    """Calculate the exact current total independently of historical summaries."""
    rows = ctx.resource("sales")
    return {"total": str(sum((Decimal(row["amount"]) for row in rows), Decimal(0)))}


def scripted_responder():
    step = 0

    def respond(request):
        nonlocal step
        if request.instructions.startswith("Summarize historical"):
            payload = request.messages[0].content
            ids = [
                str(event["content"]["evidence_id"])
                for event in payload["events_data"]
                if isinstance(event["content"], dict) and event["content"].get("evidence_id")
            ]
            summary = (
                payload["previous_summary_data"]
                + " Historical observations; evidence IDs: "
                + ", ".join(ids)
                + ". Use current compute_total evidence for the final total."
            )
            return ModelResponse(text=summary, usage=TokenUsage(input_tokens=100, output_tokens=20))

        tools = [message for message in request.messages if message.role == "tool"]
        if request.instructions.startswith("Prepare"):
            name, args = (
                ("normalize", {})
                if not tools
                else ("complete_stage", {"text": "Normalized all 60 rows."})
            )
        else:
            if step == 0:
                name, args = "clean_data", {"task": "Normalize all amounts; retain rows."}
            elif step <= 12:
                name, args = "read_batch", {"offset": (step - 1) * 5}
            elif step == 13:
                name, args = "compute_total", {}
            elif step == 14:
                evidence = next(m.content for m in reversed(tools) if m.name == "compute_total")
                name, args = (
                    "save_memory",
                    {
                        "key": "revenue",
                        "value": evidence["data"]["total"],
                        "evidence_ids": [evidence["evidence_id"]],
                    },
                )
            else:
                name, args = "complete_stage", {"text": "Total sales: 1830.0 across 60 rows."}
            step += 1
        return ModelResponse(
            calls=(ToolCall(f"call-{step}-{len(request.messages)}", name, args),),
            usage=TokenUsage(input_tokens=100, output_tokens=20),
        )

    return respond


async def run_example(apply_policies):
    cleaner = Stage("cleaner", "Prepare the specified data.", Task, Report, tools=[normalize])
    stage = Stage(
        "analysis",
        "Inspect batches, compute an exact total, and save a current revenue finding.",
        Task,
        Report,
        tools=[cleaner.as_tool(name="clean_data"), read_batch, compute_total],
        memory=True,
        required_memory=("revenue",),
        context_policies=ContextPolicies(
            enabled=True,
            protected_fields=("task",),
            artifact_offload=ArtifactOffload(enabled=True, max_chars=1200),
            history=Summarize(
                enabled=True,
                recent_batches=2,
                trigger_fraction=0.65,
                target_fraction=0.45,
                max_input_tokens=5000,
                max_output_tokens=800,
            ),
        ),
    )
    context = RunContext(
        resources={
            "sales": [
                {"amount": f" {i}.0 ", "notes": "Detailed source observation. " * 100}
                for i in range(1, 61)
            ]
        }
    )
    provider = ScriptedProvider(scripted_responder())
    runner = Runner(provider, limits=RunLimits(max_input_tokens=6500, max_model_calls=60))
    result = await runner.run(
        stage,
        {"task": "Inspect all 60 rows in pages, retain them, and report exact total sales."},
        context=context,
        apply_context_policies=apply_policies,
    )
    assert len(result.children) == 1
    assert result.compactions
    assert context.memory.entries["revenue"].value == "1830.0"
    assert context.revisions["sales"] == 1
    assert any(
        message.name == "read_batch" and len(str(message.content)) > 1200
        for message in result.history
    )
    assert any(
        isinstance(message.content, dict) and message.content.get("offloaded")
        for request in provider.requests
        for message in request.messages
    )
    assert result.usage.by_purpose["summarize"].model_calls > 0
    return result


async def main():
    result = await run_example(True)
    print(result.output.text)
    print("Cleaner invocations:", len(result.children))
    print("Compactions:", len(result.compactions))
    print("Summary calls:", result.usage.by_purpose["summarize"].model_calls)
    print("Synthetic inclusive usage:", result.usage.total.model_dump())
    try:
        await run_example(False)
    except ContextBudgetExceeded:
        print("Policies disabled: context budget exceeded, as expected.")
    else:
        raise AssertionError("The uncompressed comparison should exceed the same input budget")


if __name__ == "__main__":
    asyncio.run(main())
