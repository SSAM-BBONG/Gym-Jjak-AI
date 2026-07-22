from datetime import date, timedelta

from app.common.exceptions import SubjectAccessDeniedError
from app.common.models import (
    InBodyRecord,
    OnboardingProfile,
    PaymentHistory,
    PtHistory,
    PtUsageSummary,
    SubscriptionStatus,
    TrainerSubjectAccess,
    WorkoutDiary,
)


class FakeUserDataClient:
    """UserDataClient의 가짜 구현체. 테스트 fixture로 미리 채워둔 데이터만 반환하며,
    actor/subject id를 내부에서 임의로 바꾸지 않는다."""

    def __init__(
        self,
        *,
        subscriptions: dict[int, SubscriptionStatus] | None = None,
        payment_histories: dict[int, list[PaymentHistory]] | None = None,
        pt_usages: dict[int, PtUsageSummary] | None = None,
        pt_histories: dict[int, list[PtHistory]] | None = None,
        onboarding_profiles: dict[int, OnboardingProfile] | None = None,
        workout_diaries: dict[int, list[WorkoutDiary]] | None = None,
        inbody_records: dict[int, list[InBodyRecord]] | None = None,
        trainer_subject_access: set[tuple[int, int]] | None = None,
    ) -> None:
        self._subscriptions = subscriptions or {}
        self._payment_histories = payment_histories or {}
        self._pt_usages = pt_usages or {}
        self._pt_histories = pt_histories or {}
        self._onboarding_profiles = onboarding_profiles or {}
        self._workout_diaries = workout_diaries or {}
        self._inbody_records = inbody_records or {}
        self._trainer_subject_access = trainer_subject_access or set()

    async def get_subscription_status(self, user_id: int) -> SubscriptionStatus:
        return self._subscriptions[user_id]

    async def get_payment_history(self, user_id: int) -> list[PaymentHistory]:
        return self._payment_histories.get(user_id, [])

    async def get_pt_usage(self, user_id: int) -> PtUsageSummary:
        return self._pt_usages[user_id]

    async def get_pt_history(self, user_id: int) -> list[PtHistory]:
        return self._pt_histories.get(user_id, [])

    async def get_onboarding(self, user_id: int) -> OnboardingProfile | None:
        return self._onboarding_profiles.get(user_id)

    async def get_recent_workouts(self, user_id: int, weeks: int = 4) -> list[WorkoutDiary]:
        cutoff = date.today() - timedelta(weeks=weeks)
        return [
            diary
            for diary in self._workout_diaries.get(user_id, [])
            if diary.diary_date >= cutoff
        ]

    async def get_recent_inbody(
        self, user_id: int, months: int = 6, limit: int = 6
    ) -> list[InBodyRecord]:
        cutoff = date.today() - timedelta(days=months * 30)
        records = [
            record
            for record in self._inbody_records.get(user_id, [])
            if record.measured_at >= cutoff
        ]
        records.sort(key=lambda record: record.measured_at, reverse=True)
        return records[:limit]

    async def assert_trainer_can_access(
        self, trainer_id: int, subject_user_id: int
    ) -> TrainerSubjectAccess:
        if (trainer_id, subject_user_id) not in self._trainer_subject_access:
            raise SubjectAccessDeniedError()
        return TrainerSubjectAccess(
            trainer_id=trainer_id, subject_user_id=subject_user_id, is_allowed=True
        )
