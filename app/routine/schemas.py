"""회원/트레이너 공용 구조화 루틴 응답 모델."""

from typing import Literal

from pydantic import BaseModel, Field

from app.common.models import ActorContext


class TrainerRoutineRequest(BaseModel):
    """트레이너 전용 상세 루틴 분석 요청. 채팅 세션을 만들지 않는 1회성 API용이다."""

    actor: ActorContext
    subject_user_id: int


class SourceReference(BaseModel):
    """루틴 근거로 사용한 문서 출처 1건."""

    source: str
    title: str
    category: str


class RoutineRequest(BaseModel):
    """회원 루틴 추천 요청. 자유 텍스트 메시지 하나로 안전검사와 프롬프트에 모두 사용한다."""

    message: str


class RoutineExercise(BaseModel):
    """루틴 하루 중 운동 종목 1개."""

    name: str
    part: str
    sets: int = Field(ge=1, le=10)
    reps: str
    intensity: str
    rest_seconds: int = Field(ge=15, le=600)
    rationale: str


class RoutineDay(BaseModel):
    """루틴의 하루 구성(웜업/운동/쿨다운)."""

    day_label: str
    goal: str
    warm_up: list[str]
    exercises: list[RoutineExercise]
    cool_down: list[str]


class RoutineResult(BaseModel):
    """루틴 추천 최종 결과. status로 완전/부분/차단 여부를 표시한다."""

    status: Literal["COMPLETE", "LIMITED", "BLOCKED"]
    title: str
    summary: str
    days: list[RoutineDay]
    cautions: list[str]
    missing_data: list[str]
    sources: list[SourceReference]
