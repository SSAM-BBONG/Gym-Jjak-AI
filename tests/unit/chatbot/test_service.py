"""ChatbotService.chat()의 SSE 스트리밍 계약 검증. delta/done/error 이벤트 포맷과
순서, 그리고 에러가 항상 error 이벤트로 통일되는지를 확인한다."""

import asyncio
import json

import pytest

from app.chatbot.graph import build_chatbot_graph
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.schemas import ChatRequest
from app.chatbot.service import ChatbotService
from app.common.models import ActorContext, PaymentHistory, Role
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


async def test_chat_emits_error_event_for_inactive_subscription() -> None:
    builder = _Builder()
    builder.user_data._subscriptions[MEMBER_ID].is_active = False
    service = build_service(builder)

    events = await _run(service, chat_request())

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "CHATBOT_SUBSCRIPTION_REQUIRED"
    assert data["retryable"] is False
    assert data["request_id"]


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


async def test_chat_uses_actor_fixed_id_for_function_calling() -> None:
    builder = _Builder()
    builder.user_data._payment_histories[MEMBER_ID] = [
        PaymentHistory(paid_at="2026-07-01T00:00:00", amount="10000", item_name="테스트")
    ]
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_payment_history", args={}, id="call-1")]),
        LLMResponse(text="결제 내역을 안내드립니다."),
    ]
    service = build_service(builder)

    events = await _run(service, chat_request(message="결제 내역 알려줘"))

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "PERSONAL"
    assert builder.user_data.calls[-1] == ("get_payment_history", MEMBER_ID)


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


async def test_chat_emits_llm_call_limit_exceeded_error_event() -> None:
    builder = _Builder()
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_pt_usage", args={"n": i}, id=f"call-{i}")])
        for i in range(10)
    ]
    service = build_service(builder)

    events = await _run(service, chat_request(message="결제 내역 알려줘"))

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "LLM_CALL_LIMIT_EXCEEDED"
