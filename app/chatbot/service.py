"""챗봇 대화 1턴을 실행하는 Use Case. 라우터는 이 서비스만 알고, LangGraph/LangChain/
Gemini는 몰라도 된다 — 그런 구현 세부사항은 전부 이 파일 아래(graph/nodes)에 있다.

chat()은 SSE 문자열을 흘려보내는 async generator다. 그래프 실행은 백그라운드 task로
돌리고, agent_node/rag_node가 stream_queue에 넣는 텍스트 델타를 즉시 delta 이벤트로
내보낸다. 에러는 access_guard 실패든 LLM 호출 한도 초과든 타임아웃이든 전부
error 이벤트로 통일한다 — 스트림은 이미 200으로 시작했으므로 HTTP status를
나중에 바꿀 수 없기 때문이다."""

import asyncio
import json
import logging
from typing import AsyncIterator

from app.chatbot.exceptions import ChatRequestTimeoutError, LLMCallLimitExceededError
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.schemas import ChatRequest, ChatResponse
from app.chatbot.state import ChatState
from app.chatbot.tools import ToolExecutionContext, ToolRegistry
from app.core.exceptions import AppError
from app.core.logging import get_request_id
from app.core.settings import get_settings
from app.llm.errors import LLMError
from app.routine.exceptions import ActorRoleNotAllowedError, SubscriptionRequiredError

logger = logging.getLogger(__name__)

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

# error_handlers.py의 LLM 오류 재시도 가능 여부 매핑과 동일하게 유지한다.
_LLM_ERROR_RETRYABLE = {
    "LLM_NETWORK_ERROR": True,
    "LLM_RATE_LIMITED": True,
    "LLM_INVALID_RESPONSE": False,
}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error_payload(exc: Exception, request_id: str) -> dict:
    if isinstance(exc, AppError):
        return {"code": exc.code, "message": exc.message, "request_id": request_id, "retryable": exc.retryable}
    if isinstance(exc, LLMError):
        retryable = _LLM_ERROR_RETRYABLE.get(exc.code, False)
        message = (
            "AI 서버 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            if retryable
            else "요청을 처리하지 못했습니다. 다른 방식으로 다시 시도해 주세요."
        )
        return {"code": exc.code, "message": message, "request_id": request_id, "retryable": retryable}
    return {
        "code": "INTERNAL_ERROR",
        "message": "서버 내부 오류가 발생했습니다.",
        "request_id": request_id,
        "retryable": False,
    }


class _StreamDone:
    """그래프 실행이 끝났음을 큐로 알리는 신호. result가 있으면 정상 종료,
    error가 있으면 예외/타임아웃으로 종료된 것이다."""

    __slots__ = ("result", "error")

    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error


class ChatbotService:
    def __init__(self, *, graph, deps: ChatbotDeps) -> None:
        self._graph = graph
        self._deps = deps

    async def _run_graph_and_signal(self, initial_state: ChatState, config: dict, queue: asyncio.Queue) -> None:
        try:
            result = await asyncio.wait_for(
                self._graph.ainvoke(initial_state, config=config),
                timeout=get_settings().request_timeout_seconds,
            )
            await queue.put(_StreamDone(result=result))
        except asyncio.TimeoutError:
            logger.warning(
                "chatbot_graph_timeout request_id=%s timeout_seconds=%s",
                get_request_id(),
                get_settings().request_timeout_seconds,
            )
            await queue.put(_StreamDone(error=ChatRequestTimeoutError()))
        except (AppError, LLMError) as e:  # 그래프 내부에서 던진 예상된 오류. 상세 코드만 남긴다.
            logger.warning(
                "chatbot_graph_handled_error request_id=%s code=%s",
                get_request_id(),
                getattr(e, "code", None),
            )
            await queue.put(_StreamDone(error=e))
        except Exception as e:  # 스트림을 안전하게 끝내기 위해 모든 예외를 error 이벤트로 변환한다.
            logger.exception("chatbot_graph_unexpected_error request_id=%s", get_request_id())
            await queue.put(_StreamDone(error=e))

    async def chat(self, request: ChatRequest) -> AsyncIterator[str]:
        """요청 1건을 그래프로 실행하고 SSE 이벤트를 흘려보낸다."""
        request_id = get_request_id()

        try:
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
            queue: asyncio.Queue = asyncio.Queue()
            config = {
                "configurable": {
                    "deps": self._deps,
                    "tool_registry": tool_registry,
                    "stream_queue": queue,
                }
            }
        except (AppError, LLMError) as e:  # 예상된 오류. 상세 코드만 남기고 스택트레이스는 생략한다.
            logger.warning(
                "chatbot_setup_handled_error request_id=%s code=%s",
                request_id,
                getattr(e, "code", None),
            )
            yield _sse_event("error", _error_payload(e, request_id))
            return
        except Exception as e:  # 대화 이력/요약/컨텍스트 로딩 실패도 error 이벤트로 통일한다.
            logger.exception("chatbot_setup_unexpected_error request_id=%s", request_id)
            yield _sse_event("error", _error_payload(e, request_id))
            return

        task = asyncio.create_task(self._run_graph_and_signal(initial_state, config, queue))
        done_signal: _StreamDone | None = None
        try:
            while done_signal is None:
                item = await queue.get()
                if isinstance(item, _StreamDone):
                    done_signal = item
                else:
                    yield _sse_event("delta", {"text": item})
        finally:
            if not task.done():
                task.cancel()

        if done_signal.error is not None:
            yield _sse_event("error", _error_payload(done_signal.error, request_id))
            return

        result = done_signal.result
        error_code = result.get("error_code")
        if error_code:
            exception_cls = _ERROR_CODE_TO_EXCEPTION.get(error_code)
            exc = exception_cls() if exception_cls else RuntimeError(f"매핑되지 않은 챗봇 오류 코드: {error_code}")
            yield _sse_event("error", _error_payload(exc, request_id))
            return

        route = result.get("route") or "personal"
        routine_result = result.get("routine_result")
        response = ChatResponse(
            request_id=request_id,
            session_id=request.session_id,
            answer=result.get("answer") or "",
            category=_CATEGORY_BY_ROUTE.get(route, route.upper()),
            routine=routine_result,
            sources=result.get("sources") or [],
            limited=bool(routine_result and routine_result.status == "LIMITED"),
        )
        yield _sse_event("done", response.model_dump(mode="json"))
