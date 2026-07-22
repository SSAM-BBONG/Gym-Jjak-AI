from typing import Any, Callable

from app.llm.models import LLMMessage, LLMResponse


class FakeLLMPort:
    """LLMPort의 가짜 구현체. 실제 Gemini 호출 없이 미리 정해둔 응답을 반환한다.
    여러 도메인의 테스트가 공용으로 재사용한다."""

    def __init__(
        self,
        response: LLMResponse | None = None,
        structured_response: Any = None,
    ) -> None:
        self.response = response or LLMResponse(text="fake response")
        self.received_messages: list[list[LLMMessage]] = []
        self.received_tools: list[list[Callable] | None] = []

        self.structured_response = structured_response
        self.structured_call_count = 0
        self.structured_prompts: list[str] = []
        self.structured_schemas: list[type] = []

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[Callable] | None = None,
    ) -> LLMResponse:
        self.received_messages.append(messages)
        self.received_tools.append(tools)
        return self.response

    async def generate_structured(self, *, prompt: str, output_schema: type) -> Any:
        self.structured_call_count += 1
        self.structured_prompts.append(prompt)
        self.structured_schemas.append(output_schema)
        return self.structured_response
