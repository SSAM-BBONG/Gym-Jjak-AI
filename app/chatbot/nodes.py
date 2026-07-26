"""분류·조회·답변·루틴 노드. 의존성(llm/retriever/user_data/routine_service)와
이번 요청 전용 ToolRegistry는 그래프를 실행할 때
config["configurable"]로 주입받는다 — 그래프 자체는 어떤 구현체인지 모른다."""

import asyncio
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
from app.chatbot.interactions import (
    GREETING_MESSAGE,
    greeting_replies,
    next_routine_replies,
    parse_routine_preference,
    question_text,
)
from app.chatbot.tools import (
    DuplicateToolCallError,
    ToolArgumentValidationError,
    ToolCallLimitExceededError,
    ToolRegistry,
)
from app.common.conversation import ChatMessage
from app.common.models import Role
from app.common.user_data_client import UserDataClient
from app.core.settings import get_settings
from app.llm.models import LLMMessage
from app.llm.port import LLMPort
from app.rag.retriever import RetrieverPort
from app.routine.schemas import RoutineRequest, SourceReference
from app.routine.service import RoutineService

_ROUTINE_HINT = "ROUTINE_RECOMMENDATION"

_GREETING_KEYWORDS = ("안녕", "안녕하세요", "반가워", "하이")
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


def _deps(config: RunnableConfig) -> ChatbotDeps:
    return config["configurable"]["deps"]


def _tool_registry(config: RunnableConfig) -> ToolRegistry:
    return config["configurable"]["tool_registry"]


def _stream_queue(config: RunnableConfig) -> asyncio.Queue:
    return config["configurable"]["stream_queue"]


async def access_guard(state: ChatState, config: RunnableConfig) -> dict:
    """Spring이 선검증한 구독을 신뢰하고, FastAPI에서는 역할만 확인한다."""
    actor = state["actor"]
    if actor.role != Role.USER:
        return {"error_code": "ROLE_NOT_ALLOWED"}

    return {}


