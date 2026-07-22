"""그래프 테스트 공용 픽스처. 모든 의존성은 Fake로 구성하고 config["configurable"]로 주입한다."""

from datetime import date

import pytest

from app.chatbot.graph import build_chatbot_graph
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.state import ChatState
from app.chatbot.tools import ToolExecutionContext, ToolRegistry
from app.common.models import ActorContext, OnboardingProfile, PtUsageSummary, Role, SubscriptionStatus
from app.routine.analyzer import WorkoutAnalyzer
from app.routine.schemas import RoutineDay, RoutineExercise, RoutineResult
from app.routine.service import RoutineService
from tests.fakes.conversation import FakeConversationProvider
from tests.fakes.llm import FakeLLMPort
from tests.fakes.retriever import FakeRetriever
from tests.fakes.user_data import FakeUserDataClient

MEMBER_ID = 10


def member_actor(*, user_id: int = MEMBER_ID) -> ActorContext:
    return ActorContext(user_id=user_id, role=Role.USER)


def sample_routine_result() -> RoutineResult:
    return RoutineResult(
        status="COMPLETE",
        title="테스트 루틴",
        summary="요약",
        days=[
            RoutineDay(
                day_label="Day 1",
                goal="전신",
                warm_up=["스트레칭"],
                exercises=[
                    RoutineExercise(
                        name="스쿼트", part="LEG", sets=3, reps="10회",
                        intensity="중강도", rest_seconds=60, rationale="기초 운동",
                    )
                ],
                cool_down=["스트레칭"],
            )
        ],
        cautions=[], missing_data=[], sources=[],
    )


def chat_state(
    *,
    message: str = "안녕하세요",
    actor: ActorContext | None = None,
    intent_hint: str | None = None,
    session_id: str = "session-1",
) -> ChatState:
    return ChatState(
        request_id="req-1",
        session_id=session_id,
        actor=actor or member_actor(),
        message=message,
        intent_hint=intent_hint,
        summary=None,
        recent_messages=[],
        contexts=[],
        llm_call_count=0,
        tool_call_count=0,
    )


class _Builder:
    """테스트별로 Fake와 config를 원하는 대로 바꿀 수 있게 해주는 조립기."""

    def __init__(self) -> None:
        self.user_data = FakeUserDataClient(
            subscriptions={MEMBER_ID: SubscriptionStatus(is_active=True)},
            onboarding_profiles={MEMBER_ID: OnboardingProfile(goal="다이어트")},
            pt_usages={MEMBER_ID: PtUsageSummary(total_sessions=10, used_sessions=3, remaining_sessions=7)},
        )
        self.retriever = FakeRetriever()
        self.llm = FakeLLMPort()
        self.conversation = FakeConversationProvider()
        self.routine_service = RoutineService(
            user_data=self.user_data,
            analyzer=WorkoutAnalyzer(),
            retriever=self.retriever,
            llm=self.llm,
        )

    def config(self, *, actor: ActorContext | None = None, call_limit: int | None = None) -> dict:
        deps = ChatbotDeps(
            llm=self.llm,
            retriever=self.retriever,
            user_data=self.user_data,
            routine_service=self.routine_service,
            conversation_provider=self.conversation,
        )
        registry = ToolRegistry(
            user_data=self.user_data,
            context=ToolExecutionContext(actor=actor or member_actor()),
            call_limit=call_limit,
        )
        return {"configurable": {"deps": deps, "tool_registry": registry}}


@pytest.fixture
def builder() -> _Builder:
    return _Builder()


@pytest.fixture
def graph():
    return build_chatbot_graph()
