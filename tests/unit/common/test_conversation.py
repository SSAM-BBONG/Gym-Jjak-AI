from datetime import datetime, timedelta

from app.common.conversation import (
    RECENT_MESSAGE_LIMIT,
    ChatMessage,
    ConversationContext,
    InMemoryConversationProvider,
    resolve_context_expiry,
)

_SESSION_A = "session-1"
_SESSION_B = "session-2"
_USER_A = 10
_USER_B = 20


def message(*, session_id: str = _SESSION_A, user_id: int = _USER_A, content: str = "hi", role: str = "user") -> ChatMessage:
    return ChatMessage(session_id=session_id, user_id=user_id, role=role, content=content)


def context_item(
    *,
    session_id: str = _SESSION_A,
    user_id: int = _USER_A,
    kind: str = "PAIN",
    value: str = "왼쪽 무릎 불편",
    expires_at: datetime | None = None,
) -> ConversationContext:
    return ConversationContext(
        session_id=session_id, user_id=user_id, kind=kind, value=value, expires_at=expires_at
    )


async def test_load_context_excludes_expired_items() -> None:
    now = datetime(2026, 7, 22, 12, 0, 0)
    provider = InMemoryConversationProvider(now=lambda: now)
    await provider.save_context(context_item(expires_at=now - timedelta(seconds=1)))

    context = await provider.load_context(session_id=_SESSION_A, user_id=_USER_A, limit=20)

    assert context == []


async def test_load_context_keeps_items_without_expiry() -> None:
    now = datetime(2026, 7, 22, 12, 0, 0)
    provider = InMemoryConversationProvider(now=lambda: now)
    await provider.save_context(context_item(kind="LOCATION_TIME", expires_at=None))

    context = await provider.load_context(session_id=_SESSION_A, user_id=_USER_A, limit=20)

    assert len(context) == 1


async def test_load_context_keeps_items_not_yet_expired() -> None:
    now = datetime(2026, 7, 22, 12, 0, 0)
    provider = InMemoryConversationProvider(now=lambda: now)
    await provider.save_context(context_item(expires_at=now + timedelta(days=1)))

    context = await provider.load_context(session_id=_SESSION_A, user_id=_USER_A, limit=20)

    assert len(context) == 1


async def test_recent_messages_limited_to_default_twelve() -> None:
    provider = InMemoryConversationProvider()
    for i in range(30):
        await provider.append_message(message(content=f"msg-{i}"))

    recent = await provider.load_recent_messages(session_id=_SESSION_A, user_id=_USER_A, limit=RECENT_MESSAGE_LIMIT)

    assert len(recent) == RECENT_MESSAGE_LIMIT
    assert recent[-1].content == "msg-29"


async def test_summary_save_and_load_roundtrip() -> None:
    provider = InMemoryConversationProvider()
    await provider.save_summary(_SESSION_A, _USER_A, "기존 요약")

    summary = await provider.load_summary(_SESSION_A, _USER_A)

    assert summary == "기존 요약"


async def test_summary_missing_returns_none() -> None:
    provider = InMemoryConversationProvider()

    summary = await provider.load_summary(_SESSION_A, _USER_A)

    assert summary is None


async def test_sessions_are_isolated() -> None:
    provider = InMemoryConversationProvider()
    await provider.append_message(message(session_id=_SESSION_A, content="A"))
    await provider.append_message(message(session_id=_SESSION_B, content="B"))

    a_messages = await provider.load_recent_messages(session_id=_SESSION_A, user_id=_USER_A, limit=20)
    b_messages = await provider.load_recent_messages(session_id=_SESSION_B, user_id=_USER_A, limit=20)

    assert [m.content for m in a_messages] == ["A"]
    assert [m.content for m in b_messages] == ["B"]


async def test_users_are_isolated_even_in_same_session_id() -> None:
    provider = InMemoryConversationProvider()
    await provider.append_message(message(user_id=_USER_A, content="from-A"))
    await provider.append_message(message(user_id=_USER_B, content="from-B"))

    a_messages = await provider.load_recent_messages(session_id=_SESSION_A, user_id=_USER_A, limit=20)

    assert [m.content for m in a_messages] == ["from-A"]


def test_resolve_context_expiry_matches_ttl_policy() -> None:
    now = datetime(2026, 7, 22, 12, 0, 0)

    assert resolve_context_expiry("PAIN", now) == now + timedelta(days=7)
    assert resolve_context_expiry("ROUTINE_PREFERENCE", now) == now + timedelta(days=30)
    assert resolve_context_expiry("LOCATION_TIME", now) is None
