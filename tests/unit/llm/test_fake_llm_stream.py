"""FakeLLMPort.stream()이 generate()와 같은 response/responses_queue를 공유하며
텍스트가 있으면 델타 1개 + 최종 응답, 텍스트가 없으면(tool_calls만) 최종 응답만
내는지 검증한다. 이 Fake는 이후 그래프 노드/서비스 테스트가 전부 사용한다."""

import pytest

from app.llm.models import LLMResponse, ToolCall
from tests.fakes.llm import FakeLLMPort


async def test_stream_yields_delta_then_final_response_when_text_present() -> None:
    fake = FakeLLMPort(response=LLMResponse(text="안녕하세요"))

    chunks = [c async for c in fake.stream([])]

    assert chunks[0].delta == "안녕하세요"
    assert chunks[1].response.text == "안녕하세요"


async def test_stream_yields_only_final_response_when_text_absent() -> None:
    fake = FakeLLMPort(response=LLMResponse(text="", tool_calls=[
        ToolCall(name="get_pt_usage", args={}, id="call-1")
    ]))

    chunks = [c async for c in fake.stream([])]

    assert len(chunks) == 1
    assert chunks[0].response.tool_calls[0].name == "get_pt_usage"


async def test_stream_consumes_responses_queue_in_order() -> None:
    fake = FakeLLMPort(responses=[LLMResponse(text="첫번째"), LLMResponse(text="두번째")])

    first = [c async for c in fake.stream([])]
    second = [c async for c in fake.stream([])]

    assert first[-1].response.text == "첫번째"
    assert second[-1].response.text == "두번째"


async def test_stream_raises_exception_from_responses_queue() -> None:
    fake = FakeLLMPort(responses=[RuntimeError("boom")])

    with pytest.raises(RuntimeError, match="boom"):
        async for _ in fake.stream([]):
            pass
