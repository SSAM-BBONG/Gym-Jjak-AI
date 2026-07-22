"""GeminiAdapter.stream()의 델타 순서와 최종 응답 조립을 검증한다.
generate()와 동일하게 오류 분류(429/INVALID_ARGUMENT/기타)와 thought_signature
추출도 스트리밍 경로에서 그대로 동작해야 한다."""

import pytest
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from app.llm.errors import LLMInvalidResponseError, LLMNetworkError
from app.llm.gemini_adapter import GeminiAdapter, _THOUGHT_SIGNATURE_KEY
from app.llm.models import LLMMessage


class _FakeChunk:
    def __init__(self, *, content="", tool_calls=None, additional_kwargs=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.additional_kwargs = additional_kwargs or {}


def _adapter_with_astream(chunks: list[_FakeChunk] | None = None, side_effect=None) -> GeminiAdapter:
    adapter = GeminiAdapter()

    async def _fake_astream(_messages):
        if side_effect is not None:
            raise side_effect
        for chunk in chunks or []:
            yield chunk

    fake_model = type("FakeBaseModel", (), {"astream": staticmethod(_fake_astream)})()
    adapter._model = fake_model
    return adapter


async def test_stream_yields_text_deltas_in_order_then_final_response() -> None:
    adapter = _adapter_with_astream([_FakeChunk(content="안녕"), _FakeChunk(content="하세요")])

    chunks = [c async for c in adapter.stream([LLMMessage(role="user", content="안녕")])]

    assert [c.delta for c in chunks if c.delta] == ["안녕", "하세요"]
    assert chunks[-1].response.text == "안녕하세요"
    assert chunks[-1].response.tool_calls == []


async def test_stream_carries_tool_calls_and_thought_signature_in_final_response() -> None:
    adapter = _adapter_with_astream([
        _FakeChunk(
            tool_calls=[{"name": "get_payment_history", "args": {}, "id": "call-1"}],
            additional_kwargs={_THOUGHT_SIGNATURE_KEY: {"call-1": "c2ln"}},
        ),
    ])

    chunks = [c async for c in adapter.stream([LLMMessage(role="user", content="결제 내역")])]

    final = chunks[-1].response
    assert final.text is None
    assert final.tool_calls[0].name == "get_payment_history"
    assert final.tool_calls[0].thought_signature == "c2ln"


async def test_stream_raises_invalid_response_when_no_text_or_tool_calls() -> None:
    adapter = _adapter_with_astream([_FakeChunk(content="")])

    with pytest.raises(LLMInvalidResponseError):
        async for _ in adapter.stream([LLMMessage(role="user", content="hi")]):
            pass


async def test_stream_classifies_invalid_argument_as_invalid_response_not_network() -> None:
    error = ChatGoogleGenerativeAIError(
        "Error calling model (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. missing thought_signature"
    )
    adapter = _adapter_with_astream(side_effect=error)

    with pytest.raises(LLMInvalidResponseError):
        async for _ in adapter.stream([LLMMessage(role="user", content="hi")]):
            pass


async def test_stream_classifies_other_errors_as_network() -> None:
    error = ChatGoogleGenerativeAIError("Error calling model: 503 Service Unavailable")
    adapter = _adapter_with_astream(side_effect=error)

    with pytest.raises(LLMNetworkError):
        async for _ in adapter.stream([LLMMessage(role="user", content="hi")]):
            pass
