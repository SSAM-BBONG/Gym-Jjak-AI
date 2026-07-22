"""챗봇이 Spring에서 읽어오는 개인 데이터의 provider 독립 모델.
금액과 신체 수치는 Decimal, 날짜는 date/datetime을 사용한다."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class Role(StrEnum):
    USER = "USER"
    TRAINER = "TRAINER"


class ActorContext(BaseModel):
    """요청을 보낸 주체. Function Calling 도구는 이 값을 서버 컨텍스트로 고정해 사용하고
    모델이 만들거나 바꾸지 못하게 한다."""

    user_id: int
    role: Role


class SubscriptionStatus(BaseModel):
    is_active: bool
    plan_name: str | None = None
    expires_at: datetime | None = None


class OnboardingProfile(BaseModel):
    goal: str | None = None
    preferred_exercises: list[str] = []
    experience_level: str | None = None


class WorkoutSet(BaseModel):
    set_number: int
    weight: Decimal
    reps: int


class WorkoutDiary(BaseModel):
    diary_date: date
    part: str
    exercise: str
    sets: list[WorkoutSet]


class InBodyRecord(BaseModel):
    measured_at: date
    weight: Decimal
    body_fat_percentage: Decimal | None = None
    skeletal_muscle_mass: Decimal | None = None


class PaymentHistory(BaseModel):
    paid_at: datetime
    amount: Decimal
    item_name: str


class PtUsageSummary(BaseModel):
    total_sessions: int
    used_sessions: int
    remaining_sessions: int


class PtHistory(BaseModel):
    trainer_name: str
    started_at: date
    ended_at: date | None = None


class TrainerSubjectAccess(BaseModel):
    trainer_id: int
    subject_user_id: int
    is_allowed: bool
