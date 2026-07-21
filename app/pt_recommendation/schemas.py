from enum import Enum

from pydantic import BaseModel, Field, model_validator


class PartType(str, Enum):
    """Gym-Jjak(Spring) PtCourse.PartType과 동일한 값을 유지한다."""

    CHEST = "CHEST"
    BACK = "BACK"
    SHOULDER = "SHOULDER"
    ARM = "ARM"
    ABS = "ABS"
    CORE = "CORE"
    LEG = "LEG"
    GLUTE = "GLUTE"
    FULL_BODY = "FULL_BODY"


class PainOnset(str, Enum):
    ACUTE = "ACUTE"
    SUBACUTE = "SUBACUTE"
    CHRONIC = "CHRONIC"


class PtRecommendationRequest(BaseModel):
    user_id: int
    target_parts: list[PartType] = Field(min_length=1)
    distance_level: int = Field(ge=1, le=5)
    has_pain: bool
    pain_area: str | None = None
    pain_onset: PainOnset | None = None

    @model_validator(mode="after")
    def check_pain_fields(self) -> "PtRecommendationRequest":
        if self.has_pain and self.pain_onset is None:
            raise ValueError("has_pain=true인 경우 pain_onset은 필수입니다.")
        if not self.has_pain and (self.pain_area is not None or self.pain_onset is not None):
            raise ValueError("has_pain=false인 경우 pain_area/pain_onset은 비워야 합니다.")
        return self


class RecommendedPtCourse(BaseModel):
    course_id: int
    course_name: str
    trainer_id: int
    trainer_name: str
    reason: str = Field(min_length=1, max_length=1000)


class PtRecommendationResponse(BaseModel):
    recommendations: list[RecommendedPtCourse]


class PtCourseCandidate(BaseModel):
    """1차 필터링을 통과한 후보 PT코스 한 개. user_data_client가 Java에서 조회해서 채운다.
    부위(PartType)는 트레이너가 아니라 PtCourse에 달린 값이라, 필터링/추천 단위를
    트레이너가 아닌 PT코스로 잡는다 — 한 트레이너가 여러 코스(부위)를 가질 수 있음."""

    course_id: int
    course_name: str
    trainer_id: int
    trainer_name: str
    bio: str


class UserProfile(BaseModel):
    """온보딩+PT이력을 종합한, 2차 AI 프롬프트에 넣을 회원 프로필. user_data_client가 채운다."""

    exercise_goal: str
    exercise_period: str
    exercise_frequency: str
    pt_history_summary: str
