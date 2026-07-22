"""Spring이 보유한 개인 데이터를 읽기 전용으로 조회하는 경계.

actor(요청 주체)/subject(조회 대상) id는 서버 컨텍스트에서만 정해지며, 이 계약을
구현하는 쪽이 임의로 바꾸지 않는다. Function Calling 도구(app/chatbot/tools.py, 추후
구현)가 내부적으로 이 Port를 사용한다.

HTTP(Spring 연동) 구현은 이번 단계에서 만들지 않는다. 초기 구현은
tests/fakes/user_data.py의 FakeUserDataClient만 사용하고, 실제 Spring 호출은
별도 연동 계획(app/chatbot/docs/IMPLEMENTATION_PLAN.md의 Deferred Integration Plan)에서
진행한다."""

from typing import Protocol

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


class UserDataClient(Protocol):
    async def get_subscription_status(self, user_id: int) -> SubscriptionStatus: ...

    async def get_payment_history(self, user_id: int) -> list[PaymentHistory]: ...

    async def get_pt_usage(self, user_id: int) -> PtUsageSummary: ...

    async def get_pt_history(self, user_id: int) -> list[PtHistory]: ...

    async def get_onboarding(self, user_id: int) -> OnboardingProfile | None: ...

    async def get_recent_workouts(self, user_id: int, weeks: int = 4) -> list[WorkoutDiary]: ...

    async def get_recent_inbody(
        self, user_id: int, months: int = 6, limit: int = 6
    ) -> list[InBodyRecord]: ...

    async def assert_trainer_can_access(
        self, trainer_id: int, subject_user_id: int
    ) -> TrainerSubjectAccess: ...
