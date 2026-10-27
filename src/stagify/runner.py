"""Staged ReAct execution, child stages, bounded context, and shared accounting."""

from __future__ import annotations

import asyncio
import inspect
import math
import random
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .context import ContextPolicies
from .context.compiler import ContextCompiler, estimate_tokens
from .contracts import (
    ErrorInfo,
    Message,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    RunLimits,
    StageResult,
    ToolSpec,
    json_data,
)
from .errors import (
    ConfigurationError,
    ContextBudgetExceeded,
    ContextValidationError,
    EvidenceError,
    ProviderOutputError,
    ProviderTransientError,
    RunLimitExceeded,
    StageCompletionError,
    StageExecutionError,
    StageModelLimitExceeded,
    StageTimeoutError,
    StagifyError,
    StateConflictError,
    SubstageError,
    ToolExecutionError,
    ToolInputError,
)
from .providers.base import Provider
from .stages import Stage, StageTool
from .state import RunContext, ToolContext
from .tools import Tool
from .usage import UsageLedger


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Read(_Args):
    evidence_id: str
    pointer: str = ""
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=25, ge=1, le=100)


class _List(_Args):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class _Save(_Args):
    key: str = Field(min_length=1)
    value: Any
    evidence_ids: list[str] = Field(min_length=1)
    expected_version: int | None = None
    kind: str = "finding"


class _Withdraw(_Args):
    key: str
    expected_version: int


@dataclass
class _Run:
    id: str
    context: RunContext
    ledger: UsageLedger
    policies_override: bool | None
    verbose_override: bool | None
    deadline: float | None


