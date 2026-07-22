"""assistant 메시지의 tool_calls가 LangChain AIMessage로 올바르게 재현되는지 검증한다.
(app/llm/models.py에 LLMMessage.tool_calls 필드를 append로 추가하면서 함께 넣은 변환 로직)"""

from app.llm.gemini_adapter import _to_langchain_message
from app.llm.models import LLMMessage, ToolCall


def test_assistant_message_with_tool_calls_becomes_ai_message_with_tool_calls() -> None:
    message = LLMMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="get_pt_usage", args={}, id="call-1")],
    )

    result = _to_langchain_message(message)

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "get_pt_usage"
    assert result.tool_calls[0]["args"] == {}
    assert result.tool_calls[0]["id"] == "call-1"


def test_assistant_message_without_tool_calls_is_unaffected() -> None:
    message = LLMMessage(role="assistant", content="일반 답변입니다")

    result = _to_langchain_message(message)

    assert result.content == "일반 답변입니다"
    assert result.tool_calls == []
