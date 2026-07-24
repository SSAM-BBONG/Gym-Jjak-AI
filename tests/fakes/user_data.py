from datetime import date, timedelta

from app.common.exceptions import SubjectAccessDeniedError
from app.common.models import (
    InBodyRecord,
    OnboardingProfile,
    PaymentHistory,
    PtHistory,
    PtUsageSummary,
    TrainerSubjectAccess,
    WorkoutDiary,
)


class FakeUserDataClient:
    """UserDataClient의 가짜 구현체. 테스트 fixture로 미리 채워둔 데이터만 반환하며,
    actor/subject id를 내부에서 임의로 바꾸지 않는다."""

    def __init__(
        self,
        *,
        payment_histories: dict[int, list[PaymentHistory]] | None = None,
        pt_usages: dict[int, PtUsageSummary] | None = None,
        pt_histories: dict[int, list[PtHistory]] | None = None,
        onboarding_profiles: dict[int, OnboardingProfile] | None = None,
        workout_diaries: dict[int, list[WorkoutDiary]] | None = None,
        inbody_records: dict[int, list[InBodyRecord]] | None = None,
        trainer_subject_access: set[tuple[int, int]] | None = None,
    ) -> None:
        self._payment_histories = payment_histories or {}
        self._pt_usages = pt_usages or {}
        self._pt_histories = pt_histories or {}
        self._onboarding_profiles = onboarding_profiles or {}
        self._workout_diaries = workout_diaries or {}
        self._inbody_records = inbody_records or {}
        self._trainer_subject_access = trainer_subject_access or set()
        # (메서드명, 첫 인자) 호출 기록 — "결제/구독 조회가 호출되지 않았다" 같은
        # 부정 조건을 검증하는 테스트에서 사용한다.
        self.calls: list[tuple[str, int]] = []

    async def get_payment_history(self, user_id: int) -> list[PaymentHistory]:
        """기록이 없으면 빈 리스트를 반환한다."""
        self.calls.append(("get_payment_history", user_id))
        return self._payment_histories.get(user_id, [])

    async def get_pt_usage(self, user_id: int) -> PtUsageSummary:
        """생성자로 받은 pt_usages에서 그대로 반환한다."""
        self.calls.append(("get_pt_usage", user_id))
        return self._pt_usages[user_id]

    async def get_pt_history(self, user_id: int) -> list[PtHistory]:
        """기록이 없으면 빈 리스트를 반환한다."""
        self.calls.append(("get_pt_history", user_id))
        return self._pt_histories.get(user_id, [])

    async def get_onboarding(self, user_id: int) -> OnboardingProfile | None:
        """등록된 온보딩이 없으면 None을 반환한다."""
        self.calls.append(("get_onboarding", user_id))
        return self._onboarding_profiles.get(user_id)

    async def get_recent_workouts(self, user_id: int, weeks: int = 4) -> list[WorkoutDiary]:
        """오늘 기준 최근 weeks주 이내 운동일지만 걸러 반환한다."""
        self.calls.append(("get_recent_workouts", user_id))
        cutoff = date.today() - timedelta(weeks=weeks)
        return [
            diary
            for diary in self._workout_diaries.get(user_id, [])
            if diary.diary_date >= cutoff
        ]

    async def get_recent_inbody(
        self, user_id: int, months: int = 6, limit: int = 6
    ) -> list[InBodyRecord]:
        """최근 months개월 이내 기록을 최신순으로 정렬해 최대 limit건만 반환한다."""
        self.calls.append(("get_recent_inbody", user_id))
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
        """(trainer_id, subject_user_id) 조합이 trainer_subject_access에 없으면 거부한다."""
        self.calls.append(("assert_trainer_can_access", trainer_id))
        if (trainer_id, subject_user_id) not in self._trainer_subject_access:
            raise SubjectAccessDeniedError()
        return TrainerSubjectAccess(
            trainer_id=trainer_id, subject_user_id=subject_user_id, is_allowed=True
        )
