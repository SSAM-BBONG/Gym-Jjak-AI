from typing import Any, AsyncIterator, Callable

from app.llm.models import LLMMessage, LLMResponse, LLMStreamChunk


class FakeLLMPort:
    """LLMPort의 가짜 구현체. 실제 Gemini 호출 없이 미리 정해둔 응답을 반환한다.
    여러 도메인의 테스트가 공용으로 재사용한다."""

    def __init__(
        self,
        response: LLMResponse | None = None,
        structured_response: Any = None,
        responses: list[LLMResponse | Exception] | None = None,
    ) -> None:
        """response는 generate()가 매번 반환할 고정값, structured_response는
        generate_structured()가 반환할 값. responses를 주면 generate() 호출마다
        순서대로 하나씩 꺼내 쓴다(Exception이면 그대로 raise) — Function Calling처럼
        같은 인스턴스가 여러 번 다른 응답을 내야 하는 멀티턴 테스트에 사용한다.
        큐가 바닥나면 이후 호출은 response로 되돌아간다."""
        self.response = response or LLMResponse(text="fake response")
        self.responses_queue = list(responses) if responses is not None else None
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
        """호출 인자를 기록하고, responses 큐가 있으면 순서대로, 없으면 고정 response를 반환한다."""
        self.received_messages.append(messages)
        self.received_tools.append(tools)
        if self.responses_queue:
            next_item = self.responses_queue.pop(0)
            if isinstance(next_item, Exception):
                raise next_item
            return next_item
        return self.response

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[Callable] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """generate()와 동일한 response/responses_queue를 재사용한다. 텍스트가 있으면
        델타 1개로 흘려보낸 뒤 최종 응답을 담은 청크를 낸다."""
        self.received_messages.append(messages)
        self.received_tools.append(tools)
        if self.responses_queue:
            next_item = self.responses_queue.pop(0)
            if isinstance(next_item, Exception):
                raise next_item
            response = next_item
        else:
            response = self.response
        if response.text:
            yield LLMStreamChunk(delta=response.text)
        yield LLMStreamChunk(response=response)

    async def generate_structured(self, *, prompt: str, output_schema: type) -> Any:
        """호출 인자를 기록하고 미리 설정된 structured_response를 그대로 반환한다."""
        self.structured_call_count += 1
        self.structured_prompts.append(prompt)
        self.structured_schemas.append(output_schema)
        return self.structured_response