async def intent_router(state: ChatState, config: RunnableConfig) -> dict:
    """intent_hint가 있으면 그대로 따르고(LLM 분류 생략), 아니면 고신뢰 키워드로 먼저
    분류한다. 어느 키워드에도 안 걸리면 그때만 LLM을 1회 호출해 분류한다."""
    if state.get("error_code"):
        return {}

    if state.get("intent_hint") == _ROUTINE_HINT:
        return {"intent": "routine", "route": "routine"}

    message = state["message"]
    normalized_message = message.strip().lower()
    if any(keyword in normalized_message for keyword in _GREETING_KEYWORDS):
        return {"intent": "greeting", "route": "greeting"}
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
    (이 재호출은 재시도가 아니라 정상적인 Function Calling 후속 턴이다).
    LLM 응답은 stream_queue로 델타를 흘려보내며 생성한다 — 도구 호출을 요청하는 중간 턴은
    보통 텍스트가 비어 있어 실질적으로 델타가 나가지 않는다."""
    call_count = state.get("llm_call_count", 0)
    if call_count >= get_settings().llm_call_limit:
        return {"error_code": "LLM_CALL_LIMIT_EXCEEDED", "pending_tool_calls": []}

    deps = _deps(config)
    queue = _stream_queue(config)
    llm_messages = state.get("llm_messages") or _build_initial_agent_messages(state)

    response = None
    # tool_definitions()를 넘겨야 Gemini가 두 Spring 조회 도구를 Function Call 후보로 인식한다.
    # 실행은 여기서 직접 하지 않고, 모델 응답 뒤 LangGraph의 tool_node가 담당한다.
    async for chunk in deps.llm.stream(llm_messages, tools=_tool_registry(config).tool_definitions()):
        if chunk.delta:
            await queue.put(chunk.delta)
        if chunk.response is not None:
            response = chunk.response

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
            # Spring data만 JSON으로 직렬화해 ToolMessage에 넣는다. 내부 헤더/세션 정보는 모델에 노출하지 않는다.
            result = await registry.execute(call.name, call.args)
            content = json.dumps(result.data, ensure_ascii=False, default=str)
            tool_results.append(result)
        except DuplicateToolCallError:
            content = json.dumps({"error": "DUPLICATE_TOOL_CALL"})
        except ToolCallLimitExceededError:
            content = json.dumps({"error": "TOOL_CALL_LIMIT_EXCEEDED"})
        except ToolArgumentValidationError:
            content = json.dumps({"error": "TOOL_INPUT_INVALID"})
        llm_messages.append(LLMMessage(role="tool", content=content, tool_call_id=call.id))
        tool_call_count += 1

    return {
        "llm_messages": llm_messages,
        "pending_tool_calls": [],
        "tool_results": tool_results,
        "tool_call_count": tool_call_count,
    }


async def rag_node(state: ChatState, config: RunnableConfig) -> dict:
    """서비스/정책 질문. RAG 검색 결과를 근거로 LLM이 1회 호출로 답변을 만든다.
    답변 텍스트는 stream_queue로 델타를 흘려보내며 생성한다."""
    deps = _deps(config)
    queue = _stream_queue(config)
    documents = await deps.retriever.search(state["message"], category=None, keywords=[], top_k=3)
    prompt = build_rag_prompt(message=state["message"], documents=documents)

    response = None
    async for chunk in deps.llm.stream([LLMMessage(role="user", content=prompt)]):
        if chunk.delta:
            await queue.put(chunk.delta)
        if chunk.response is not None:
            response = chunk.response

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
    LLM 구조화 출력은 전부 그 서비스 책임이다. 실시간 토큰 스트리밍은 없지만, delta 이벤트가
    항상 한 번은 나가도록 완성된 요약을 단일 델타로 stream_queue에 흘려보낸다."""
    deps = _deps(config)
    preference = parse_routine_preference(state.get("contexts") or [])
    replies = next_routine_replies(preference)

    if preference.has_selected_value() and replies:
        answer = question_text(replies)
        await _stream_queue(config).put(answer)
        return {
            "answer": answer,
            "quick_replies": replies,
            "sources": [],
        }

    result = await deps.routine_service.recommend_for_member(
        actor=state["actor"],
        # The snapshot is request-scoped and has already been authorized and assembled by Spring.
        request=RoutineRequest(
            message=state["message"],
            personal_data=state.get("personal_data"),
        ),
    )
    answer = result.summary if not replies else f"{result.summary}\n\n{question_text(replies)}"
    await _stream_queue(config).put(answer)
    return {
        "routine_result": result,
        "answer": answer,
        "quick_replies": replies,
        "sources": result.sources,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }


async def greeting_node(state: ChatState, config: RunnableConfig) -> dict:
    """인사말은 LLM 분류·RAG 없이 고정 안내와 기능 선택지를 반환한다."""
    await _stream_queue(config).put(GREETING_MESSAGE)
    return {
        "answer": GREETING_MESSAGE,
        "quick_replies": greeting_replies(),
        "sources": [],
    }


async def reject_node(state: ChatState, config: RunnableConfig) -> dict:
    """서비스 무관 질문, 타인 정보 요청 등. 도구/LLM을 전혀 호출하지 않고 정중히 거절한다.
    다른 route와 마찬가지로 delta 이벤트가 한 번은 나가도록 거절 메시지를 단일 델타로
    stream_queue에 흘려보낸다."""
    await _stream_queue(config).put(REJECT_MESSAGE)
    return {"answer": REJECT_MESSAGE, "sources": []}


async def format_node(state: ChatState, config: RunnableConfig) -> dict:
    """오류가 없으면 answer/sources 기본값을 채운다. 오류가 있으면 그대로 통과시켜
    persist_node가 저장을 건너뛰게 한다."""
    if state.get("error_code"):
        return {}
    return {
        "answer": state.get("answer") or _FALLBACK_ANSWER,
        "sources": state.get("sources") or [],
        "quick_replies": state.get("quick_replies") or [],
    }
