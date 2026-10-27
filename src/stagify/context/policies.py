"""Explicit, independently enabled policies. No context reduction by default."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArtifactOffload:
    enabled: bool = False
    max_chars: int = 4000

    def __post_init__(self) -> None:
        if self.max_chars < 256:
            raise ValueError("max_chars must be at least 256")


@dataclass(frozen=True)
class Summarize:
    enabled: bool = False
    recent_batches: int = 3
    trigger_fraction: float = 0.8
    target_fraction: float = 0.6
    max_input_tokens: int = 6000
    max_output_tokens: int = 1000

    def __post_init__(self) -> None:
        if self.recent_batches < 0:
            raise ValueError("recent_batches cannot be negative")
        if not 0 < self.target_fraction < self.trigger_fraction <= 1:
            raise ValueError("Require 0 < target_fraction < trigger_fraction <= 1")
        if min(self.max_input_tokens, self.max_output_tokens) < 1:
            raise ValueError("Summary token limits must be positive")


@dataclass(frozen=True)
class ContextPolicies:
    enabled: bool = False
    protected_fields: tuple[str, ...] = ()
    artifact_offload: ArtifactOffload = field(default_factory=ArtifactOffload)
    history: Summarize = field(default_factory=Summarize)
    memory_keys: tuple[str, ...] | None = None
