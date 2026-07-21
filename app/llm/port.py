from typing import Any, Callable, Protocol, TypeVar

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any]
    id: str


class LLMResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class LLMPort(Protocol):
    async def generate(
        self,
        messages: list[tuple[str, str]],
        tools: list[Callable] | None = None,
    ) -> LLMResponse: ...

    async def generate_structured_image(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
        output_schema: type[StructuredOutput],
    ) -> StructuredOutput: ...
