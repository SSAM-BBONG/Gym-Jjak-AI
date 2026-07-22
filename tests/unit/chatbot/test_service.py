"""ChatbotService.chat()의 실제 로직 검증. Task 12 통합 테스트는 FakeChatbotService로
전체를 교체해 실제 chat() 코드가 검증되지 않았던 걸 여기서 메운다."""

import asyncio

import pytest

from app.chatbot.exceptions import ChatRequestTimeoutError, LLMCallLimitExceededError
from app.chatbot.graph import build_chatbot_graph
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.schemas import ChatRequest
from app.chatbot.service import ChatbotService
from app.common.models import PaymentHistory
from app.llm.models import LLMResponse, ToolCall
from app.routine.exceptions import ActorRoleNotAllowedError, SubscriptionRequiredError

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


async def test_chat_returns_response_with_request_id_and_category() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    response = await service.chat(chat_request())

    assert response.answer == "환불은 7일 이내 가능합니다."
    assert response.category == "SERVICE_POLICY"
    assert response.request_id
    assert response.session_id == "session-1"


async def test_chat_persists_via_conversation_provider() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    await service.chat(chat_request())

    assert len(builder.conversation.appended_messages) == 2  # user + assistant


async def test_chat_returns_routine_result_and_limited_flag() -> None:
    builder = _Builder()
    builder.llm.structured_response = sample_routine_result()
    service = build_service(builder)

    response = await service.chat(chat_request(message="루틴 추천해줘"))

    assert response.category == "ROUTINE"
    assert response.routine is not None
    # 기본 _Builder에는 운동일지/인바디를 채워두지 않아 LIMITED가 정상이다.
    assert response.limited is True
    assert set(response.routine.missing_data) == {"workout_diaries", "inbody"}


async def test_chat_raises_subscription_required_for_inactive_subscription() -> None:
    builder = _Builder()
    builder.user_data._subscriptions[MEMBER_ID].is_active = False
    service = build_service(builder)

    with pytest.raises(SubscriptionRequiredError):
        await service.chat(chat_request())


async def test_chat_raises_role_not_allowed_for_trainer_actor() -> None:
    from app.common.models import ActorContext, Role

    builder = _Builder()
    service = build_service(builder)

    with pytest.raises(ActorRoleNotAllowedError):
        await service.chat(chat_request(actor=ActorContext(user_id=20, role=Role.TRAINER)))


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

    response = await service.chat(chat_request(message="결제 내역 알려줘"))

    assert response.category == "PERSONAL"
    assert builder.user_data.calls[-1] == ("get_payment_history", MEMBER_ID)


async def test_chat_raises_timeout_error_when_graph_exceeds_budget(monkeypatch) -> None:
    builder = _Builder()
    service = build_service(builder)

    async def _hang(coro, *args, **kwargs):
        coro.close()  # 실제로 await하지 않아 생기는 ResourceWarning 방지
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", _hang)

    with pytest.raises(ChatRequestTimeoutError):
        await service.chat(chat_request())


async def test_chat_maps_llm_call_limit_exceeded() -> None:
    builder = _Builder()
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_pt_usage", args={"n": i}, id=f"call-{i}")])
        for i in range(10)
    ]
    service = build_service(builder)

    with pytest.raises(LLMCallLimitExceededError):
        await service.chat(chat_request(message="결제 내역 알려줘"))
