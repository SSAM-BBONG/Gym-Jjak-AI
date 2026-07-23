"""GeminiAdapter.generate()의 오류 분류와 thought_signature 왕복을 검증한다.
실제로 겪은 버그: 429가 아닌 ChatGoogleGenerativeAIError(예: 400 INVALID_ARGUMENT)가
전부 LLM_NETWORK_ERROR로 뭉개져서, Function Calling 멀티턴에 필요한
thought_signature 누락이라는 진짜 원인이 "일시적 네트워크 오류"로 오인됐다."""

from unittest.mock import AsyncMock

import pytest
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from app.llm.errors import LLMInvalidResponseError, LLMNetworkError
from app.llm.gemini_adapter import GeminiAdapter, _THOUGHT_SIGNATURE_KEY, _to_langchain_message
from app.llm.models import LLMMessage, ToolCall


class _FakeResponse:
    def __init__(self, *, content="", tool_calls=None, additional_kwargs=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.additional_kwargs = additional_kwargs or {}


def _adapter_with_base_model(ainvoke_result=None, ainvoke_side_effect=None) -> GeminiAdapter:
    adapter = GeminiAdapter()
    fake_model = type(
        "FakeBaseModel",
        (),
        {"ainvoke": AsyncMock(return_value=ainvoke_result, side_effect=ainvoke_side_effect)},
    )()
    adapter._model = fake_model
    return adapter


async def test_generate_extracts_thought_signature_into_tool_call() -> None:
    response = _FakeResponse(
        tool_calls=[{"name": "get_payment_history", "args": {}, "id": "call-1"}],
        additional_kwargs={_THOUGHT_SIGNATURE_KEY: {"call-1": "c2lnbmF0dXJl"}},
    )
    adapter = _adapter_with_base_model(ainvoke_result=response)

    result = await adapter.generate([LLMMessage(role="user", content="결제 내역 알려줘")])

    assert result.tool_calls[0].thought_signature == "c2lnbmF0dXJl"


async def test_generate_leaves_thought_signature_none_when_absent() -> None:
    response = _FakeResponse(
        tool_calls=[{"name": "get_payment_history", "args": {}, "id": "call-1"}],
    )
    adapter = _adapter_with_base_model(ainvoke_result=response)

    result = await adapter.generate([LLMMessage(role="user", content="결제 내역 알려줘")])

    assert result.tool_calls[0].thought_signature is None


async def test_generate_classifies_invalid_argument_as_invalid_response_not_network() -> None:
    error = ChatGoogleGenerativeAIError(
        "Error calling model 'gemini-flash-latest' (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. "
        "Function call is missing a thought_signature"
    )
    adapter = _adapter_with_base_model(ainvoke_side_effect=error)

    with pytest.raises(LLMInvalidResponseError):
        await adapter.generate([LLMMessage(role="user", content="결제 내역 알려줘")])


async def test_generate_still_classifies_other_errors_as_network() -> None:
    error = ChatGoogleGenerativeAIError("Error calling model: 503 Service Unavailable")
    adapter = _adapter_with_base_model(ainvoke_side_effect=error)

    with pytest.raises(LLMNetworkError):
        await adapter.generate([LLMMessage(role="user", content="결제 내역 알려줘")])


def test_to_langchain_message_echoes_thought_signature_via_additional_kwargs() -> None:
    message = LLMMessage(
        role="assistant",
        content="",
        tool_calls=[
            ToolCall(name="get_payment_history", args={}, id="call-1", thought_signature="sig-1")
        ],
    )

    result = _to_langchain_message(message)

    assert result.additional_kwargs[_THOUGHT_SIGNATURE_KEY] == {"call-1": "sig-1"}


def test_to_langchain_message_omits_signature_map_when_no_signatures() -> None:
    message = LLMMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="get_payment_history", args={}, id="call-1")],
    )

    result = _to_langchain_message(message)

    assert _THOUGHT_SIGNATURE_KEY not in result.additional_kwargs
