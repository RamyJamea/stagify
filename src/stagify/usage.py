"""One accounting ledger for returned usage, child totals, and enforced budgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import RunLimitExceeded, StageModelLimitExceeded

Purpose = Literal["agent", "summarize", "extract", "repair"]


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    tool_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def populate_total(self) -> TokenUsage:
        if (
            self.total_tokens is None
            and self.input_tokens is not None
            and self.output_tokens is not None
        ):
            object.__setattr__(self, "total_tokens", self.input_tokens + self.output_tokens)
        return self


class UsageTotals(TokenUsage):
    model_calls: int = 0
    tool_calls: int = 0
    complete: bool = True


class StageUsage(BaseModel):
    own: UsageTotals = Field(default_factory=UsageTotals)
    children: UsageTotals = Field(default_factory=UsageTotals)
    total: UsageTotals = Field(default_factory=UsageTotals)
    by_purpose: dict[str, UsageTotals] = Field(default_factory=dict)


@dataclass
class UsageRecord:
    stage_id: str
    ancestors: tuple[str, ...]
    purpose: Purpose
    provider: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    request_id: str = field(default_factory=lambda: uuid4().hex)


class UsageLedger:
    def __init__(self, max_model_calls: int, max_tool_calls: int):
        self.max_model_calls = max_model_calls
        self.max_tool_calls = max_tool_calls
        self.requests: list[UsageRecord] = []
        self.tools: list[tuple[str, tuple[str, ...]]] = []

    def start_request(
        self,
        stage_id: str,
        ancestors: tuple[str, ...],
        purpose: Purpose,
        provider: str,
        local_limit: int | None,
    ) -> UsageRecord:
        if len(self.requests) >= self.max_model_calls:
            raise RunLimitExceeded("Run model-call limit reached")
        local = sum(r.stage_id == stage_id for r in self.requests)
        if local_limit is not None and local >= local_limit:
            raise StageModelLimitExceeded("Stage model-call limit reached")
        record = UsageRecord(stage_id, ancestors, purpose, provider)
        self.requests.append(record)
        return record

    def start_tool(self, stage_id: str, ancestors: tuple[str, ...]) -> None:
        if len(self.tools) >= self.max_tool_calls:
            raise RunLimitExceeded("Run tool-call limit reached")
        self.tools.append((stage_id, ancestors))

    @staticmethod
    def _sum(records: list[UsageRecord], tool_calls: int) -> UsageTotals:
        values: dict[str, int | None] = {}
        for name in TokenUsage.model_fields:
            fields = [getattr(record.usage, name) for record in records]
            values[name] = sum(fields) if all(v is not None for v in fields) else None
        return UsageTotals(
            **values,
            model_calls=len(records),
            tool_calls=tool_calls,
            complete=all(
                r.usage.input_tokens is not None and r.usage.output_tokens is not None
                for r in records
            ),
        )

    def for_stage(self, stage_id: str) -> StageUsage:
        own = [r for r in self.requests if r.stage_id == stage_id]
        children = [r for r in self.requests if stage_id in r.ancestors]
        own_tools = sum(s == stage_id for s, _ in self.tools)
        child_tools = sum(stage_id in ancestors for _, ancestors in self.tools)
        combined = own + children
        return StageUsage(
            own=self._sum(own, own_tools),
            children=self._sum(children, child_tools),
            total=self._sum(combined, own_tools + child_tools),
            by_purpose={
                p: self._sum([r for r in combined if r.purpose == p], 0)
                for p in dict.fromkeys(r.purpose for r in combined)
            },
        )
