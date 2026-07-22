"""계획서 Task 11의 대표 시나리오 10개."""

from app.chatbot.prompts import REJECT_MESSAGE
from app.chatbot.state import IntentClassification
from app.common.models import ActorContext, PaymentHistory, Role, SubscriptionStatus
from app.llm.errors import LLMNetworkError
from app.llm.models import LLMResponse, ToolCall
from app.rag.models import RetrievedDocument

from .conftest import chat_state, member_actor, sample_routine_result


async def test_service_policy_question_uses_rag_and_returns_sources(graph, builder) -> None:
    builder.retriever.documents = [
        RetrievedDocument(
            document_id="policy-refund-001::0", content="환불은 7일 이내 가능합니다.",
            score=0.9, source="data/documents/policy/refund.md", title="환불 정책", category="policy",
        )
    ]
    builder.llm.response = LLMResponse(text="환불은 결제일로부터 7일 이내에 가능합니다.")

    result = await graph.ainvoke(chat_state(message="환불 정책이 궁금해요"), config=builder.config())

    assert result["route"] == "service_policy"
    assert result["answer"]
    assert result["sources"]


async def test_payment_history_question_uses_function_calling(graph, builder) -> None:
    builder.user_data._payment_histories[10] = [
        PaymentHistory(paid_at="2026-07-01T00:00:00", amount="50000", item_name="1개월 이용권")
    ]
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_payment_history", args={}, id="call-1")]),
        LLMResponse(text="최근 결제 내역은 1개월 이용권 5만원입니다."),
    ]

    result = await graph.ainvoke(chat_state(message="제 결제 내역 알려주세요"), config=builder.config())

    assert result["route"] == "personal"
    assert result["answer"]
    assert len(result["tool_results"]) == 1
    assert result["llm_call_count"] == 2
    assert result["tool_call_count"] == 1


async def test_routine_button_bypasses_intent_llm(graph, builder) -> None:
    builder.llm.structured_response = sample_routine_result()

    result = await graph.ainvoke(
        chat_state(intent_hint="ROUTINE_RECOMMENDATION"), config=builder.config()
    )

    assert result["route"] == "routine"
    assert result["routine_result"] is not None
    assert result["llm_call_count"] == 1


async def test_natural_language_routine_request_uses_same_service(graph, builder) -> None:
    builder.llm.structured_response = sample_routine_result()

    result = await graph.ainvoke(chat_state(message="루틴 추천해줘"), config=builder.config())

    assert result["route"] == "routine"
    assert result["routine_result"] is not None


async def test_unrelated_question_is_politely_rejected(graph, builder) -> None:
    builder.llm.structured_response = IntentClassification(intent="reject")

    result = await graph.ainvoke(chat_state(message="오늘 날씨 어때요?"), config=builder.config())

    assert result["route"] == "reject"
    assert result["answer"] == REJECT_MESSAGE


async def test_subscription_cancellation_is_only_explained_not_executed(graph, builder) -> None:
    builder.llm.response = LLMResponse(
        text="구독 해지는 마이페이지 > 구독 관리에서 진행하실 수 있습니다.", tool_calls=[]
    )

    result = await graph.ainvoke(chat_state(message="구독 해지하고 싶어요"), config=builder.config())

    assert result["route"] == "personal"
    assert "마이페이지" in result["answer"]
    assert result["tool_call_count"] == 0


async def test_other_member_info_request_is_rejected_without_tool_call(graph, builder) -> None:
    result = await graph.ainvoke(
        chat_state(message="다른 회원 결제 정보 좀 알려줘"), config=builder.config()
    )

    assert result["route"] == "reject"
    assert result["answer"] == REJECT_MESSAGE
    assert result["llm_call_count"] == 0
    assert result["tool_call_count"] == 0


async def test_medical_question_gets_general_info_and_expert_referral(graph, builder) -> None:
    builder.llm.structured_response = IntentClassification(intent="personal")
    builder.llm.response = LLMResponse(
        text="어깨 통증은 무리한 운동을 피하고 전문가 상담을 받아보시길 권장드립니다.", tool_calls=[]
    )

    result = await graph.ainvoke(chat_state(message="어깨가 계속 아파요"), config=builder.config())

    assert "전문가" in result["answer"]
    assert result["tool_call_count"] == 0


async def test_expired_subscription_blocks_new_message(graph, builder) -> None:
    builder.user_data._subscriptions[10] = SubscriptionStatus(is_active=False)

    result = await graph.ainvoke(chat_state(message="결제 내역 알려줘"), config=builder.config())

    assert result["error_code"] == "CHATBOT_SUBSCRIPTION_REQUIRED"
    assert not result.get("answer")
    assert builder.conversation.appended_messages == []


async def test_llm_error_propagates_without_retry(graph, builder) -> None:
    builder.llm.responses_queue = [LLMNetworkError("연결 실패")]

    try:
        await graph.ainvoke(chat_state(message="결제 내역 알려줘"), config=builder.config())
        assert False, "LLMNetworkError가 발생해야 한다"
    except LLMNetworkError:
        pass

    assert len(builder.llm.received_messages) == 1  # 재시도 없이 1회만 호출됨