class Runner:
    def __init__(
        self,
        provider: Provider,
        *,
        limits: RunLimits | None = None,
        context_policies: ContextPolicies | None = None,
        verbose: bool = False,
        logger: Any = None,
        min_interval_seconds: float = 0,
    ):
        if not math.isfinite(min_interval_seconds) or min_interval_seconds < 0:
            raise ConfigurationError("min_interval_seconds must be finite and nonnegative")
        self.min_interval_seconds = min_interval_seconds
        self.provider = provider
        self.limits = limits or RunLimits()
        self.context_policies = context_policies or ContextPolicies()
        self.verbose = verbose
        self.logger = logger if logger is not None else structlog.get_logger("stagify")

    async def run(
        self,
        stage: Stage[Any, Any],
        stage_input: BaseModel | dict[str, Any],
        *,
        context: RunContext | None = None,
        apply_context_policies: bool | None = None,
        verbose: bool | None = None,
    ) -> StageResult[Any]:
        shared = context if context is not None else RunContext()
        if shared._active:
            raise ConfigurationError("A RunContext cannot be used by concurrent root runs")
        shared._active = True
        start = time.monotonic()
        run = _Run(
            uuid4().hex,
            shared,
            UsageLedger(self.limits.max_model_calls, self.limits.max_tool_calls),
            apply_context_policies,
            verbose,
            asyncio.get_running_loop().time() + self.limits.timeout_seconds
            if self.limits.timeout_seconds is not None
            else None,
        )
        try:
            result = await self._stage(run, stage, stage_input, (), (), None, None)
            self.logger.info(
                "run.completed",
                run_id=run.id,
                status=result.status,
                duration_ms=round((time.monotonic() - start) * 1000, 2),
                usage=result.usage.total.model_dump(),
            )
            return result
        except BaseException as exc:
            self.logger.error(
                "run.failed",
                run_id=run.id,
                error_code=getattr(
                    exc,
                    "code",
                    "cancelled" if isinstance(exc, asyncio.CancelledError) else "internal_error",
                ),
            )
            raise
        finally:
            shared._active = False

    async def _stage(
        self,
        run: _Run,
        stage: Stage[Any, Any],
        value: Any,
        ancestors: tuple[str, ...],
        stage_path: tuple[int, ...],
        parent_resources: frozenset[str] | None,
        inherited_verbose: bool | None,
    ) -> StageResult[Any]:
        provider = stage.provider if stage.provider is not None else self.provider
        invocation = uuid4().hex
        parent = ancestors[-1] if ancestors else None
        history: list[Message] = []
        compiler: ContextCompiler | None = None
        verbosity = (
            run.verbose_override
            if run.verbose_override is not None
            else (
                stage.verbose
                if stage.verbose is not None
                else self.verbose
                if inherited_verbose is None
                else inherited_verbose
            )
        )
        logger = self.logger.bind(
            run_id=run.id,
            stage_name=stage.name,
            stage_invocation_id=invocation,
            parent_invocation_id=parent,
        )
        start = time.monotonic()

        def event(name: str, **fields: Any) -> None:
            if verbosity:
                logger.debug(name, **fields)

        def finish(
            status: str, output: Any = None, error: StagifyError | None = None
        ) -> StageResult[Any]:
            result = StageResult(
                status=status,
                output=output,
                run_id=run.id,
                stage_name=stage.name,
                invocation_id=invocation,
                parent_invocation_id=parent,
                usage=run.ledger.for_stage(invocation),
                history=list(history),
                error=ErrorInfo(code=error.code, message=str(error), details=error.details)
                if error
                else None,
                children=[
                    r for r in run.context.results.values() if r.parent_invocation_id == invocation
                ],
                resource_versions=dict(run.context.revisions),
                evidence_ids=[
                    e.id for e in run.context.artifacts._items.values() if e.stage_id == invocation
                ],
                compactions=list(compiler.receipts) if compiler is not None else [],
            )
            run.context.results[invocation] = result
            if parent is None:
                run.context.last_result = result
            logger.info(
                "stage.completed" if status == "completed" else "stage.failed",
                status=status,
                error_code=error.code if error else None,
                duration_ms=round((time.monotonic() - start) * 1000, 2),
                usage=result.usage.total.model_dump(),
            )
            return result

        resources = frozenset()
        stage_context: ToolContext | None = None
        try:
            if len(ancestors) >= self.limits.max_depth or id(stage) in stage_path:
                raise ConfigurationError("Substage depth exceeded or recursive stage cycle")
            try:
                parsed = stage.input_model.model_validate(value)
                payload = parsed.model_dump(
                    mode="json",
                    include=set(stage.context_fields) if stage.context_fields is not None else None,
                )
            except (ValidationError, ValueError, TypeError) as exc:
                raise ContextValidationError(
                    "Stage input does not satisfy its input_model"
                ) from exc
            requested = frozenset().union(*(t.reads | t.writes for t in stage.tools))
            resources = stage.resources if stage.resources is not None else requested
            resources = frozenset(resources)
            if not requested <= resources or not resources <= run.context.resources.keys():
                raise ConfigurationError("Stage tools require undeclared or missing resources")
            if parent_resources is not None and not resources <= parent_resources:
                raise ConfigurationError("Child stage requests resources outside its parent grant")
            stage_context = ToolContext(
                run.context,
                run_id=run.id,
                stage_id=invocation,
                allowed_resources=resources,
                writable_resources=frozenset(),
            )
            policies = stage.context_policies or self.context_policies
            enabled = policies.enabled if run.policies_override is None else run.policies_override
            if not set(policies.protected_fields) <= set(payload):
                raise ConfigurationError(
                    "Protected fields must be present in the rendered stage input"
                )
            tool_map: dict[str, Tool | StageTool] = {t.name: t for t in stage.tools}
            if stage.memory:
                tool_map.update(self._memory_tools(stage_context, policies, resources))
            specs = tuple(t.spec for t in tool_map.values())
            if stage.output_model is not None:
                specs += (
                    ToolSpec(
                        "complete_stage",
                        "Submit the validated stage output alone.",
                        stage.output_model.model_json_schema(),
                    ),
                )
            instructions = stage.instructions
            if stage.output_model is not None:
                instructions += (
                    "\nSubmit the final result with complete_stage, alone in its response."
                )
            history.append(Message("user", payload))
            capabilities = getattr(provider, "capabilities", ProviderCapabilities())
            output_limit = min(
                self.limits.max_output_tokens,
                stage.max_output_tokens or self.limits.max_output_tokens,
                capabilities.max_output_tokens or self.limits.max_output_tokens,
            )
            budget = min(
                self.limits.max_input_tokens,
                capabilities.max_input_tokens or self.limits.max_input_tokens,
                (capabilities.context_window - output_limit)
                if capabilities.context_window is not None
                else self.limits.max_input_tokens,
            )
            if budget < 1:
                raise ConfigurationError("No input space remains after reserving output capacity")

            async def invoke(request: ModelRequest, purpose: str = "agent") -> ModelResponse:
                if estimate_tokens(request) > budget:
                    raise ContextBudgetExceeded("Rendered provider request exceeds its allocation")
                for retry in range(self.limits.max_model_retries + 1):
                    remaining = self.limits.max_model_calls - len(run.ledger.requests)
                    if stage.max_model_calls is not None:
                        remaining = min(
                            remaining,
                            stage.max_model_calls
                            - sum(item.stage_id == invocation for item in run.ledger.requests),
                        )
                    current_request = request
                    if purpose == "agent":
                        available = request.tools
                        if remaining == 1 and any(t.name == "complete_stage" for t in available):
                            available = tuple(t for t in available if t.name == "complete_stage")
                        current_request = replace(
                            request,
                            tools=available,
                            instructions=(
                                request.instructions + "\n\n"
                                f"Remaining provider requests: {remaining}, including final submission."
                            ),
                        )
                    if estimate_tokens(current_request) > budget:
                        raise ContextBudgetExceeded(
                            "Rendered provider request exceeds its allocation"
                        )
                    record = run.ledger.start_request(
                        invocation, ancestors, purpose, provider.name, stage.max_model_calls
                    )
                    event(
                        "provider.request",
                        purpose=purpose,
                        request_id=record.request_id,
                        attempt=retry + 1,
                    )
                    try:
                        if self.min_interval_seconds:
                            await asyncio.sleep(self.min_interval_seconds)
                        response = await provider.generate(current_request)
                    except ProviderTransientError as exc:
                        if retry == self.limits.max_model_retries or remaining <= 1:
                            raise
                        delay = (
                            exc.retry_after
                            if exc.retry_after is not None
                            else (self.limits.retry_delay * 2**retry * random.uniform(0.8, 1.2))
                        )
                        if (
                            not isinstance(delay, (float, int))
                            or not math.isfinite(delay)
                            or delay < 0
                        ):
                            raise ConfigurationError("Provider retry delay is invalid")
                        logger.warning(
                            "provider.retry_scheduled", attempt=retry + 1, delay_seconds=delay
                        )
                        await asyncio.sleep(delay)
                        continue
                    if not isinstance(response, ModelResponse):
                        raise ProviderOutputError("Provider must return ModelResponse")
                    record.usage = response.usage
                    if any(
                        call.name not in {tool.name for tool in current_request.tools}
                        for call in response.calls
                    ):
                        raise ProviderOutputError(
                            "Provider selected a tool unavailable for this request"
                        )
                    if response.status not in ("completed", "requires_action"):
                        raise ProviderOutputError(
                            "Provider returned an incomplete or failed response"
                        )
                    event("provider.response", purpose=purpose, usage=response.usage.model_dump())
                    return response
                raise AssertionError("Unreachable retry state")

            compiler = ContextCompiler(
                policies=policies,
                enabled=enabled,
                shared=run.context,
                resources=resources,
                memory=stage.memory,
                budget=budget,
                invoke=invoke,
                event=event,
                projections={
                    t.name: t.projection
                    for t in stage.tools
                    if isinstance(t, Tool) and t.projection is not None
                },
            )
            deadline = run.deadline
            if stage.timeout_seconds is not None:
                local_deadline = asyncio.get_running_loop().time() + stage.timeout_seconds
                deadline = local_deadline if deadline is None else min(deadline, local_deadline)
            event("stage.started", policies_enabled=enabled)
            repairs = 0
            seen_call_ids: set[str] = set()
            async with asyncio.timeout_at(deadline):
                while True:
                    request = await compiler.compile(
                        ModelRequest(instructions, (), specs, output_limit), history
                    )
                    response = await invoke(request)
                    calls = response.calls
                    if response.status == "requires_action" and not calls:
                        raise ProviderOutputError("Provider requested action without tool calls")
                    if len({c.call_id for c in calls}) != len(calls):
                        raise ProviderOutputError("Duplicate tool-call IDs")
                    for call in calls:
                        if not call.call_id or call.call_id in seen_call_ids:
                            raise ProviderOutputError("Empty or reused tool-call ID")
                        if call.name not in tool_map and not (
                            call.name == "complete_stage" and stage.output_model is not None
                        ):
                            raise ProviderOutputError("Provider selected an unknown tool")
                        if not isinstance(call.arguments, dict):
                            raise ProviderOutputError("Tool arguments must be a JSON object")
                    if any(c.name == "complete_stage" for c in calls) and len(calls) != 1:
                        raise ProviderOutputError("complete_stage must be submitted alone")
                    seen_call_ids.update(c.call_id for c in calls)
                    history.append(
                        Message("assistant", response.text, tuple(calls), native=response.native)
                    )
                    if not calls:
                        if stage.output_model is None and response.text.strip():
                            await self._validate_completion(
                                stage, response.text.strip(), stage_context
                            )
                            return finish("completed", response.text.strip())
                        if stage.output_model is not None and stage.max_model_calls is not None:
                            own_calls = sum(r.stage_id == invocation for r in run.ledger.requests)
                            if own_calls >= stage.max_model_calls:
                                raise StageModelLimitExceeded("Stage model-call limit reached")
                        raise ProviderOutputError("Stage ended without a valid completion")
                    for call in calls:
                        run.ledger.start_tool(invocation, ancestors)
                        if call.name == "complete_stage":
                            try:
                                output = stage.output_model.model_validate(call.arguments)
                                await self._validate_completion(stage, output, stage_context)
                            except (
                                ValidationError,
                                StageCompletionError,
                                StateConflictError,
                            ) as exc:
                                error = StageCompletionError(
                                    "Completion did not satisfy the output/state contract"
                                )
                                history.append(
                                    Message(
                                        "tool",
                                        {"ok": False, "code": error.code, "message": str(error)},
                                        call_id=call.call_id,
                                        name=call.name,
                                    )
                                )
                                if repairs >= stage.max_completion_repairs:
                                    raise error from exc
                                repairs += 1
                                continue
                            history.append(
                                Message(
                                    "tool",
                                    {"ok": True, "data": output.model_dump(mode="json")},
                                    call_id=call.call_id,
                                    name=call.name,
                                )
                            )
                            return finish("completed", output)
                        item = tool_map[call.name]
                        try:
                            parsed_args = (
                                item.arguments.model_validate(call.arguments)
                                if isinstance(item, StageTool)
                                else item.parse(call.arguments)
                            )
                        except (ValidationError, ToolInputError):
                            history.append(
                                Message(
                                    "tool",
                                    {
                                        "ok": False,
                                        "code": "invalid_tool_input",
                                        "message": "Arguments do not satisfy this tool's schema",
                                    },
                                    call_id=call.call_id,
                                    name=call.name,
                                )
                            )
                            logger.warning(
                                "tool.failed", tool_name=call.name, error_code="invalid_tool_input"
                            )
                            continue
                        event("tool.started", tool_name=call.name, tool_call_id=call.call_id)
                        if isinstance(item, StageTool):
                            child_input = parsed_args
                            if item.input_mapper is not None:
                                child_input = await self._maybe_await(
                                    item.input_mapper(parsed_args, stage_context)
                                )
                            try:
                                child = await self._stage(
                                    run,
                                    item.stage,
                                    child_input,
                                    ancestors + (invocation,),
                                    stage_path + (id(stage),),
                                    resources,
                                    verbosity,
                                )
                            except StagifyError as exc:
                                child = exc.result
                                if item.on_error == "raise":
                                    raise SubstageError(
                                        "Child stage failed",
                                        details={
                                            "child_invocation_id": child.invocation_id
                                            if child
                                            else None,
                                            "resource_versions": dict(run.context.revisions),
                                            "child_error_code": exc.code,
                                        },
                                    ) from exc
                                result = {
                                    "ok": False,
                                    "code": "substage_error",
                                    "message": "Child stage failed",
                                    "resource_versions": dict(run.context.revisions),
                                }
                            else:
                                result = {
                                    "ok": child.status == "completed",
                                    "status": child.status,
                                    "data": json_data(child.output),
                                    "invocation_id": child.invocation_id,
                                    "resource_versions": child.resource_versions,
                                    "evidence_ids": child.evidence_ids,
                                }
                        else:
                            result = await self._execute_tool(
                                run, item, parsed_args, invocation, resources, event, logger
                            )
                        history.append(
                            Message("tool", result, call_id=call.call_id, name=call.name)
                        )
                        event("tool.completed", tool_name=call.name, tool_call_id=call.call_id)
        except TimeoutError as exc:
            error = StageTimeoutError("Stage deadline exceeded")
            result = finish("partial" if stage.allow_partial else "failed", error=error)
            error.result = result
            if stage.allow_partial:
                return result
            raise error from exc
        except asyncio.CancelledError:
            finish("cancelled")
            raise
        except StagifyError as exc:
            if isinstance(exc, RunLimitExceeded) and stage.allow_partial:
                output = None
                if stage.partial_output is not None and stage_context is not None:
                    try:
                        output = await self._maybe_await(stage.partial_output(stage_context))
                        if stage.output_model is not None:
                            output = stage.output_model.model_validate(output)
                    except asyncio.CancelledError:
                        finish("cancelled")
                        raise
                    except Exception as partial_error:
                        failure = StageCompletionError(
                            "Partial output did not satisfy its contract"
                        )
                        failure.result = finish("failed", error=failure)
                        raise failure from partial_error
                return finish("partial", output, exc)
            exc.result = finish("failed", error=exc)
            raise
        except Exception as exc:
            error = StageExecutionError(
                "Unexpected stage failure", details={"exception_type": type(exc).__name__}
            )
            error.result = finish("failed", error=error)
            raise error from exc

    async def _execute_tool(
        self,
        run: _Run,
        tool: Tool,
        args: BaseModel,
        invocation: str,
        resources: frozenset[str],
        event: Any,
        logger: Any,
    ) -> dict[str, Any]:
        declared = tool.reads | tool.writes
        if not declared <= resources:
            raise ConfigurationError("Tool resource grant exceeds stage grant")
        context = ToolContext(
            run.context,
            run_id=run.id,
            stage_id=invocation,
            allowed_resources=declared,
            writable_resources=tool.writes,
        )
        async with AsyncExitStack() as stack:
            for name in sorted(declared):
                await stack.enter_async_context(run.context.lock(name))
            before = dict(run.context.revisions)
            try:
                data = await tool.invoke(args, context)
                data = json_data(data)
            except BaseException as exc:
                for name in tool.writes:
                    if run.context.revisions[name] == before[name]:
                        run.context.revisions[name] += 1
                if isinstance(exc, asyncio.CancelledError):
                    raise
                if isinstance(exc, (ToolInputError, StateConflictError)):
                    logger.warning("tool.failed", tool_name=tool.name, error_code=exc.code)
                    return {
                        "ok": False,
                        "code": exc.code,
                        "message": str(exc),
                        "resource_versions": {k: run.context.revisions[k] for k in declared},
                    }
                raise ToolExecutionError(
                    "Tool execution failed; external effects may require reconciliation",
                    details={
                        "tool": tool.name,
                        "writes": sorted(tool.writes),
                        "resource_versions": {k: run.context.revisions[k] for k in declared},
                    },
                ) from exc
            for name in tool.writes:
                if run.context.revisions[name] == before[name]:
                    run.context.revisions[name] += 1
            result = {"ok": True, "data": data}
            if tool.record_evidence:
                evidence = run.context.artifacts.record(
                    run_id=run.id,
                    stage_id=invocation,
                    tool_name=tool.name,
                    arguments=args.model_dump(mode="json"),
                    versions={k: run.context.revisions[k] for k in declared},
                    data=data,
                )
                result.update(evidence_id=evidence.id, resource_versions=evidence.resource_versions)
            return result

    def _memory_tools(
        self, context: ToolContext, policies: ContextPolicies, resources: frozenset[str]
    ) -> dict[str, Tool]:
        def read(args: _Read, ctx: ToolContext) -> Any:
            evidence = ctx.artifacts.get(args.evidence_id)
            if not set(evidence.resource_versions) <= resources:
                raise EvidenceError("Evidence is outside this stage's resource grant")
            return ctx.artifacts.read(
                args.evidence_id,
                args.pointer,
                offset=args.offset,
                limit=args.limit,
                max_chars=policies.artifact_offload.max_chars,
            )

        def index(args: _List, ctx: ToolContext) -> Any:
            allowed = [
                e for e in ctx.artifacts._items.values() if set(e.resource_versions) <= resources
            ]
            return {
                "items": [
                    {"id": e.id, "tool": e.tool_name, "resource_versions": e.resource_versions}
                    for e in allowed[args.offset : args.offset + args.limit]
                ],
                "total": len(allowed),
            }

        def save(args: _Save, ctx: ToolContext) -> Any:
            entry = ctx.save(
                args.key,
                args.value,
                evidence_ids=tuple(args.evidence_ids),
                expected_version=args.expected_version,
                kind=args.kind,
            )
            return {"key": entry.key, "version": entry.version, "status": "current"}

        def withdraw(args: _Withdraw, ctx: ToolContext) -> Any:
            entry = ctx.memory.update(
                args.key, None, expected_version=args.expected_version, withdraw=True
            )
            return {"key": entry.key, "version": entry.version, "status": "retracted"}

        return {
            name: Tool(name, model, fn, description, reads=resources, record_evidence=False)
            for name, model, fn, description in [
                (
                    "read_evidence",
                    _Read,
                    read,
                    "Read exact stored evidence using JSON Pointer and list pagination.",
                ),
                (
                    "list_evidence",
                    _List,
                    index,
                    "List a bounded page of available evidence metadata.",
                ),
                (
                    "save_memory",
                    _Save,
                    save,
                    "Save a supported working entry. Supply expected_version when replacing.",
                ),
                (
                    "withdraw_memory",
                    _Withdraw,
                    withdraw,
                    "Withdraw an existing working entry using its current version.",
                ),
            ]
        }

    async def _validate_completion(
        self, stage: Stage[Any, Any], output: Any, context: ToolContext
    ) -> None:
        if stage.required_memory:
            context.memory.require_current(context._shared.revisions, stage.required_memory)
        if stage.validate_completion is not None:
            valid = await self._maybe_await(stage.validate_completion(output, context))
            if valid is False:
                raise StageCompletionError("Application completion validator rejected the result")

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value
