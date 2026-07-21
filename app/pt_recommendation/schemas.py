from enum import Enum

from pydantic import BaseModel, Field, model_validator


class PainOnset(str, Enum):
    ACUTE = "ACUTE"
    SUBACUTE = "SUBACUTE"
    CHRONIC = "CHRONIC"


class PtCourseCandidate(BaseModel):
    """1차 필터링(부위·거리)을 통과한 후보 PT코스 한 개.
    Spring이 온보딩 기준주소+2차온보딩 조건으로 이미 걸러서 요청에 번들로 실어 보낸다
    (diet/trainer_report와 동일하게, FastAPI는 Spring에 되물어보지 않는다).
    bio는 PtCourse.description(코스 설명)이다."""

    course_id: int
    course_name: str
    trainer_id: int
    trainer_name: str
    bio: str


class UserProfile(BaseModel):
    """온보딩+PT이력을 종합한 회원 프로필. Spring이 조회해서 채워 보낸다."""

    exercise_goal: str
    exercise_period: str
    exercise_frequency: str
    pt_history_summary: str


class PtRecommendationRequest(BaseModel):
    candidates: list[PtCourseCandidate] = Field(min_length=1)
    profile: UserProfile
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
