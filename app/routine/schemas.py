"""회원/트레이너 공용 구조화 루틴 응답 모델."""

from typing import Literal

from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    source: str
    title: str
    category: str


class RoutineExercise(BaseModel):
    name: str
    part: str
    sets: int = Field(ge=1, le=10)
    reps: str
    intensity: str
    rest_seconds: int = Field(ge=15, le=600)
    rationale: str


class RoutineDay(BaseModel):
    day_label: str
    goal: str
    warm_up: list[str]
    exercises: list[RoutineExercise]
    cool_down: list[str]


class RoutineResult(BaseModel):
    status: Literal["COMPLETE", "LIMITED", "BLOCKED"]
    title: str
    summary: str
    days: list[RoutineDay]
    cautions: list[str]
    missing_data: list[str]
    sources: list[SourceReference]
