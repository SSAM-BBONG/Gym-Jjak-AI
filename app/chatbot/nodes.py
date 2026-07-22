"""분류·조회·답변·루틴 노드. 의존성(llm/retriever/user_data/routine_service/
conversation_provider)과 이번 요청 전용 ToolRegistry는 그래프를 실행할 때
config["configurable"]로 주입받는다 — 그래프 자체는 어떤 구현체인지 모른다."""

import json
from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig

from app.chatbot.state import ChatState, IntentClassification
from app.chatbot.prompts import (
    PERSONAL_AGENT_SYSTEM_PROMPT,
    REJECT_MESSAGE,
    build_intent_classification_prompt,
    build_rag_prompt,
)
from app.chatbot.tools import DuplicateToolCallError, ToolCallLimitExceededError, ToolRegistry
from app.common.conversation import ChatMessage, ConversationProvider
from app.common.models import Role
from app.common.user_data_client import UserDataClient
from app.core.settings import get_settings
from app.llm.models import LLMMessage
from app.llm.port import LLMPort
from app.rag.retriever import RetrieverPort
from app.routine.schemas import RoutineRequest, SourceReference
from app.routine.service import RoutineService

_ROUTINE_HINT = "ROUTINE_RECOMMENDATION"

_ROUTINE_KEYWORDS = ("루틴", "운동 추천", "운동 루틴")
_PERSONAL_KEYWORDS = (
    "결제", "구독", "인바디", "운동일지", "온보딩", "이용권", "pt", "PT", "포인트",
)
_SERVICE_POLICY_KEYWORDS = ("환불", "정책", "고객센터", "이용약관", "요금")
_REJECT_KEYWORDS = ("다른 회원", "타인", "다른 사람", "친구 정보", "다른 사용자")

_FALLBACK_ANSWER = "죄송합니다, 지금은 답변을 생성하지 못했습니다."


@dataclass
class ChatbotDeps:
    """그래프 노드가 실제로 의존하는 것들. 매 요청 config로 주입되며 그래프 자체에는 안 묶인다."""

    llm: LLMPort
    retriever: RetrieverPort
    user_data: UserDataClient
    routine_service: RoutineService
    conversation_provider: ConversationProvider


def _deps(config: RunnableConfig) -> ChatbotDeps:
    return config["configurable"]["deps"]


def _tool_registry(config: RunnableConfig) -> ToolRegistry:
    return config["configurable"]["tool_registry"]


async def access_guard(state: ChatState, config: RunnableConfig) -> dict:
    """role=USER, 활성 구독 여부를 확인한다. 실패하면 이후 노드는 진행하되
    다른 노드들이 error_code를 보고 조기 종료한다."""
    deps = _deps(config)
    actor = state["actor"]
    if actor.role != Role.USER:
        return {"error_code": "ROLE_NOT_ALLOWED"}

    subscription = await deps.user_data.get_subscription_status(actor.user_id)
    if not subscription.is_active:
        return {"error_code": "CHATBOT_SUBSCRIPTION_REQUIRED"}
    return {}


async def intent_router(state: ChatState, config: RunnableConfig) -> dict:
    """intent_hint가 있으면 그대로 따르고(LLM 분류 생략), 아니면 고신뢰 키워드로 먼저
    분류한다. 어느 키워드에도 안 걸리면 그때만 LLM을 1회 호출해 분류한다."""
    if state.get("error_code"):
        return {}

    if state.get("intent_hint") == _ROUTINE_HINT:
        return {"intent": "routine", "route": "routine"}

    message = state["message"]
    if any(k in message for k in _REJECT_KEYWORDS):
        return {"intent": "reject", "route": "reject"}
    if any(k in message for k in _ROUTINE_KEYWORDS):
        return {"intent": "routine", "route": "routine"}
    if any(k in message for k in _PERSONAL_KEYWORDS):
        return {"intent": "personal", "route": "personal"}
    if any(k in message for k in _SERVICE_POLICY_KEYWORDS):
        return {"intent": "service_policy", "route": "service_policy"}

    deps = _deps(config)
    classification = await deps.llm.generate_structured(
        prompt=build_intent_classification_prompt(message),
        output_schema=IntentClassification,
    )
    return {
        "intent": classification.intent,
        "route": classification.intent,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }


def _build_initial_agent_messages(state: ChatState) -> list[LLMMessage]:
    messages = [LLMMessage(role="system", content=PERSONAL_AGENT_SYSTEM_PROMPT)]
    summary = state.get("summary")
    if summary:
        messages.append(LLMMessage(role="system", content=f"[이전 대화 요약]\n{summary}"))
    for m in state.get("recent_messages") or []:
        messages.append(LLMMessage(role=m.role, content=m.content))
    messages.append(LLMMessage(role="user", content=state["message"]))
    return messages


