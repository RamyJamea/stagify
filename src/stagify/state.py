"""Explicit in-memory resources, evidence, and versioned working entries."""

from __future__ import annotations

import asyncio
import hashlib
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .contracts import StageResult, dumps, json_data
from .errors import EvidenceError, StateConflictError, ToolInputError


@dataclass(frozen=True)
class Evidence:
    id: str
    run_id: str
    stage_id: str
    tool_name: str
    arguments: dict[str, Any]
    resource_versions: dict[str, int]
    content_hash: str
    data: Any


class ArtifactStore:
    """Process-local storage; deliberately no durability or global query cache."""

    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}

    def record(
        self,
        *,
        run_id: str,
        stage_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        versions: dict[str, int],
        data: Any,
    ) -> Evidence:
        value = json_data(data)
        evidence = Evidence(
            uuid4().hex,
            run_id,
            stage_id,
            tool_name,
            json_data(arguments),
            dict(versions),
            hashlib.sha256(dumps(value).encode()).hexdigest(),
            value,
        )
        self._items[evidence.id] = evidence
        return deepcopy(evidence)

    def get(self, evidence_id: str) -> Evidence:
        try:
            return deepcopy(self._items[evidence_id])
        except KeyError as exc:
            raise EvidenceError("Unknown evidence ID") from exc

    def read(
        self,
        evidence_id: str,
        pointer: str = "",
        *,
        offset: int = 0,
        limit: int = 25,
        max_chars: int = 8000,
    ) -> dict[str, Any]:
        if offset < 0 or not 1 <= limit <= 100:
            raise EvidenceError("Require offset >= 0 and 1 <= limit <= 100")
        value = self.get(evidence_id).data
        if pointer and not pointer.startswith("/"):
            raise EvidenceError("Evidence pointer must start with /")
        try:
            for token in pointer.split("/")[1:] if pointer else []:
                token = token.replace("~1", "/").replace("~0", "~")
                if isinstance(value, list):
                    if not token.isdigit():
                        raise KeyError(token)
                    value = value[int(token)]
                else:
                    value = value[token]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise EvidenceError("Invalid evidence pointer") from exc
        result: dict[str, Any] = {"evidence_id": evidence_id, "pointer": pointer}
        if isinstance(value, list):
            result.update(
                data=value[offset : offset + limit],
                total=len(value),
                next_offset=offset + limit if offset + limit < len(value) else None,
            )
        else:
            result["data"] = value
        if len(dumps(result)) > max_chars:
            raise EvidenceError("Selected evidence is too large; use a narrower pointer or page")
        return json_data(result)

    def index(self, *, offset: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        if offset < 0 or not 1 <= limit <= 100:
            raise EvidenceError("Invalid evidence index page")
        return [
            {"id": e.id, "tool": e.tool_name, "resource_versions": dict(e.resource_versions)}
            for e in list(self._items.values())[offset : offset + limit]
        ]


@dataclass(frozen=True)
class WorkingEntry:
    key: str
    version: int
    value: Any
    evidence_ids: tuple[str, ...] = ()
    dependencies: dict[str, int] = field(default_factory=dict)
    kind: str = "finding"
    withdrawn: bool = False

    def status(self, versions: dict[str, int]) -> str:
        if self.withdrawn:
            return "retracted"
        return (
            "current"
            if all(versions.get(k) == v for k, v in self.dependencies.items())
            else "stale"
        )


class WorkingState:
    def __init__(self) -> None:
        self.entries: dict[str, WorkingEntry] = {}
        self.events: list[WorkingEntry] = []

    def update(
        self,
        key: str,
        value: Any,
        *,
        evidence_ids: tuple[str, ...] = (),
        dependencies: dict[str, int] | None = None,
        kind: str = "finding",
        expected_version: int | None = None,
        withdraw: bool = False,
    ) -> WorkingEntry:
        old = self.entries.get(key)
        if not key.strip():
            raise ToolInputError("Working-state key cannot be empty")
        if old is not None and expected_version != old.version:
            raise StateConflictError(
                "Supply the current expected_version to replace an entry",
                details={"key": key, "version": old.version},
            )
        if old is None and (expected_version not in (None, 0) or withdraw):
            raise StateConflictError("Working entry does not exist")
        entry = WorkingEntry(
            key,
            1 if old is None else old.version + 1,
            json_data(value),
            tuple(evidence_ids),
            dict(dependencies or {}),
            kind,
            withdraw,
        )
        self.entries[key] = entry
        self.events.append(entry)
        return deepcopy(entry)

    def snapshot(
        self, versions: dict[str, int], keys: tuple[str, ...] | None = None
    ) -> list[dict[str, Any]]:
        return [
            {
                "key": e.key,
                "version": e.version,
                "kind": e.kind,
                "value": json_data(e.value),
                "status": e.status(versions),
                "evidence_ids": list(e.evidence_ids),
            }
            for e in self.entries.values()
            if not e.withdrawn and (keys is None or e.key in keys)
        ]

    def require_current(
        self, versions: dict[str, int], keys: tuple[str, ...] | None = None
    ) -> None:
        required = tuple(self.entries) if keys is None else keys
        for key in required:
            entry = self.entries.get(key)
            if entry is None or entry.status(versions) != "current":
                raise StateConflictError(
                    "A required working entry is missing or stale", details={"key": key}
                )


class RunContext:
    def __init__(
        self, *, resources: dict[str, Any] | None = None, revisions: dict[str, int] | None = None
    ):
        self.resources = dict(resources or {})
        self.revisions = {key: 0 for key in self.resources}
        self.revisions.update(revisions or {})
        self.artifacts = ArtifactStore()
        self.memory = WorkingState()
        self.results: dict[str, StageResult[Any]] = {}
        self.last_result: StageResult[Any] | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._active = False

    def lock(self, resource: str) -> asyncio.Lock:
        return self._locks.setdefault(resource, asyncio.Lock())


class ToolContext:
    def __init__(
        self,
        shared: RunContext,
        *,
        run_id: str,
        stage_id: str,
        allowed_resources: frozenset[str],
        writable_resources: frozenset[str],
    ):
        self._shared = shared
        self.run_id = run_id
        self.stage_id = stage_id
        self.allowed_resources = allowed_resources
        self.writable_resources = writable_resources

    @property
    def artifacts(self) -> ArtifactStore:
        return self._shared.artifacts

    @property
    def memory(self) -> WorkingState:
        return self._shared.memory

    @property
    def revisions(self) -> dict[str, int]:
        return {key: self._shared.revisions[key] for key in self.allowed_resources}

    def resource(self, name: str) -> Any:
        if name not in self.allowed_resources or name not in self._shared.resources:
            raise ToolInputError("Resource access was not declared for this tool")
        return self._shared.resources[name]

    def touch(self, name: str) -> int:
        if name not in self.writable_resources:
            raise ToolInputError("Resource writes were not declared for this tool")
        self._shared.revisions[name] += 1
        return self._shared.revisions[name]

    def save(
        self,
        key: str,
        value: Any,
        *,
        evidence_ids: tuple[str, ...],
        expected_version: int | None = None,
        kind: str = "finding",
    ) -> WorkingEntry:
        if not evidence_ids:
            raise EvidenceError("A supported entry requires evidence IDs")
        versions: dict[str, int] = {}
        for evidence_id in evidence_ids:
            evidence = self.artifacts.get(evidence_id)
            if any(
                self._shared.revisions.get(k) != v for k, v in evidence.resource_versions.items()
            ):
                raise EvidenceError("Supporting evidence is stale")
            if not set(evidence.resource_versions) <= self.allowed_resources:
                raise EvidenceError("Evidence references a resource outside this stage")
            versions.update(evidence.resource_versions)
        return self.memory.update(
            key,
            value,
            evidence_ids=evidence_ids,
            dependencies=versions,
            kind=kind,
            expected_version=expected_version,
        )
