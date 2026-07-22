"""챗봇 대화 1턴을 실행하는 Use Case. 라우터는 이 서비스만 알고, LangGraph/LangChain/
Gemini는 몰라도 된다 — 그런 구현 세부사항은 전부 이 파일 아래(graph/nodes)에 있다."""

import asyncio

from app.chatbot.exceptions import ChatRequestTimeoutError, LLMCallLimitExceededError
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.schemas import ChatRequest, ChatResponse
from app.chatbot.state import ChatState
from app.chatbot.tools import ToolExecutionContext, ToolRegistry
from app.core.logging import get_request_id
from app.core.settings import get_settings
from app.routine.exceptions import ActorRoleNotAllowedError, SubscriptionRequiredError

_ERROR_CODE_TO_EXCEPTION = {
    "ROLE_NOT_ALLOWED": ActorRoleNotAllowedError,
    "CHATBOT_SUBSCRIPTION_REQUIRED": SubscriptionRequiredError,
    "LLM_CALL_LIMIT_EXCEEDED": LLMCallLimitExceededError,
}

_CATEGORY_BY_ROUTE = {
    "routine": "ROUTINE",
    "personal": "PERSONAL",
    "service_policy": "SERVICE_POLICY",
    "reject": "REJECT",
}


class ChatbotService:
    def __init__(self, *, graph, deps: ChatbotDeps) -> None:
        self._graph = graph
        self._deps = deps

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """요청 1건을 그래프로 실행하고 외부 API 계약 형태로 변환한다.
        그래프가 error_code를 반환하면 해당 도메인 예외로 승격해 공통 오류 응답을 타게 한다."""
        request_id = get_request_id()

        summary = await self._deps.conversation_provider.load_summary(
            request.session_id, request.actor.user_id
        )
        recent_messages = await self._deps.conversation_provider.load_recent_messages(
            request.session_id, request.actor.user_id
        )
        contexts = await self._deps.conversation_provider.load_context(
            request.session_id, request.actor.user_id
        )

        initial_state = ChatState(
            request_id=request_id,
            session_id=request.session_id,
            actor=request.actor,
            message=request.message,
            intent_hint=request.intent_hint,
            summary=summary,
            recent_messages=recent_messages,
            contexts=contexts,
            llm_call_count=0,
            tool_call_count=0,
        )

        tool_registry = ToolRegistry(
            user_data=self._deps.user_data,
            context=ToolExecutionContext(actor=request.actor),
        )
        config = {"configurable": {"deps": self._deps, "tool_registry": tool_registry}}

        try:
            result = await asyncio.wait_for(
                self._graph.ainvoke(initial_state, config=config),
                timeout=get_settings().request_timeout_seconds,
            )
        except asyncio.TimeoutError as e:
            raise ChatRequestTimeoutError() from e

        error_code = result.get("error_code")
        if error_code:
            exception_cls = _ERROR_CODE_TO_EXCEPTION.get(error_code)
            if exception_cls is None:
                raise RuntimeError(f"매핑되지 않은 챗봇 오류 코드: {error_code}")
            raise exception_cls()

        route = result.get("route") or "personal"
        routine_result = result.get("routine_result")
        return ChatResponse(
            request_id=request_id,
            session_id=request.session_id,
            answer=result.get("answer") or "",
            category=_CATEGORY_BY_ROUTE.get(route, route.upper()),
            routine=routine_result,
            sources=result.get("sources") or [],
            limited=bool(routine_result and routine_result.status == "LIMITED"),
        )
