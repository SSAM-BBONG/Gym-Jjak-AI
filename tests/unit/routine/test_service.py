from datetime import date

import pytest

from app.common.exceptions import SubjectAccessDeniedError
from app.common.models import ActorContext, OnboardingProfile, Role, SubscriptionStatus
from app.rag.models import RetrievedDocument
from app.routine.analyzer import WorkoutAnalyzer
from app.routine.exceptions import ActorRoleNotAllowedError, SubscriptionRequiredError
from app.routine.schemas import (
    RoutineDay,
    RoutineExercise,
    RoutineRequest,
    RoutineResult,
)
from app.routine.service import RoutineService
from tests.fakes.llm import FakeLLMPort
from tests.fakes.retriever import FakeRetriever
from tests.fakes.user_data import FakeUserDataClient
from tests.fixtures.user_data import inbody_record, workout_diary, workout_set

_MEMBER_ID = 10
_TRAINER_ID = 20


def member_actor() -> ActorContext:
    return ActorContext(user_id=_MEMBER_ID, role=Role.USER)


def trainer_actor() -> ActorContext:
    return ActorContext(user_id=_TRAINER_ID, role=Role.TRAINER)


def routine_request(message: str = "주 3회 전신 루틴 추천해줘") -> RoutineRequest:
    return RoutineRequest(message=message)


def sample_routine_result(status: str = "COMPLETE") -> RoutineResult:
    return RoutineResult(
        status=status,
        title="테스트 루틴",
        summary="요약",
        days=[
            RoutineDay(
                day_label="Day 1",
                goal="전신",
                warm_up=["스트레칭"],
                exercises=[
                    RoutineExercise(
                        name="스쿼트",
                        part="LEG",
                        sets=3,
                        reps="10회",
                        intensity="중강도",
                        rest_seconds=60,
                        rationale="기초 운동",
                    )
                ],
                cool_down=["스트레칭"],
            )
        ],
        cautions=[],
        missing_data=[],
        sources=[],
    )


def build_routine_service(
    *,
    with_workouts: bool = True,
    with_inbody: bool = True,
    subscription_active: bool = True,
    trainer_access: set[tuple[int, int]] | None = None,
):
    today = date.today()
    workouts = (
        {_MEMBER_ID: [workout_diary(diary_date=today, part="CHEST", exercise="벤치프레스", sets=[workout_set(1, 40, 10)])]}
        if with_workouts
        else {}
    )
    inbody = (
        {_MEMBER_ID: [inbody_record(measured_at=today, weight=70)]}
        if with_inbody
        else {}
    )
    user_data = FakeUserDataClient(
        subscriptions={_MEMBER_ID: SubscriptionStatus(is_active=subscription_active)},
        onboarding_profiles={_MEMBER_ID: OnboardingProfile(goal="다이어트", experience_level="초보")},
        workout_diaries=workouts,
        inbody_records=inbody,
        trainer_subject_access=trainer_access if trainer_access is not None else {(_TRAINER_ID, _MEMBER_ID)},
    )
    retriever = FakeRetriever(
        documents=[
            RetrievedDocument(
                document_id="routine-beginner-fullbody-001::0",
                content="초보자 전신 루틴 설명",
                score=0.9,
                source="data/documents/routine/beginner-fullbody.md",
                title="초보자 전신 루틴",
                category="routine",
            )
        ]
    )
    llm = FakeLLMPort(structured_response=sample_routine_result())
    service = RoutineService(
        user_data=user_data, analyzer=WorkoutAnalyzer(), retriever=retriever, llm=llm
    )
    return service, user_data, retriever, llm


async def test_member_routine_uses_profile_workout_inbody_and_rag() -> None:
    service, _, retriever, llm = build_routine_service()

    result = await service.recommend_for_member(actor=member_actor(), request=routine_request())

    assert result.status == "COMPLETE"
    assert llm.structured_call_count == 1
    assert retriever.queries[0].category == "routine"
    assert result.sources


async def test_missing_workout_and_inbody_returns_limited_result() -> None:
    service, _, _, _ = build_routine_service(with_workouts=False, with_inbody=False)

    result = await service.recommend_for_member(actor=member_actor(), request=routine_request())

    assert result.status == "LIMITED"
    assert set(result.missing_data) == {"workout_diaries", "inbody"}


async def test_high_risk_message_blocks_before_llm_call() -> None:
    service, _, _, llm = build_routine_service()

    result = await service.recommend_for_member(
        actor=member_actor(), request=routine_request("운동하다 흉통이 있는데 루틴 추천해줘")
    )

    assert result.status == "BLOCKED"
    assert llm.structured_call_count == 0


async def test_inactive_subscription_is_rejected() -> None:
    service, _, _, llm = build_routine_service(subscription_active=False)

    with pytest.raises(SubscriptionRequiredError):
        await service.recommend_for_member(actor=member_actor(), request=routine_request())

    assert llm.structured_call_count == 0


async def test_trainer_role_cannot_use_member_path() -> None:
    service, _, _, _ = build_routine_service()

    with pytest.raises(ActorRoleNotAllowedError):
        await service.recommend_for_member(actor=trainer_actor(), request=routine_request())


async def test_trainer_routine_checks_relationship_before_anything_else() -> None:
    service, user_data, _, llm = build_routine_service(trainer_access=set())

    with pytest.raises(SubjectAccessDeniedError):
        await service.recommend_for_trainer(actor=trainer_actor(), subject_user_id=_MEMBER_ID)

    assert llm.structured_call_count == 0
    assert not any(call[0] == "get_subscription_status" for call in user_data.calls)


async def test_trainer_routine_does_not_query_subscription_or_payment() -> None:
    service, user_data, _, llm = build_routine_service()

    result = await service.recommend_for_trainer(actor=trainer_actor(), subject_user_id=_MEMBER_ID)

    assert result.status == "COMPLETE"
    assert not any(call[0] == "get_subscription_status" for call in user_data.calls)
    assert not any(call[0] == "get_payment_history" for call in user_data.calls)


async def test_trainer_prompt_is_more_detailed_than_member_prompt() -> None:
    service, _, _, llm = build_routine_service()

    await service.recommend_for_trainer(actor=trainer_actor(), subject_user_id=_MEMBER_ID)
    trainer_prompt = llm.structured_prompts[-1]

    llm.structured_prompts.clear()
    await service.recommend_for_member(actor=member_actor(), request=routine_request())
    member_prompt = llm.structured_prompts[-1]

    assert "트레이너용 상세 분석" in trainer_prompt
    assert "트레이너용 상세 분석" not in member_prompt


async def test_member_with_only_user_role_cannot_use_trainer_path() -> None:
    service, _, _, _ = build_routine_service()

    with pytest.raises(ActorRoleNotAllowedError):
        await service.recommend_for_trainer(actor=member_actor(), subject_user_id=_MEMBER_ID)
