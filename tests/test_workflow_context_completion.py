import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ConfigDict, Field, field_validator

from stagify import (
    Completion,
    ContextField,
    ContextPolicies,
    ModelResponse,
    RunContext,
    RunLimits,
    Runner,
    Stage,
    Step,
    Summarize,
    TokenUsage,
    ToolCall,
    Workflow,
    tool,
)
from stagify.errors import (
    ConfigurationError,
    ContextValidationError,
    ProviderAuthenticationError,
    ProviderOutputError,
    ProviderTransientError,
    RunLimitExceeded,
    StageCompletionError,
    StageExecutionError,
    StageModelLimitExceeded,
    StageTimeoutError,
    SubstageError,
)
from stagify.testing import ScriptedProvider


class Task(BaseModel):
    task: str


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Output(BaseModel):
    text: str


class Expanded(Task):
    catalog: list[int]
    revision: int


USAGE = TokenUsage(input_tokens=10, output_tokens=2)


def call(name, arguments=None, identity="call"):
    return ModelResponse(calls=(ToolCall(identity, name, arguments or {}),), usage=USAGE)


def text(value="done"):
    return ModelResponse(text=value, usage=USAGE)


def basic_workflow():
    first = Stage("explore", "Explore.", Task)
    second = Stage("write", "Write.", Task)
    return Workflow(
        "report",
        Task,
        (
            Step(first),
            Step(second, input=lambda state: {"task": state.output("explore")}),
        ),
    )


def test_workflow_binds_outputs_and_aggregates_one_ledger():
    provider = ScriptedProvider([text("observations"), text("report")])
    result = asyncio.run(Runner(provider).run(basic_workflow(), {"task": "analyze"}))
    assert result.status == "completed"
    assert result.output == "report"
    assert result.usage.total.input_tokens == 20
    assert result.usage.total.model_calls == 2
    assert result.usage.own.model_calls == 0
    assert provider.requests[1].messages[0].content == {"task": "observations"}
    assert all(stage.run_id == result.run_id for stage in result.steps.values())


def test_shared_global_budget_does_not_reset_between_steps():
    provider = ScriptedProvider([text("first"), text("must not execute")])
    context = RunContext()
    with pytest.raises(RunLimitExceeded) as caught:
        asyncio.run(
            Runner(provider, limits=RunLimits(max_model_calls=1)).run(
                basic_workflow(),
                {"task": "analyze"},
                context=context,
            )
        )
    assert len(provider.requests) == 1
    result = caught.value.workflow_result
    assert result is context.last_workflow_result
    assert list(result.steps) == ["explore", "write"]
    assert result.steps["write"].status == "failed"
    assert result.usage.total.model_calls == 1


def test_stage_limit_counts_workflow_steps_and_children():
    child = Stage("clean", "Clean.", Task, Empty)
    parent = Stage("analysis", "Analyze.", Task, Empty, tools=(child.as_tool(),))
    workflow = Workflow("report", Task, (Step(parent),))
    provider = ScriptedProvider([call("clean", {"task": "clean"})])
    with pytest.raises(SubstageError) as caught:
        asyncio.run(
            Runner(provider, limits=RunLimits(max_stage_invocations=1)).run(
                workflow,
                {"task": "analyze"},
            )
        )
    assert isinstance(caught.value.__cause__, RunLimitExceeded)
    assert caught.value.workflow_result.usage.total.model_calls == 1


def test_workflow_children_are_counted_once_and_do_not_consume_depth():
    child = Stage("clean", "Clean.", Task, Empty)
    parent = Stage("analysis", "Analyze.", Task, Empty, tools=(child.as_tool(),))
    writer = Stage("write", "Write.", Task)
    provider = ScriptedProvider(
        [
            call("clean", {"task": "clean"}, "child"),
            call("complete_stage", identity="cleaned"),
            call("complete_stage", identity="analyzed"),
            text("report"),
        ]
    )
    workflow = Workflow("report", Task, (Step(parent), Step(writer)))
    result = asyncio.run(
        Runner(provider, limits=RunLimits(max_depth=2)).run(
            workflow,
            {"task": "report"},
        )
    )
    assert result.usage.total.model_calls == 4
    assert result.usage.total.input_tokens == 40
    assert result.steps["analysis"].usage.total.model_calls == 3
    assert result.steps["analysis"].children[0].usage.total.model_calls == 1


