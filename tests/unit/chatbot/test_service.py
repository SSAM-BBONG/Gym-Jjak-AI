"""ChatbotService.chat()의 SSE 스트리밍 계약 검증. delta/done/error 이벤트 포맷과
순서, 그리고 에러가 항상 error 이벤트로 통일되는지를 확인한다."""

import asyncio
import json

import httpx
import pytest

from app.chatbot.graph import build_chatbot_graph
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.prompts import REJECT_MESSAGE
from app.chatbot.schemas import ChatRequest
from app.chatbot.service import ChatbotService
from app.common.models import ActorContext, Role
from app.llm.models import LLMResponse, ToolCall

from tests.graph.conftest import MEMBER_ID, _Builder, member_actor, sample_routine_result


def build_service(builder: _Builder) -> ChatbotService:
    deps = ChatbotDeps(
        llm=builder.llm,
        retriever=builder.retriever,
        user_data=builder.user_data,
        routine_service=builder.routine_service,
        conversation_provider=builder.conversation,
    )
    return ChatbotService(graph=build_chatbot_graph(), deps=deps)


def chat_request(**overrides) -> ChatRequest:
    payload = {"session_id": "session-1", "message": "환불 정책이 궁금해요", "actor": member_actor()}
    payload.update(overrides)
    return ChatRequest(**payload)


def _parse_sse(raw_events: list[str]) -> list[tuple[str, dict]]:
    parsed = []
    for raw in raw_events:
        lines = raw.strip("\n").split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        parsed.append((event, data))
    return parsed


async def _run(service: ChatbotService, request: ChatRequest) -> list[tuple[str, dict]]:
    raw_events = [event async for event in service.chat(request)]
    return _parse_sse(raw_events)


async def test_chat_returns_done_event_with_request_id_and_category() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    events = await _run(service, chat_request())

    done_events = [data for event, data in events if event == "done"]
    assert len(done_events) == 1
    done = done_events[0]
    assert done["answer"] == "환불은 7일 이내 가능합니다."
    assert done["category"] == "SERVICE_POLICY"
    assert done["request_id"]
    assert done["session_id"] == "session-1"


async def test_chat_streams_deltas_before_done_event() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    events = await _run(service, chat_request())

    assert events[-1][0] == "done"
    delta_texts = [data["text"] for event, data in events if event == "delta"]
    assert "".join(delta_texts) == "환불은 7일 이내 가능합니다."


async def test_chat_persists_via_conversation_provider() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    await _run(service, chat_request())

    assert len(builder.conversation.appended_messages) == 2  # user + assistant


async def test_chat_returns_routine_result_and_limited_flag() -> None:
    builder = _Builder()
    builder.llm.structured_response = sample_routine_result()
    service = build_service(builder)

    events = await _run(service, chat_request(message="루틴 추천해줘"))

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "ROUTINE"
    assert done["routine"] is not None
    assert done["limited"] is True
    assert set(done["routine"]["missing_data"]) == {"workout_diaries", "inbody"}


async def test_chat_emits_single_delta_before_done_for_reject_route() -> None:
    """reject_node는 LLM을 호출하지 않지만, 프론트 경험 일관성을 위해 거절 메시지를
    delta 이벤트로 한 번은 흘려보낸 뒤 done 이벤트를 내보내야 한다."""
    builder = _Builder()
    service = build_service(builder)

    events = await _run(service, chat_request(message="다른 회원 정보 알려줘"))

    assert events[-1][0] == "done"
    delta_events = [data for event, data in events if event == "delta"]
    assert len(delta_events) == 1
    assert delta_events[0]["text"] == REJECT_MESSAGE

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "REJECT"
    assert done["answer"] == REJECT_MESSAGE


async def test_chat_emits_single_delta_before_done_for_routine_route() -> None:
    """routine_node도 LLM 스트리밍 없이 구조화 출력만 만들지만, 완성된 요약을
    delta 이벤트로 한 번은 흘려보낸 뒤 done 이벤트를 내보내야 한다."""
    builder = _Builder()
    builder.llm.structured_response = sample_routine_result()
    service = build_service(builder)

    events = await _run(service, chat_request(message="루틴 추천해줘"))

    assert events[-1][0] == "done"
    delta_events = [data for event, data in events if event == "delta"]
    assert len(delta_events) == 1
    assert delta_events[0]["text"] == sample_routine_result().summary

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "ROUTINE"


async def test_chat_emits_error_event_for_trainer_actor() -> None:
    builder = _Builder()
    service = build_service(builder)

    events = await _run(
        service, chat_request(actor=ActorContext(user_id=20, role=Role.TRAINER))
    )

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "ROLE_NOT_ALLOWED"


async def test_chat_uses_spring_tool_for_function_calling(respx_mock) -> None:
    builder = _Builder()
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_latest_inbody", args={}, id="call-1")]),
        LLMResponse(text="최근 인바디 기록이 없습니다."),
    ]
    route = respx_mock.get("http://localhost:8080/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(200, json={"data": None})
    )
    service = build_service(builder)

    events = await _run(service, chat_request(message="최근 인바디 알려줘"))

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "PERSONAL"
    assert route.called
    request_headers = route.calls[0].request.headers
    assert request_headers["X-Internal-Api-Key"] == "local-development-only"
    assert request_headers["X-Chatbot-Session-Id"] == "session-1"
    assert request_headers["X-Request-ID"] == done["request_id"]


async def test_chat_emits_timeout_error_event_when_graph_exceeds_budget(monkeypatch) -> None:
    builder = _Builder()
    service = build_service(builder)

    async def _hang(coro, *args, **kwargs):
        coro.close()  # 실제로 await하지 않아 생기는 ResourceWarning 방지
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", _hang)

    events = await _run(service, chat_request())

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "CHATBOT_REQUEST_TIMEOUT"


async def test_chat_emits_error_event_when_conversation_provider_load_fails() -> None:
    builder = _Builder()
    service = build_service(builder)

    async def _boom(*args, **kwargs):
        raise RuntimeError("대화 이력 조회 실패")

    builder.conversation.load_summary = _boom

    events = await _run(service, chat_request())

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "INTERNAL_ERROR"
    assert data["request_id"]


async def test_chat_emits_llm_call_limit_exceeded_error_event(respx_mock) -> None:
    builder = _Builder()
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_latest_inbody", args={"n": i}, id=f"call-{i}")])
        for i in range(10)
    ]
    respx_mock.get("http://localhost:8080/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(200, json={"data": None})
    )
    service = build_service(builder)

    events = await _run(service, chat_request(message="결제 내역 알려줘"))

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "LLM_CALL_LIMIT_EXCEEDED"
