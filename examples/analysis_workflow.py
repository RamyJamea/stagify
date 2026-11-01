"""Explore, delegate preparation, save a finding, and write with native Stagify."""

import asyncio
import os
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from stagify import (
    Completion,
    ContextField,
    ContextPolicies,
    RunContext,
    RunLimits,
    Runner,
    Stage,
    Step,
    ToolContext,
    Workflow,
    tool,
)
from stagify.errors import StageModelLimitExceeded
from stagify.providers.google import GoogleProvider


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str


class DataInput(Task):
    catalog: dict
    revision: int


class AnalysisInput(DataInput):
    exploration: str


class Report(BaseModel):
    text: str


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


@tool(writes={"sales"})
def normalize_amounts(args: Empty, ctx: ToolContext):
    """Normalize amount strings while retaining every row."""
    rows = ctx.resource("sales")
    values = [str(Decimal(row["amount"].strip())) for row in rows]
    for row, value in zip(rows, values, strict=True):
        row["amount"] = value
    return {"normalized_rows": len(rows)}


@tool(reads={"sales"})
def total_sales(args: Empty, ctx: ToolContext):
    """Sum the exported sales amounts exactly."""
    return {
        "total": str(sum((Decimal(row["amount"]) for row in ctx.resource("sales")), Decimal(0)))
    }


def saved_report(ctx: ToolContext) -> Report:
    value = ctx.memory.values(ctx.revisions, ("revenue",), require_current=True)["revenue"]
    return Report(text=f"Total recorded sales: {value}. Export completeness is unknown.")


def build_workflow() -> Workflow:
    fields = {
        "catalog": ContextField(
            lambda ctx: {"rows": len(ctx.resource("sales")), "fields": ["amount"]},
            protected=True,
            depends_on=("sales",),
        ),
        "revision": ContextField(lambda ctx: ctx.revisions["sales"], depends_on=("sales",)),
    }
    cleaner = Stage(
        "clean",
        "Prepare the specified amount strings; preserve rows.",
        DataInput,
        Report,
        tools=(normalize_amounts,),
        resources={"sales"},
        context=fields,
    )
    explore = Stage(
        "explore",
        "Explore the catalog and state the investigation scope.",
        DataInput,
        resources={"sales"},
        context=fields,
    )
    analysis = Stage(
        "analysis",
        "Call clean_data, then total_sales. Save the exact total as revenue with save_memory and its evidence ID. Submit complete_stage with {}.",
        AnalysisInput,
        Report,
        tools=(cleaner.as_tool(name="clean_data", arguments=Task), total_sales),
        resources={"sales"},
        context=fields,
        memory=True,
        max_completion_repairs=0,
        max_model_calls=10,
        completion=Completion(
            arguments=Empty,
            required_memory=("revenue",),
            output=lambda submission, ctx: saved_report(ctx),
            partial_on=(StageModelLimitExceeded,),
            partial_output=lambda ctx: Report(
                text=saved_report(ctx).text + " Analysis coverage is incomplete."
            ),
        ),
    )
    writer = Stage("write", "Write a short Markdown report from the supplied text.", Report)
    return Workflow(
        "sales_report",
        Task,
        (
            Step(explore),
            Step(
                analysis,
                input=lambda state: {
                    "task": state.input.task,
                    "exploration": state.output("explore"),
                },
            ),
            Step(writer, input=lambda state: state.output("analysis")),
        ),
    )


async def main():
    context = RunContext(resources={"sales": [{"amount": " 10.5 "}, {"amount": "13.5"}]})
    provider = GoogleProvider(
        model="gemini-3.8-flash",
        api_key=os.environ["GEMINI_API_KEY"],
        temperature=None,
        top_p=None,
    )
    async with Runner(
        provider,
        limits=RunLimits(max_model_calls=20, timeout_seconds=120),
        context_policies=ContextPolicies(enabled=True),
    ) as runner:
        result = await runner.run(
            build_workflow(),
            {"task": "Report total recorded sales."},
            context=context,
        )
    assert result.status == "completed"
    assert context.memory.values(context.revisions)["revenue"] == "24.0"
    assert result.steps["analysis"].children[0].history[0].content["revision"] == 0
    assert result.steps["analysis"].context["revision"] == context.revisions["sales"]
    assert context.revisions["sales"] >= 1
    print(result.output)
    print("Combined usage:", result.usage.total.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
