from abc import ABC, abstractmethod
from .schemas import CompleteToolCall, GenConfig, ToolSpec, ToolResult, TurnResponse


class ProviderError(RuntimeError):
    """A provider failure that stops the run unless a subtype permits recovery."""

    def __init__(self, message: str, *, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class ProviderTransientError(ProviderError):
    """Temporary failure before local tools execute; retry within the turn budget."""

    def __init__(
        self, status_code: int | None = None, retry_after: float | None = None
    ):
        self.retry_after = retry_after
        super().__init__(
            (
                f"Temporary provider failure (HTTP {status_code})"
                if status_code is not None
                else "Temporary provider transport failure"
            ),
            status_code=status_code,
        )


class ProviderOutputError(ProviderError):
    """Malformed or missing required model output; stop the stage."""


class BaseNLP(ABC):
    @abstractmethod
    async def gen_turn(
        self,
        config: GenConfig,
        content: str | list[dict],
        tools: list[ToolSpec] | None = None,
    ) -> TurnResponse: ...

    @abstractmethod
    async def connect(
        self, api_key: str | None, base_url: str | None = None
    ) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def create_model_msg(self, message: str) -> dict: ...

    @abstractmethod
    def create_user_msg(self, message: str) -> dict: ...

    @abstractmethod
    def create_tool_call(self, call: CompleteToolCall, arguments: dict) -> dict: ...

    @abstractmethod
    def create_tool_result(self, result: ToolResult) -> list[dict]: ...

    @abstractmethod
    def create_tools(self, tools: list[ToolSpec]) -> list[dict]: ...
