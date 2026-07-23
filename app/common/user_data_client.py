"""Spring이 보유한 개인 데이터를 읽기 전용으로 조회하는 경계.

actor(요청 주체)/subject(조회 대상) id는 서버 컨텍스트에서만 정해지며, 이 계약을
구현하는 쪽이 임의로 바꾸지 않는다. Function Calling 도구(app/chatbot/tools.py, 추후
구현)가 내부적으로 이 Port를 사용한다.

HTTP(Spring 연동) 구현은 이번 단계에서 만들지 않는다. 초기 구현은
tests/fakes/user_data.py의 FakeUserDataClient만 사용하고, 실제 Spring 호출은
별도 연동 계획(app/chatbot/docs/IMPLEMENTATION_PLAN.md의 Deferred Integration Plan)에서
진행한다."""

from typing import Protocol

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


class UserDataClient(Protocol):
    """Spring이 가진 개인 데이터를 읽기 전용으로 조회하는 8개 메서드 계약."""

    async def get_subscription_status(self, user_id: int) -> SubscriptionStatus:
        """AI 구독 활성 여부를 조회한다."""
        ...

    async def get_payment_history(self, user_id: int) -> list[PaymentHistory]:
        """결제 내역 전체를 조회한다."""
        ...

    async def get_pt_usage(self, user_id: int) -> PtUsageSummary:
        """PT 세션 사용 현황을 조회한다."""
        ...

    async def get_pt_history(self, user_id: int) -> list[PtHistory]:
        """PT 수강 이력을 조회한다."""
        ...

    async def get_onboarding(self, user_id: int) -> OnboardingProfile | None:
        """온보딩 프로필을 조회한다. 등록 전이면 None."""
        ...

    async def get_recent_workouts(self, user_id: int, weeks: int = 4) -> list[WorkoutDiary]:
        """최근 N주 운동일지를 조회한다."""
        ...

    async def get_recent_inbody(
        self, user_id: int, months: int = 6, limit: int = 6
    ) -> list[InBodyRecord]:
        """최근 N개월 인바디 기록을 최신순 최대 limit건 조회한다."""
        ...

    async def assert_trainer_can_access(
        self, trainer_id: int, subject_user_id: int
    ) -> TrainerSubjectAccess:
        """트레이너가 해당 회원을 담당하는지 검증하고, 아니면 SubjectAccessDeniedError를 던진다."""
        ...


class InMemoryUserDataClient:
    """Spring HTTP 연동 전 임시 구현체(Deferred Integration Plan 전까지 사용).

    실제 데이터가 없으므로 항상 "값 없음"에 해당하는 결과만 반환한다 — 구독은
    비활성으로 응답해 챗봇이 CHATBOT_SUBSCRIPTION_REQUIRED로 정직하게 안내하게 하고,
    트레이너 접근은 항상 거부한다. 실제 서비스 동작을 위해서는 Spring 조회 API를 붙인
    HTTP 구현체로 교체해야 한다."""

    async def get_subscription_status(self, user_id: int) -> SubscriptionStatus:
        return SubscriptionStatus(is_active=False)

    async def get_payment_history(self, user_id: int) -> list[PaymentHistory]:
        return []

    async def get_pt_usage(self, user_id: int) -> PtUsageSummary:
        return PtUsageSummary(total_sessions=0, used_sessions=0, remaining_sessions=0)

    async def get_pt_history(self, user_id: int) -> list[PtHistory]:
        return []

    async def get_onboarding(self, user_id: int) -> OnboardingProfile | None:
        return None

    async def get_recent_workouts(self, user_id: int, weeks: int = 4) -> list[WorkoutDiary]:
        return []

    async def get_recent_inbody(
        self, user_id: int, months: int = 6, limit: int = 6
    ) -> list[InBodyRecord]:
        return []

    async def assert_trainer_can_access(
        self, trainer_id: int, subject_user_id: int
    ) -> TrainerSubjectAccess:
        raise SubjectAccessDeniedError()
