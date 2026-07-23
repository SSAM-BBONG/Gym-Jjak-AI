from app.common.conversation import ChatMessage, ConversationContext


class FakeConversationProvider:
    """ConversationProvider의 가짜 구현체. 만료·세션격리 같은 실제 정책은
    InMemoryConversationProvider에서 검증하고, 이 Fake는 챗봇 그래프/서비스 테스트에서
    대화 기억 의존을 미리 정해둔 값으로 단순화하는 용도다. 호출 인자도 기록한다."""

    def __init__(
        self,
        *,
        summary: str | None = None,
        recent_messages: list[ChatMessage] | None = None,
        context: list[ConversationContext] | None = None,
    ) -> None:
        self.summary = summary
        self.recent_messages = recent_messages or []
        self.context = context or []
        self.appended_messages: list[ChatMessage] = []
        self.saved_summaries: list[tuple[str, int, str]] = []
        self.saved_contexts: list[ConversationContext] = []

    async def load_summary(self, session_id: str, user_id: int) -> str | None:
        return self.summary

    async def load_recent_messages(
        self, session_id: str, user_id: int, limit: int = 12
    ) -> list[ChatMessage]:
        return self.recent_messages[-limit:]

    async def load_context(
        self, session_id: str, user_id: int, limit: int = 20
    ) -> list[ConversationContext]:
        return self.context[:limit]

    async def append_message(self, message: ChatMessage) -> None:
        self.appended_messages.append(message)

    async def save_summary(self, session_id: str, user_id: int, summary: str) -> None:
        self.saved_summaries.append((session_id, user_id, summary))

    async def save_context(self, context: ConversationContext) -> None:
        self.saved_contexts.append(context)
