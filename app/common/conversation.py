"""대화 이력·요약·컨텍스트 경계. Redis로 교체 가능하도록 Protocol과 구현체를 분리한다.
챗봇 서비스는 구체 InMemoryConversationProvider를 import하지 않고 ConversationProvider만
생성자로 주입받는다. InMemory 구현은 개발/테스트 프로세스 수명 동안만 유지되고,
비활성 세션 6개월 보존 정책의 실제 삭제는 Spring/Redis 연동 범위에서 구현한다."""

from datetime import datetime, timedelta
from typing import Callable, Literal, Protocol

from pydantic import BaseModel

# 컨텍스트 종류별 만료 정책. None이면 명시적 만료 없이 세션(프로세스) 수명 동안만 유지된다.
_CONTEXT_TTL_DAYS: dict[str, int | None] = {
    "PAIN": 7,
    "ROUTINE_PREFERENCE": 30,
    "LOCATION_TIME": None,
}

# load_recent_messages()의 기본 개수. 대화 맥락으로 LLM에 넘기는 최근 메시지 수.
RECENT_MESSAGE_LIMIT = 12

ContextKind = Literal["PAIN", "ROUTINE_PREFERENCE", "LOCATION_TIME"]


class ChatMessage(BaseModel):
    """대화 메시지 1건."""

    session_id: str
    user_id: int
    role: Literal["user", "assistant"]
    content: str


class ConversationContext(BaseModel):
    """세션 안에서 기억해둘 짧은 사실 1건(예: 통증 부위, 선호 루틴).
    expires_at이 None이면 명시적 만료 없이 세션이 끝날 때까지만 유지된다."""

    session_id: str
    user_id: int
    kind: ContextKind
    value: str
    expires_at: datetime | None = None


class ChatMemory(BaseModel):
    """LLM 프롬프트 조립에 사용할 압축된 대화 기억(요약 + 최근 메시지)."""

    summary: str | None
    recent_messages: list[ChatMessage]


def resolve_context_expiry(kind: ContextKind, now: datetime) -> datetime | None:
    """컨텍스트 종류별 TTL 정책에 따라 만료 시각을 계산한다.
    PAIN=7일, ROUTINE_PREFERENCE=30일, LOCATION_TIME=만료 없음(세션 종료까지)."""
    ttl_days = _CONTEXT_TTL_DAYS[kind]
    if ttl_days is None:
        return None
    return now + timedelta(days=ttl_days)


def build_memory(*, summary: str | None, messages: list[ChatMessage]) -> ChatMemory:
    """요약과 메시지 전체 이력에서 최근 RECENT_MESSAGE_LIMIT개만 잘라 ChatMemory를 만든다.
    프롬프트 크기를 억제하기 위해 오래된 메시지는 summary가 이미 압축했다고 가정한다."""
    return ChatMemory(summary=summary, recent_messages=messages[-RECENT_MESSAGE_LIMIT:])


class ConversationProvider(Protocol):
    """대화 이력/요약/컨텍스트 저장소 계약. 구현체를 InMemory <-> Redis로 교체해도
    챗봇 서비스 코드는 이 인터페이스만 알면 된다."""

    async def load_summary(self, session_id: str, user_id: int) -> str | None:
        """세션 요약을 조회한다. 없으면 None."""
        ...

    async def load_recent_messages(
        self, session_id: str, user_id: int, limit: int = RECENT_MESSAGE_LIMIT
    ) -> list[ChatMessage]:
        """최근 메시지를 시간순으로 최대 limit개 조회한다."""
        ...

    async def load_context(
        self, session_id: str, user_id: int, limit: int = 20
    ) -> list[ConversationContext]:
        """만료되지 않은 컨텍스트만 조회한다."""
        ...

    async def append_message(self, message: ChatMessage) -> None:
        """메시지 1건을 이력에 추가한다."""
        ...

    async def save_summary(self, session_id: str, user_id: int, summary: str) -> None:
        """세션 요약을 저장(덮어쓰기)한다."""
        ...

    async def save_context(self, context: ConversationContext) -> None:
        """컨텍스트 1건을 저장한다."""
        ...


class InMemoryConversationProvider:
    """ConversationProvider의 기본 구현체. 프로세스 메모리에만 저장하며 재시작하면 사라진다.
    now는 만료 판정 기준 시각을 주입받기 위한 것으로, 테스트에서 시각을 고정할 때 쓴다."""

    def __init__(self, *, now: Callable[[], datetime] = datetime.now) -> None:
        self._now = now
        self._summaries: dict[tuple[str, int], str] = {}
        self._messages: dict[tuple[str, int], list[ChatMessage]] = {}
        self._contexts: dict[tuple[str, int], list[ConversationContext]] = {}

    async def load_summary(self, session_id: str, user_id: int) -> str | None:
        return self._summaries.get((session_id, user_id))

    async def load_recent_messages(
        self, session_id: str, user_id: int, limit: int = RECENT_MESSAGE_LIMIT
    ) -> list[ChatMessage]:
        messages = self._messages.get((session_id, user_id), [])
        return messages[-limit:]

    async def load_context(
        self, session_id: str, user_id: int, limit: int = 20
    ) -> list[ConversationContext]:
        now = self._now()
        items = [
            context
            for context in self._contexts.get((session_id, user_id), [])
            if context.expires_at is None or context.expires_at > now
        ]
        return items[-limit:]

    async def append_message(self, message: ChatMessage) -> None:
        key = (message.session_id, message.user_id)
        self._messages.setdefault(key, []).append(message)

    async def save_summary(self, session_id: str, user_id: int, summary: str) -> None:
        self._summaries[(session_id, user_id)] = summary

    async def save_context(self, context: ConversationContext) -> None:
        key = (context.session_id, context.user_id)
        self._contexts.setdefault(key, []).append(context)
