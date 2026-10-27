"""Analysis invokes a cleaner stage as a tool, then saves a supported finding."""

import asyncio
from decimal import Decimal

from pydantic import BaseModel

from stagify import (
    ContextPolicies,
    ModelResponse,
    RunContext,
    Runner,
    Stage,
    TokenUsage,
    ToolCall,
    ToolContext,
    tool,
)
from stagify.testing import ScriptedProvider


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


def respond(request):
    tools = [message for message in request.messages if message.role == "tool"]
    if request.instructions.startswith("Prepare"):
        name, args = (
            ("normalize_amounts", {})
            if not tools
            else ("complete_stage", {"text": "Amounts normalized; all rows retained."})
        )
    elif not tools:
        name, args = "clean_data", {"task": "Normalize sales amount strings."}
    elif tools[-1].name == "clean_data":
        name, args = "total_sales", {}
    elif tools[-1].name == "total_sales":
        evidence = tools[-1].content
        name, args = (
            "save_memory",
            {
                "key": "revenue",
                "value": evidence["data"]["total"],
                "evidence_ids": [evidence["evidence_id"]],
            },
        )
    else:
        name, args = "complete_stage", {"text": "Total sales are 24.0 across both rows."}
    return ModelResponse(
        calls=(ToolCall("call-" + str(len(request.messages)), name, args),),
        usage=TokenUsage(input_tokens=100, output_tokens=20),
    )


async def main():
    cleaner = Stage(
        "cleaner", "Prepare the specified data only.", Task, Report, tools=[normalize_amounts]
    )
    analysis = Stage(
        "analysis",
        "Analyze sales using exact evidence.",
        Task,
        Report,
        tools=[cleaner.as_tool(name="clean_data"), total_sales],
        memory=True,
        required_memory=("revenue",),
        context_policies=ContextPolicies(enabled=True, protected_fields=("task",)),
    )
    context = RunContext(resources={"sales": [{"amount": " 10.5 "}, {"amount": "13.5"}]})
    result = await Runner(ScriptedProvider(respond), verbose=False).run(
        analysis, {"task": "Calculate total sales, preserving both rows."}, context=context
    )
    assert result.status == "completed"
    assert context.memory.entries["revenue"].value == "24.0"
    assert context.revisions["sales"] == 1
    assert len(result.children) == 1
    assert result.usage.total.model_calls == 6
    print(result.output.text)
    print("Synthetic example usage:", result.usage.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
