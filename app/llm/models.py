from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class LLMMessage(BaseModel):
    """대화 메시지 하나. content는 단순 텍스트 또는 멀티모달 파트 리스트
    (예: [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {...}}])를 담을 수 있다.
    role="tool"일 때는 tool_call_id로 어떤 ToolCall에 대한 결과인지 표시한다."""

    role: Role
    content: str | list[dict[str, Any]]
    tool_call_id: str | None = None


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any]
    id: str


class LLMResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
