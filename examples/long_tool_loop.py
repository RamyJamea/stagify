"""A Gemini analysis loop with a cleaner, exact evidence, and optional context policies."""

import asyncio
import os
from decimal import Decimal

from pydantic import BaseModel, Field

from stagify import (
    ArtifactOffload,
    ContextPolicies,
    RunContext,
    RunLimits,
    Runner,
    Stage,
    Summarize,
    ToolContext,
    tool,
)
from stagify.errors import ContextBudgetExceeded
from stagify.providers.google import GoogleProvider


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


def all_batches_inspected(output, context):
    """Require current evidence covering every row, independently of the model's summary."""
    seen = set()
    offset = 0
    while page := context.artifacts.index(offset=offset, limit=100):
        for item in page:
            evidence = context.artifacts.get(item["id"])
            if (
                evidence.tool_name == "read_batch"
                and evidence.resource_versions == context.revisions
            ):
                start = evidence.arguments["offset"]
                seen.update(range(start, start + len(evidence.data["rows"])))
        offset += len(page)
    return set(range(len(context.resource("sales")))) <= seen


async def run_example(apply_policies):
    cleaner = Stage("cleaner", "Prepare the specified data.", Task, Report, tools=[normalize])
    stage = Stage(
        "analysis",
        "First call clean_data once. Inspect all 60 sales rows in pages of five at offsets 0, 5, 10, ..., 55. Retrieve exact evidence as needed. Then call compute_total, save its evidence as revenue, and submit complete_stage with the exact total. Preserve evidence IDs and progress in summaries.",
        Task,
        Report,
        tools=[cleaner.as_tool(name="clean_data"), read_batch, compute_total],
        memory=True,
        required_memory=("revenue",),
        validate_completion=all_batches_inspected,
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
    async with GoogleProvider(
        model="gemini-3.8-flash",
        api_key=os.environ["GEMINI_API_KEY"],
        temperature=None,
        top_p=None,
    ) as provider:
        runner = Runner(provider, limits=RunLimits(max_input_tokens=6500, max_model_calls=60))
        result = await runner.run(
            stage,
            {"task": "Inspect all 60 rows in pages, retain them, and report exact total sales."},
            context=context,
            apply_context_policies=apply_policies,
        )
    assert result.children
    assert context.memory.entries["revenue"].value == "1830.0"
    assert context.revisions["sales"] >= 1
    return result


async def main():
    result = await run_example(True)
    print(result.output.text)
    print("Cleaner invocations:", len(result.children))
    print("Compactions:", len(result.compactions))
    summary_usage = result.usage.by_purpose.get("summarize")
    print("Summary calls:", summary_usage.model_calls if summary_usage else 0)
    print("Gemini inclusive usage:", result.usage.total.model_dump())
    try:
        await run_example(False)
    except ContextBudgetExceeded:
        print("Policies disabled: context budget exceeded, as expected.")
    else:
        raise AssertionError("The uncompressed comparison should exceed the same input budget")


if __name__ == "__main__":
    asyncio.run(main())
