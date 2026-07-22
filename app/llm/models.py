from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    """LLM이 요청한 도구 호출 1건.

    thought_signature는 Gemini 2.5+/3 계열이 Function Calling 멀티턴에서 추론 연속성을
    검증하기 위해 요구하는 서명이다(base64). 다음 턴에 이 도구 호출을 다시 이력에 넣어
    보낼 때 그대로 echo해야 하며, 없으면 Gemini가 400 INVALID_ARGUMENT로 거부한다."""

    name: str
    args: dict[str, Any]
    id: str
    thought_signature: str | None = None


class LLMMessage(BaseModel):
    """대화 메시지 하나. content는 단순 텍스트 또는 멀티모달 파트 리스트
    (예: [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {...}}])를 담을 수 있다.
    role="tool"일 때는 tool_call_id로 어떤 ToolCall에 대한 결과인지 표시한다.
    role="assistant"이고 이전 턴에서 도구 호출을 요청했다면 tool_calls에 그 요청을 담아
    다음 LLM 호출 시 대화 이력에 그대로 재현한다(Function Calling 멀티턴 왕복용)."""

    role: Role
    content: str | list[dict[str, Any]]
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMStreamChunk(BaseModel):
    """LLM 스트리밍 응답 조각. delta가 있으면 텍스트 토큰 조각이고, response가 있으면
    스트림의 마지막 청크로 전체 텍스트+tool_calls가 담긴 최종 응답이다.
    한 청크에 delta와 response가 동시에 채워지는 일은 없다."""

    delta: str | None = None
    response: LLMResponse | None = None