async def agent_node(state: ChatState, config: RunnableConfig) -> dict:
    """개인 데이터 질문 처리. 한 번 실행이 LLM 호출 1회다. 도구 호출을 요청하면
    pending_tool_calls를 채워 반환하고, 그래프가 tool_node로 보냈다가 다시 이리로 되돌린다
    (이 재호출은 재시도가 아니라 정상적인 Function Calling 후속 턴이다)."""
    call_count = state.get("llm_call_count", 0)
    if call_count >= get_settings().llm_call_limit:
        return {"error_code": "LLM_CALL_LIMIT_EXCEEDED", "pending_tool_calls": []}

    deps = _deps(config)
    llm_messages = state.get("llm_messages") or _build_initial_agent_messages(state)

    response = await deps.llm.generate(llm_messages)
    assistant_message = LLMMessage(
        role="assistant", content=response.text or "", tool_calls=response.tool_calls
    )
    updated_messages = [*llm_messages, assistant_message]

    if response.tool_calls:
        return {
            "llm_messages": updated_messages,
            "pending_tool_calls": response.tool_calls,
            "llm_call_count": call_count + 1,
        }
    return {
        "llm_messages": updated_messages,
        "pending_tool_calls": [],
        "answer": response.text or _FALLBACK_ANSWER,
        "llm_call_count": call_count + 1,
    }


async def tool_node(state: ChatState, config: RunnableConfig) -> dict:
    """agent_node가 요청한 도구 호출을 전부 실행하고 결과를 tool 메시지로 이력에 붙인다.
    중복 호출/한도 초과는 예외 대신 오류 데이터로 변환해 그래프를 죽이지 않는다."""
    registry = _tool_registry(config)
    llm_messages = list(state.get("llm_messages") or [])
    tool_results = list(state.get("tool_results") or [])
    tool_call_count = state.get("tool_call_count", 0)

    for call in state.get("pending_tool_calls") or []:
        try:
            result = await registry.execute(call.name, call.args)
            content = json.dumps(result.data, ensure_ascii=False, default=str)
            tool_results.append(result)
        except DuplicateToolCallError:
            content = json.dumps({"error": "DUPLICATE_TOOL_CALL"})
        except ToolCallLimitExceededError:
            content = json.dumps({"error": "TOOL_CALL_LIMIT_EXCEEDED"})
        llm_messages.append(LLMMessage(role="tool", content=content, tool_call_id=call.id))
        tool_call_count += 1

    return {
        "llm_messages": llm_messages,
        "pending_tool_calls": [],
        "tool_results": tool_results,
        "tool_call_count": tool_call_count,
    }


async def rag_node(state: ChatState, config: RunnableConfig) -> dict:
    """서비스/정책 질문. RAG 검색 결과를 근거로 LLM이 1회 호출로 답변을 만든다."""
    deps = _deps(config)
    documents = await deps.retriever.search(state["message"], category=None, keywords=[], top_k=3)
    prompt = build_rag_prompt(message=state["message"], documents=documents)
    response = await deps.llm.generate([LLMMessage(role="user", content=prompt)])

    sources = [
        SourceReference(source=d.source, title=d.title, category=d.category) for d in documents
    ]
    return {
        "answer": response.text or _FALLBACK_ANSWER,
        "sources": sources,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }


async def routine_node(state: ChatState, config: RunnableConfig) -> dict:
    """루틴 추천. RoutineService(Task 8)를 그대로 호출한다 — 안전검사·구독확인·RAG·
    LLM 구조화 출력은 전부 그 서비스 책임이다."""
    deps = _deps(config)
    result = await deps.routine_service.recommend_for_member(
        actor=state["actor"], request=RoutineRequest(message=state["message"])
    )
    return {
        "routine_result": result,
        "answer": result.summary,
        "sources": result.sources,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }


async def reject_node(state: ChatState, config: RunnableConfig) -> dict:
    """서비스 무관 질문, 타인 정보 요청 등. 도구/LLM을 전혀 호출하지 않고 정중히 거절한다."""
    return {"answer": REJECT_MESSAGE, "sources": []}


async def format_node(state: ChatState, config: RunnableConfig) -> dict:
    """오류가 없으면 answer/sources 기본값을 채운다. 오류가 있으면 그대로 통과시켜
    persist_node가 저장을 건너뛰게 한다."""
    if state.get("error_code"):
        return {}
    return {
        "answer": state.get("answer") or _FALLBACK_ANSWER,
        "sources": state.get("sources") or [],
    }


async def persist_node(state: ChatState, config: RunnableConfig) -> dict:
    """접근 검증을 통과한 user 메시지는 항상 저장한다. assistant 메시지는 성공한
    답변(error_code 없음)만 저장하고, LLM 실패 안내는 정상 assistant 메시지로 남기지 않는다."""
    if state.get("error_code"):
        return {}

    deps = _deps(config)
    session_id = state["session_id"]
    user_id = state["actor"].user_id

    await deps.conversation_provider.append_message(
        ChatMessage(session_id=session_id, user_id=user_id, role="user", content=state["message"])
    )
    answer = state.get("answer")
    if answer:
        await deps.conversation_provider.append_message(
            ChatMessage(session_id=session_id, user_id=user_id, role="assistant", content=answer)
        )
    return {}
