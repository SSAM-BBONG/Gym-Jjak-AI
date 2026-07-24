"""로컬 개발 전용 샘플 UserDataClient. Spring 연동 전에 Swagger 등으로 챗봇 응답을
직접 확인해볼 수 있도록, 구독 활성 + 몇 가지 샘플 데이터를 항상 반환한다.

주의: 실제 서비스 데이터가 아니라 하드코딩된 샘플이다. `app.core.settings.get_settings().app_env
== "local"`일 때만 `app/chatbot/dependencies.py`에서 사용되며, 운영 환경(production)에는
절대 배포되지 않는다. Spring 연동이 완료되면 이 파일과 그 분기 코드를 통째로 삭제한다."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.exceptions import SubjectAccessDeniedError
from app.common.models import (
    InBodyRecord,
    OnboardingProfile,
    PaymentHistory,
    PtHistory,
    PtUsageSummary,
    TrainerSubjectAccess,
    WorkoutDiary,
    WorkoutSet,
)

# Swagger 예시(actor.user_id=10)와 맞춘 샘플 신원. 트레이너 담당 관계도 이 조합만 허용한다.
SAMPLE_USER_ID = 10
SAMPLE_TRAINER_ID = 20


class LocalDevUserDataClient:
    """어떤 user_id로 조회해도 같은 로컬 샘플 데이터를 반환한다."""

    async def get_payment_history(self, user_id: int) -> list[PaymentHistory]:
        return [
            PaymentHistory(
                paid_at="2026-07-01T10:00:00", amount=Decimal("50000"), item_name="1개월 이용권"
            )
        ]

    async def get_pt_usage(self, user_id: int) -> PtUsageSummary:
        return PtUsageSummary(total_sessions=10, used_sessions=3, remaining_sessions=7)

    async def get_pt_history(self, user_id: int) -> list[PtHistory]:
        return [PtHistory(trainer_name="김트레이너", started_at=date(2026, 5, 1))]

    async def get_onboarding(self, user_id: int) -> OnboardingProfile | None:
        return OnboardingProfile(
            goal="체지방 감량", preferred_exercises=["스쿼트", "런지"], experience_level="초보"
        )

    async def get_recent_workouts(self, user_id: int, weeks: int = 4) -> list[WorkoutDiary]:
        today = date.today()
        return [
            WorkoutDiary(
                diary_date=today - timedelta(days=2),
                part="CHEST",
                exercise="벤치프레스",
                sets=[
                    WorkoutSet(set_number=1, weight=Decimal("40"), reps=10),
                    WorkoutSet(set_number=2, weight=Decimal("40"), reps=8),
                ],
            ),
            WorkoutDiary(
                diary_date=today - timedelta(days=5),
                part="LEG",
                exercise="스쿼트",
                sets=[WorkoutSet(set_number=1, weight=Decimal("50"), reps=10)],
            ),
        ]

    async def get_recent_inbody(
        self, user_id: int, months: int = 6, limit: int = 6
    ) -> list[InBodyRecord]:
        today = date.today()
        return [
            InBodyRecord(
                measured_at=today - timedelta(days=60),
                weight=Decimal("70"),
                body_fat_percentage=Decimal("20"),
            ),
            InBodyRecord(
                measured_at=today, weight=Decimal("68"), body_fat_percentage=Decimal("18")
            ),
        ][:limit]

    async def assert_trainer_can_access(
        self, trainer_id: int, subject_user_id: int
    ) -> TrainerSubjectAccess:
        if trainer_id != SAMPLE_TRAINER_ID or subject_user_id != SAMPLE_USER_ID:
            raise SubjectAccessDeniedError()
        return TrainerSubjectAccess(
            trainer_id=trainer_id, subject_user_id=subject_user_id, is_allowed=True
        )
