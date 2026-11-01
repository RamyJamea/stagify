"""Staged tool workflows with explicit, optional context management."""

from .completion import Completion
from .context import ArtifactOffload, ContextPolicies, Summarize
from .context.fields import ContextField
from .contracts import (
    Message,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    RunLimits,
    StageResult,
    ToolCall,
    ToolSpec,
)
from .errors import StagifyError
from .providers import Provider
from .runner import Runner
from .stages import Stage, StageTool
from .state import ArtifactStore, RunContext, ToolContext, WorkingState
from .tools import Tool, tool
from .usage import StageUsage, TokenUsage, UsageTotals
from .workflow import Step, Workflow, WorkflowContext, WorkflowResult

__all__ = [
    "ArtifactOffload",
    "ArtifactStore",
    "Completion",
    "ContextField",
    "ContextPolicies",
    "Message",
    "ModelRequest",
    "ModelResponse",
    "Provider",
    "ProviderCapabilities",
    "RunContext",
    "RunLimits",
    "Runner",
    "Stage",
    "StageResult",
    "StageTool",
    "StageUsage",
    "Step",
    "StagifyError",
    "Summarize",
    "TokenUsage",
    "Tool",
    "ToolCall",
    "ToolContext",
    "ToolSpec",
    "UsageTotals",
    "WorkingState",
    "Workflow",
    "WorkflowContext",
    "WorkflowResult",
    "tool",
]
