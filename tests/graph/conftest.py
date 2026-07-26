"""그래프 테스트 공용 픽스처. 모든 의존성은 Fake로 구성하고 config["configurable"]로 주입한다."""

import asyncio
from datetime import date

import pytest

from app.chatbot.graph import build_chatbot_graph
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.state import ChatState
from app.chatbot.tools import ToolRegistry
from app.common.models import ActorContext, OnboardingProfile, PtUsageSummary, Role
from app.routine.analyzer import WorkoutAnalyzer
from app.routine.schemas import RoutineDay, RoutineExercise, RoutineResult
from app.routine.service import RoutineService
from tests.fakes.llm import FakeLLMPort
from tests.fakes.retriever import FakeRetriever
from tests.fakes.user_data import FakeUserDataClient

MEMBER_ID = 10


class FakeSpringChatbotToolClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def get_latest_inbody(self) -> dict | None:
        self.calls.append(("get_latest_inbody", None))
        return None

    async def get_workout_history(self, from_date: date, to_date: date) -> dict:
        self.calls.append(("get_workout_history", (from_date, to_date)))
        return {"from": from_date.isoformat(), "to": to_date.isoformat(), "diaries": []}


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
            onboarding_profiles={MEMBER_ID: OnboardingProfile(goal="다이어트")},
            pt_usages={MEMBER_ID: PtUsageSummary(total_sessions=10, used_sessions=3, remaining_sessions=7)},
        )
        self.retriever = FakeRetriever()
        self.llm = FakeLLMPort()
        self.tool_client = FakeSpringChatbotToolClient()
        self.routine_service = RoutineService(
            user_data=self.user_data,
            analyzer=WorkoutAnalyzer(),
            retriever=self.retriever,
            llm=self.llm,
        )

    def config(self, *, call_limit: int | None = None) -> dict:
        deps = ChatbotDeps(
            llm=self.llm,
            retriever=self.retriever,
            user_data=self.user_data,
            routine_service=self.routine_service,
        )
        registry = ToolRegistry(client=self.tool_client, call_limit=call_limit)
        return {
            "configurable": {
                "deps": deps,
                "tool_registry": registry,
                "stream_queue": asyncio.Queue(),
            }
        }


@pytest.fixture
def builder() -> _Builder:
    return _Builder()


@pytest.fixture
def graph():
    return build_chatbot_graph()
