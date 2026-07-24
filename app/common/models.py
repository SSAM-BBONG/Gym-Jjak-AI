"""챗봇이 Spring에서 읽어오는 개인 데이터의 provider 독립 모델.
금액과 신체 수치는 Decimal, 날짜는 date/datetime을 사용한다."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class Role(StrEnum):
    """요청 주체의 역할. 회원용/트레이너용 흐름 분기에 사용한다."""

    USER = "USER"
    TRAINER = "TRAINER"


class ActorContext(BaseModel):
    """요청을 보낸 주체. Function Calling 도구는 이 값을 서버 컨텍스트로 고정해 사용하고
    모델이 만들거나 바꾸지 못하게 한다."""

    user_id: int
    role: Role


class OnboardingProfile(BaseModel):
    """온보딩 시 등록한 목표·선호 운동·숙련도."""

    goal: str | None = None
    preferred_exercises: list[str] = []
    experience_level: str | None = None


class WorkoutSet(BaseModel):
    """운동일지의 세트 1개(중량·횟수)."""

    set_number: int
    weight: Decimal
    reps: int


class WorkoutDiary(BaseModel):
    """하루치 운동일지 1건(부위·종목·세트 목록)."""

    diary_date: date
    part: str
    exercise: str
    sets: list[WorkoutSet]


class InBodyRecord(BaseModel):
    """인바디 측정 기록 1건."""

    measured_at: date
    weight: Decimal
    body_fat_percentage: Decimal | None = None
    skeletal_muscle_mass: Decimal | None = None


class PaymentHistory(BaseModel):
    """결제 내역 1건."""

    paid_at: datetime
    amount: Decimal
    item_name: str


class PtUsageSummary(BaseModel):
    """PT 세션 사용 현황 요약(총/사용/잔여 횟수)."""

    total_sessions: int
    used_sessions: int
    remaining_sessions: int


class PtHistory(BaseModel):
    """PT 수강 이력 1건."""

    trainer_name: str
    started_at: date
    ended_at: date | None = None


class TrainerSubjectAccess(BaseModel):
    """트레이너가 특정 회원(subject)을 조회할 수 있는지에 대한 판정 결과."""

    trainer_id: int
    subject_user_id: int
    is_allowed: bool
