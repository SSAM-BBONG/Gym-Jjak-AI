from typing import Any, Callable, Protocol

from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any]
    id: str


class LLMResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = []


class LLMPort(Protocol):
    async def generate(
        self,
        messages: list[tuple[str, str]],
        tools: list[Callable] | None = None,
    ) -> LLMResponse: ...
