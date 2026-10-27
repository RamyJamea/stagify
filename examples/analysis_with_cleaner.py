"""Analysis invokes a cleaner stage as a tool, then saves a supported finding."""

import asyncio
import os
from decimal import Decimal

from pydantic import BaseModel

from stagify import (
    ContextPolicies,
    RunContext,
    RunLimits,
    Runner,
    Stage,
    ToolContext,
    tool,
)
from stagify.providers.google import GoogleProvider


class Task(BaseModel):
    task: str


class Report(BaseModel):
    text: str


class Empty(BaseModel):
    pass


@tool(writes={"sales"})
def normalize_amounts(args: Empty, ctx: ToolContext):
    """Normalize the declared amount strings, preserving rows."""
    rows = ctx.resource("sales")
    parsed = [str(Decimal(row["amount"].strip())) for row in rows]
    for row, value in zip(rows, parsed, strict=True):
        row["amount"] = value
    return {"normalized_rows": len(rows)}


@tool(reads={"sales"})
def total_sales(args: Empty, ctx: ToolContext):
    """Calculate the exact sum of the sales amount strings."""
    return {
        "total": str(sum((Decimal(row["amount"]) for row in ctx.resource("sales")), Decimal(0)))
    }


async def main():
    cleaner = Stage(
        "cleaner", "Prepare the specified data only.", Task, Report, tools=[normalize_amounts]
    )
    analysis = Stage(
        "analysis",
        "First call clean_data once. Then call total_sales, save its evidence as the revenue finding, and submit complete_stage using the exact total.",
        Task,
        Report,
        tools=[cleaner.as_tool(name="clean_data"), total_sales],
        memory=True,
        required_memory=("revenue",),
        context_policies=ContextPolicies(enabled=True, protected_fields=("task",)),
    )
    context = RunContext(resources={"sales": [{"amount": " 10.5 "}, {"amount": "13.5"}]})
    async with GoogleProvider(
        model="gemini-3.8-flash",
        api_key=os.environ["GEMINI_API_KEY"],
        temperature=None,
        top_p=None,
    ) as provider:
        result = await Runner(
            provider, limits=RunLimits(max_model_calls=20, timeout_seconds=120), verbose=False
        ).run(analysis, {"task": "Calculate total sales, preserving both rows."}, context=context)
    assert result.status == "completed"
    assert context.memory.entries["revenue"].value == "24.0"
    assert context.revisions["sales"] >= 1
    assert result.children
    print(result.output.text)
    print("Gemini usage:", result.usage.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
