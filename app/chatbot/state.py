"""LangGraph가 노드 사이에서 주고받는 대화 상태."""

from typing import Literal, TypedDict

from pydantic import BaseModel

from app.chatbot.tools import ToolResult
from app.common.conversation import ChatMessage, ConversationContext
from app.common.models import ActorContext
from app.llm.models import LLMMessage, ToolCall
from app.routine.schemas import RoutineResult, SourceReference

# personal: 개인 데이터 조회(Function Calling) / service_policy: RAG / routine: 루틴 추천 / reject: 거절
ChatIntent = Literal["personal", "service_policy", "routine", "reject"]


class IntentClassification(BaseModel):
    """의도가 규칙 기반 키워드로 모호할 때만 LLM 1회 호출로 받는 분류 결과."""

    intent: ChatIntent


class ChatState(TypedDict, total=False):
    """그래프 실행 1회(메시지 1건 처리)의 전체 상태. 각 노드는 일부 키만 갱신해 반환한다."""

    request_id: str
    session_id: str
    actor: ActorContext
    message: str
    intent_hint: str | None

    summary: str | None
    recent_messages: list[ChatMessage]
    contexts: list[ConversationContext]

    intent: ChatIntent | None
    route: str | None

    llm_messages: list[LLMMessage]
    pending_tool_calls: list[ToolCall]
    tool_results: list[ToolResult]

    routine_result: RoutineResult | None

    answer: str | None
    sources: list[SourceReference]

    llm_call_count: int
    tool_call_count: int
    error_code: str | None
