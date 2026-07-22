from app.common.conversation import ChatMessage, build_memory


def make_messages(count: int) -> list[ChatMessage]:
    return [
        ChatMessage(session_id="session-1", user_id=10, role="user", content=f"msg-{i}")
        for i in range(count)
    ]


def test_memory_uses_summary_and_recent_messages_only() -> None:
    memory = build_memory(summary="기존 요약", messages=make_messages(30))

    assert memory.summary == "기존 요약"
    assert len(memory.recent_messages) == 12
    assert memory.recent_messages[-1].content == "msg-29"


def test_memory_summary_can_be_none() -> None:
    memory = build_memory(summary=None, messages=make_messages(3))

    assert memory.summary is None
    assert len(memory.recent_messages) == 3
