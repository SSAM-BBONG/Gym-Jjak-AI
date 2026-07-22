"""llm_call_count >= 6, tool_call_count >= 5 초과 시 오류 종료, 중복 도구 호출 차단."""

from app.llm.models import LLMResponse, ToolCall

from .conftest import chat_state


async def test_llm_call_limit_exceeded_ends_with_error_code(graph, builder) -> None:
    # agent_node가 매번 새 도구 호출을 요청하도록 만들어 llm_call_limit(6)에 걸리게 한다.
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_pt_usage", args={"n": i}, id=f"call-{i}")])
        for i in range(10)
    ]

    result = await graph.ainvoke(chat_state(message="결제 내역 알려줘"), config=builder.config())

    assert result["error_code"] == "LLM_CALL_LIMIT_EXCEEDED"
    assert result["llm_call_count"] <= 6
    assert not result.get("answer")


async def test_duplicate_tool_call_is_reported_as_tool_error_not_crash(graph, builder) -> None:
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_pt_usage", args={}, id="call-1")]),
        LLMResponse(text="", tool_calls=[ToolCall(name="get_pt_usage", args={}, id="call-2")]),
        LLMResponse(text="확인했습니다."),
    ]

    result = await graph.ainvoke(chat_state(message="결제 내역 알려줘"), config=builder.config())

    # 두 번째 get_pt_usage({}) 호출은 중복이라 오류 데이터로 tool 메시지에 담기고,
    # 그래프는 죽지 않고 세 번째 LLM 호출까지 정상적으로 이어진다.
    assert result["answer"] == "확인했습니다."
    tool_messages = [m for m in result["llm_messages"] if m.role == "tool"]
    assert any("DUPLICATE_TOOL_CALL" in m.content for m in tool_messages)


async def test_tool_call_limit_is_reported_as_tool_error_not_crash(graph, builder) -> None:
    # call_limit=1로 좁혀서 두 번째 도구 호출이 한도 초과가 되도록 만든다.
    tool_names = ["get_pt_usage", "get_subscription_status", "get_onboarding"]
    builder.llm.responses_queue = [
        LLMResponse(
            text="",
            tool_calls=[ToolCall(name=name, args={}, id=f"call-{i}") for i, name in enumerate(tool_names)],
        ),
        LLMResponse(text="확인했습니다."),
    ]

    config = builder.config(call_limit=1)
    result = await graph.ainvoke(chat_state(message="결제 내역 알려줘"), config=config)

    tool_messages = [m for m in result["llm_messages"] if m.role == "tool"]
    assert any("TOOL_CALL_LIMIT_EXCEEDED" in m.content for m in tool_messages)
    assert result["answer"] == "확인했습니다."