def test_workflow_preserves_provider_error_type_and_stops():
    error = ProviderAuthenticationError("rejected")
    provider = ScriptedProvider([text("first"), error])
    with pytest.raises(ProviderAuthenticationError) as caught:
        asyncio.run(Runner(provider).run(basic_workflow(), {"task": "report"}))
    assert caught.value is error
    assert caught.value.result.stage_name == "write"
    assert caught.value.workflow_result.steps["explore"].output == "first"
    assert caught.value.workflow_result.usage.total.complete is False


def test_invalid_binding_has_a_safe_workflow_snapshot():
    workflow = replace(basic_workflow(), output=lambda state: 1 / 0)
    with pytest.raises(StageExecutionError) as caught:
        asyncio.run(Runner(ScriptedProvider([text(), text()])).run(workflow, {"task": "x"}))
    assert isinstance(caught.value.__cause__, ZeroDivisionError)
    assert caught.value.workflow_result.usage.total.model_calls == 2


def test_invalid_workflow_input_is_rejected_without_a_provider_call():
    provider = ScriptedProvider([])
    with pytest.raises(ContextValidationError) as caught:
        asyncio.run(Runner(provider).run(basic_workflow(), {}))
    assert not provider.requests
    assert caught.value.workflow_result.steps == {}


def test_workflow_deadline_includes_async_bindings():
    async def blocked(state):
        await asyncio.sleep(1)
        return {"task": "late"}

    workflow = Workflow("report", Task, (Step(Stage("write", "Write.", Task), input=blocked),))
    provider = ScriptedProvider([])
    with pytest.raises(StageTimeoutError) as caught:
        asyncio.run(
            Runner(provider, limits=RunLimits(timeout_seconds=0.01)).run(
                workflow,
                {"task": "x"},
            )
        )
    assert caught.value.workflow_result.status == "failed"
    assert not provider.requests


