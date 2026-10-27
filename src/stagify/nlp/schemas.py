from pydantic import BaseModel, ConfigDict, Field, field_serializer
from typing import Literal, Any, NotRequired, TypedDict


class GenConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    model_name: str = Field(min_length=1)
    temperature: float | None = Field(default=0.0, ge=0, le=2)
    top_p: float | None = Field(default=1.0, gt=0, le=1)
    thinking_level: Literal["high", "medium", "low", "minimal"] | None = "low"
    max_output_tokens: int | None = Field(default=None, gt=0)
    instructions: str | None = None
    struct: type[BaseModel] | None = None
    max_struct_chars: int = Field(default=65536, ge=1)

    @field_serializer("struct")
    def serialize_struct(self, struct: type[BaseModel] | None) -> dict | None:
        return struct.model_json_schema() if struct is not None else None


class GenResponse(BaseModel):
    model_name: str
    request_id: str | None = None
    text: str | None = None
    struct: Any | None = None
    input_tokens: int | None = None
    reason_tokens: int | None = None
    output_tokens: int | None = None
    cache_tokens: int | None = None
    tool_tokens: int | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class ToolResult(BaseModel):
    call_id: str
    name: str
    result: Any


class CompleteToolCall(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, Any]


class TurnResponse(GenResponse):
    status: str
    calls: list[CompleteToolCall] = Field(default_factory=list)
    replay_content: list[dict[str, Any]] = Field(default_factory=list)


class GenerationError(TypedDict):
    turn: int
    type: str
    status_code: NotRequired[int | None]


class AgentResult(BaseModel):
    result: dict[str, Any]
    turns: int
    tool_calls: int
    transcript: list[dict[str, Any]]
    usage: dict[str, int] = Field(default_factory=dict)
    generation_errors: list[GenerationError] = Field(default_factory=list)