def test_workflow_cancellation_keeps_completed_and_active_steps():
    async def run():
        entered = asyncio.Event()

        async def blocked(request):
            if request.instructions.startswith("Explore"):
                return text("first")
            entered.set()
            await asyncio.Event().wait()

        provider = ScriptedProvider(blocked)
        context = RunContext()
        task = asyncio.create_task(
            Runner(provider).run(
                basic_workflow(),
                {"task": "x"},
                context=context,
            )
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert context.last_workflow_result.status == "cancelled"
        assert context.last_workflow_result.steps["write"].status == "cancelled"
        assert not context._active

    asyncio.run(run())


@tool(reads={"data"}, writes={"data"})
def mutate(args: Empty, ctx):
    ctx.resource("data").append(2)
    return {"changed": True}


def expanded_stage(**options):
    return Stage("analysis", "Analyze.", Expanded, tools=(mutate,), resources={"data"}, **options)


def test_injected_fields_override_supplied_values_and_refresh_after_mutation():
    fields = {
        "catalog": ContextField(
            lambda ctx: ctx.resource("data"), depends_on=("data",), protected=True
        ),
        "revision": ContextField(lambda ctx: ctx.revisions["data"], depends_on=("data",)),
    }
    provider = ScriptedProvider([call("mutate"), text()])
    context = RunContext(resources={"data": [1]})
    result = asyncio.run(
        Runner(provider).run(
            expanded_stage(context=fields),
            {"task": "x", "catalog": [999], "revision": 999},
            context=context,
        )
    )
    assert provider.requests[0].messages[0].content == {"task": "x", "catalog": [1], "revision": 0}
    assert provider.requests[1].messages[0].content == {
        "task": "x",
        "catalog": [1, 2],
        "revision": 1,
    }
    assert result.history[0].content["revision"] == 0
    assert result.context["revision"] == 1


def test_preserved_fields_are_only_loaded_once():
    source = AsyncMock(side_effect=lambda ctx: list(ctx.resource("data")))
    provider = ScriptedProvider([call("mutate"), text()])
    stage = expanded_stage(
        context={
            "catalog": ContextField(source, update="preserve"),
            "revision": ContextField(lambda ctx: ctx.revisions["data"]),
        }
    )
    asyncio.run(
        Runner(provider).run(stage, {"task": "x"}, context=RunContext(resources={"data": [1]}))
    )
    source.assert_awaited_once()
    assert provider.requests[-1].messages[0].content["catalog"] == [1]


def test_append_loads_only_deltas_when_the_dependency_changes():
    calls = []

    def delta(ctx):
        calls.append(ctx.revisions["data"])
        return [ctx.resource("data")[-1]]

    provider = ScriptedProvider(
        [
            call("mutate", identity="one"),
            call("mutate", identity="two"),
            text(),
        ]
    )
    stage = expanded_stage(
        context={
            "catalog": ContextField(delta, update="append", depends_on=("data",)),
            "revision": ContextField(lambda ctx: ctx.revisions["data"]),
        }
    )
    asyncio.run(
        Runner(provider).run(stage, {"task": "x"}, context=RunContext(resources={"data": [1]}))
    )
    assert calls == [0, 1, 2]
    assert provider.requests[-1].messages[0].content["catalog"] == [1, 2, 2]


def test_child_tool_schema_contains_only_model_arguments():
    child = Stage(
        "clean",
        "Clean.",
        Expanded,
        Empty,
        resources={"data"},
        context={
            "catalog": ContextField(lambda ctx: ctx.resource("data")),
            "revision": ContextField(lambda ctx: ctx.revisions["data"]),
        },
    )
    cleaner = child.as_tool(name="clean_data", arguments=Task)
    assert set(cleaner.spec.parameters["properties"]) == {"task"}
    parent = Stage("analysis", "Analyze.", Task, Empty, tools=(cleaner,), resources={"data"})
    provider = ScriptedProvider(
        [
            call("clean_data", {"task": "clean"}, "child"),
            call("complete_stage", identity="cleaned"),
            call("complete_stage", identity="done"),
        ]
    )
    result = asyncio.run(
        Runner(provider).run(
            parent,
            {"task": "analyze"},
            context=RunContext(resources={"data": [1]}),
        )
    )
    assert provider.requests[1].messages[0].content["catalog"] == [1]
    assert result.children[0].context["task"] == "clean"


def test_injection_never_expands_child_resource_permissions():
    child = Stage(
        "clean",
        "Clean.",
        Expanded,
        Empty,
        context={
            "catalog": ContextField(lambda ctx: ctx.resource("secret")),
            "revision": ContextField(lambda ctx: 0),
        },
    )
    parent = Stage("analysis", "Analyze.", Task, Empty, tools=(child.as_tool(arguments=Task),))
    provider = ScriptedProvider([call("clean", {"task": "clean"})])
    with pytest.raises(SubstageError):
        asyncio.run(
            Runner(provider).run(
                parent,
                {"task": "x"},
                context=RunContext(resources={"secret": [777]}),
            )
        )
    assert len(provider.requests) == 1


def test_invalid_refreshed_input_fails_before_the_next_provider_request():
    context = RunContext(resources={"data": [1]})
    stage = expanded_stage(
        context={
            "catalog": ContextField(
                lambda ctx: ctx.resource("data") if not ctx.revisions["data"] else "invalid"
            ),
            "revision": ContextField(lambda ctx: ctx.revisions["data"]),
        }
    )
    provider = ScriptedProvider([call("mutate"), text()])
    with pytest.raises(ContextValidationError) as caught:
        asyncio.run(Runner(provider).run(stage, {"task": "x"}, context=context))
    assert len(provider.requests) == 1
    assert caught.value.result.context["catalog"] == [1]


def completion_stage(**options):
    return Stage(
        "analysis", "Analyze.", Task, Output, max_model_calls=1, max_completion_repairs=0, **options
    )


def test_completion_uses_an_empty_submission_and_state_derived_typed_output():
    stage = completion_stage(
        completion=Completion(arguments=Empty, output=lambda submission, ctx: {"text": "saved"})
    )
    provider = ScriptedProvider([call("complete_stage")])
    result = asyncio.run(Runner(provider).run(stage, {"task": "x"}))
    spec = next(spec for spec in provider.requests[0].tools if spec.name == "complete_stage")
    assert spec.parameters["properties"] == {}
    assert result.output == Output(text="saved")


def test_invalid_submission_cannot_replace_the_state_derived_output():
    stage = completion_stage(
        completion=Completion(arguments=Empty, output=lambda submission, ctx: {"text": "saved"})
    )
    provider = ScriptedProvider([call("complete_stage", {"text": "invented"})])
    with pytest.raises(StageCompletionError):
        asyncio.run(Runner(provider).run(stage, {"task": "x"}))


def test_explicit_local_exhaustion_can_continue_to_the_writer_as_partial():
    stage = completion_stage(
        completion=Completion(
            partial_on=(StageModelLimitExceeded,),
            partial_output=lambda ctx: {"text": "supported partial findings"},
        )
    )
    writer = Stage("write", "Write.", Task)
    workflow = Workflow(
        "report",
        Task,
        (
            Step(stage),
            Step(writer, input=lambda state: {"task": state.output("analysis").text}),
        ),
    )
    provider = ScriptedProvider([text("unsubmitted"), text("report")])
    result = asyncio.run(Runner(provider).run(workflow, {"task": "x"}))
    assert result.status == "partial"
    assert result.output == "report"
    assert result.steps["analysis"].error.code == "stage_model_limit_exceeded"


@pytest.mark.parametrize(
    "error",
    [
        ProviderTransientError(retry_after=0),
        ProviderAuthenticationError("bad key"),
        ProviderOutputError("bad output"),
    ],
)
def test_provider_errors_never_trigger_partial_completion(error):
    stage = completion_stage(
        completion=Completion(
            partial_on=(StageModelLimitExceeded,),
            partial_output=lambda ctx: {"text": "partial"},
        )
    )
    with pytest.raises(type(error)):
        asyncio.run(Runner(ScriptedProvider([error])).run(stage, {"task": "x"}))


def test_partial_output_must_pass_the_declared_output_and_state_contract():
    stage = completion_stage(
        completion=Completion(
            required_memory=("finding",),
            partial_on=(StageModelLimitExceeded,),
            partial_output=lambda ctx: {"text": "unsupported"},
        )
    )
    with pytest.raises(StageCompletionError) as caught:
        asyncio.run(Runner(ScriptedProvider([text("unsubmitted")])).run(stage, {"task": "x"}))
    assert caught.value.result.status == "failed"


def test_stale_memory_is_excluded_or_rejected_explicitly():
    context = RunContext(resources={"data": [1]})
    context.memory.update("old", "stale", dependencies={"data": 0})
    context.revisions["data"] = 1
    context.memory.update("current", "supported", dependencies={"data": 1})
    assert context.memory.values(context.revisions) == {"current": "supported"}
    stage = completion_stage(
        completion=Completion(
            arguments=Empty,
            required_memory=("old",),
            output=lambda submission, ctx: {"text": "must fail"},
        )
    )
    stage = replace(stage, resources={"data"})
    with pytest.raises(StageCompletionError):
        asyncio.run(
            Runner(ScriptedProvider([call("complete_stage")])).run(
                stage, {"task": "x"}, context=context
            )
        )


def test_managed_runner_closes_unique_providers_after_failure_without_masking_it():
    async def run():
        provider = ScriptedProvider([ProviderAuthenticationError("bad key")])
        provider.aclose = AsyncMock(side_effect=RuntimeError("cleanup"))
        with pytest.raises(ProviderAuthenticationError):
            async with Runner(provider) as runner:
                await runner.run(basic_workflow(), {"task": "x"})
        await runner.aclose()
        provider.aclose.assert_awaited_once()

    asyncio.run(run())


def test_managed_runner_closes_child_provider_and_preserves_usage():
    async def run():
        parent = ScriptedProvider(
            [
                call("clean", {"task": "clean"}),
                call("complete_stage", identity="parent"),
            ]
        )
        child_provider = ScriptedProvider([call("complete_stage", identity="child")])
        parent.aclose, child_provider.aclose = AsyncMock(), AsyncMock()
        child = Stage("clean", "Clean.", Task, Empty, provider=child_provider)
        stage = Stage("analysis", "Analyze.", Task, Empty, tools=(child.as_tool(),))
        async with Runner(parent) as runner:
            result = await runner.run(stage, {"task": "x"})
        parent.aclose.assert_awaited_once()
        child_provider.aclose.assert_awaited_once()
        assert result.usage.total.model_calls == 3

    asyncio.run(run())


def test_workflow_compression_requests_share_the_global_ledger():
    @tool
    def large(args: Empty, ctx):
        return {"rows": list(range(1000))}

    turns = 0

    def respond(request):
        nonlocal turns
        if request.instructions.startswith("Summarize"):
            return text("Historical rows are available in evidence.")
        turns += 1
        return call("large", identity=str(turns)) if turns < 4 else text("done")

    stage = Stage(
        "analysis",
        "Analyze.",
        Task,
        tools=(large,),
        context_policies=ContextPolicies(
            enabled=True,
            history=Summarize(enabled=True, recent_batches=0, max_input_tokens=5000),
        ),
    )
    provider = ScriptedProvider(respond)
    workflow = Workflow("report", Task, (Step(stage),))
    result = asyncio.run(
        Runner(provider, limits=RunLimits(max_input_tokens=5000)).run(
            workflow,
            {"task": "retain"},
        )
    )
    assert result.usage.by_purpose["summarize"].model_calls > 0
    assert result.usage.total.model_calls == len(provider.requests)
    assert all(
        request.messages[0].content["task"] == "retain"
        for request in provider.requests
        if not request.instructions.startswith("Summarize")
    )


@pytest.mark.parametrize(
    "build",
    [
        lambda: Workflow("empty", Task, ()),
        lambda: Workflow(
            "duplicates", Task, (Step(Stage("x", "x", Task)), Step(Stage("x", "x", Task)))
        ),
        lambda: ContextField(lambda ctx: [], update="append"),
        lambda: Completion(partial_on=(ProviderTransientError,), partial_output=lambda ctx: {}),
        lambda: completion_stage(completion=Completion(), allow_partial=True),
        lambda: expanded_stage(context={"missing": ContextField(lambda ctx: None)}),
    ],
)
def test_invalid_configuration_fails_early(build):
    with pytest.raises(ConfigurationError):
        build()


def test_ordinary_aliased_input_remains_valid_when_passed_as_a_model():
    class Aliased(BaseModel):
        task: str = Field(alias="question")

    value = Aliased(question="report")
    result = asyncio.run(
        Runner(ScriptedProvider([text()])).run(
            Stage("analysis", "Analyze.", Aliased),
            value,
        )
    )
    assert result.context == {"task": "report"}


def test_aliases_cannot_override_an_injected_field():
    class Aliased(Task):
        catalog: list[int] = Field(alias="caller_catalog")

    with pytest.raises(ConfigurationError):
        Stage(
            "analysis",
            "Analyze.",
            Aliased,
            context={
                "catalog": ContextField(lambda ctx: [1]),
            },
        )


def test_no_change_in_resource_revision_does_not_append_again():
    @tool
    def inspect_data(args: Empty, ctx):
        return "unchanged"

    calls = []
    stage = Stage(
        "analysis",
        "Analyze.",
        Expanded,
        tools=(inspect_data,),
        resources={"data"},
        context={
            "catalog": ContextField(
                lambda ctx: calls.append("loaded") or [1],
                update="append",
                depends_on=("data",),
            ),
            "revision": ContextField(lambda ctx: ctx.revisions["data"]),
        },
    )
    provider = ScriptedProvider([call("inspect_data"), text()])
    result = asyncio.run(
        Runner(provider).run(
            stage,
            {"task": "x"},
            context=RunContext(resources={"data": []}),
        )
    )
    assert calls == ["loaded"]
    assert result.context["catalog"] == [1]


def test_child_exhaustion_cannot_trigger_the_parents_partial_policy():
    child = Stage("clean", "Clean.", Task, Empty, max_model_calls=1)
    parent = Stage(
        "analysis",
        "Analyze.",
        Task,
        Output,
        tools=(child.as_tool(),),
        completion=Completion(
            partial_on=(StageModelLimitExceeded,),
            partial_output=lambda ctx: {"text": "partial"},
        ),
    )
    provider = ScriptedProvider([call("clean", {"task": "clean"}), text("unsubmitted")])
    with pytest.raises(SubstageError):
        asyncio.run(Runner(provider).run(parent, {"task": "x"}))


@pytest.mark.parametrize("local", [False, True])
def test_async_context_loading_obeys_the_stage_and_run_deadline(local):
    async def blocked(ctx):
        await asyncio.sleep(1)
        return []

    stage = expanded_stage(
        timeout_seconds=0.01 if local else None,
        context={
            "catalog": ContextField(blocked),
            "revision": ContextField(lambda ctx: 0),
        },
    )
    provider = ScriptedProvider([])
    limits = RunLimits(timeout_seconds=None if local else 0.01)
    with pytest.raises(StageTimeoutError) as caught:
        asyncio.run(
            Runner(provider, limits=limits).run(
                stage,
                {"task": "x"},
                context=RunContext(resources={"data": []}),
            )
        )
    assert caught.value.result.status == "failed"
    assert not provider.requests


def test_field_refresh_does_not_reapply_input_transformations_to_validated_values():
    class AnnotatedInput(Expanded):
        @field_validator("task")
        @classmethod
        def annotate(cls, value):
            return "Investigate: " + value

    stage = Stage(
        "analysis",
        "Analyze.",
        AnnotatedInput,
        tools=(mutate,),
        resources={"data"},
        context={
            "catalog": ContextField(lambda ctx: ctx.resource("data")),
            "revision": ContextField(lambda ctx: ctx.revisions["data"]),
        },
    )
    provider = ScriptedProvider([call("mutate"), text()])
    result = asyncio.run(
        Runner(provider).run(
            stage,
            {"task": "sales"},
            context=RunContext(resources={"data": [1]}),
        )
    )
    assert result.context["task"] == "Investigate: sales"
    assert all(
        request.messages[0].content["task"] == "Investigate: sales" for request in provider.requests
    )


def test_validated_model_input_does_not_apply_field_transformations_again():
    class AnnotatedTask(Task):
        @field_validator("task")
        @classmethod
        def annotate(cls, value):
            return "Investigate: " + value

    value = AnnotatedTask(task="sales")
    result = asyncio.run(
        Runner(ScriptedProvider([text()])).run(
            Stage("analysis", "Analyze.", AnnotatedTask),
            value,
        )
    )
    assert result.context["task"] == "Investigate: sales"
