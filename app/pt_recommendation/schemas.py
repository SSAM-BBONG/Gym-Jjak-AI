from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PainOnset(str, Enum):
    ACUTE = "ACUTE"
    SUBACUTE = "SUBACUTE"
    CHRONIC = "CHRONIC"


class PtCourseCandidate(BaseModel):
    """1차 필터링(부위·거리)을 통과한 후보 PT코스 한 개.
    Spring이 온보딩 기준주소+2차온보딩 조건으로 이미 걸러서 요청에 번들로 실어 보낸다
    (FastAPI는 Spring에 되물어보지 않는다).
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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "candidates": [
                    {
                        "course_id": 101,
                        "course_name": "무릎 재활 집중 코스",
                        "trainer_id": 1,
                        "trainer_name": "김트레이너",
                        "bio": "주 2회 60분, 무릎 통증 완화에 특화된 저강도 재활 프로그램입니다. "
                        "폼롤러 이완과 고관절 가동성 운동으로 시작해, 밴드 기반 대퇴사두근·둔근 강화 "
                        "운동으로 점진적으로 부하를 늘리는 12주 커리큘럼입니다. "
                        "담당 트레이너는 10년차 재활 전문가입니다.",
                    },
                    {
                        "course_id": 102,
                        "course_name": "근비대 웨이트 코스",
                        "trainer_id": 2,
                        "trainer_name": "이트레이너",
                        "bio": "주 3회 90분, 3대 운동(스쿼트·벤치프레스·데드리프트) 중심의 근비대 특화 "
                        "프로그램입니다. 초반 4주는 정확한 자세 교정에 집중하고, 이후 8주간 점진적 "
                        "과부하 방식으로 중량을 늘려갑니다. 담당 트레이너는 보디빌딩 대회 출전 경력이 있습니다.",
                    },
                    {
                        "course_id": 103,
                        "course_name": "체지방 감소 서킷 코스",
                        "trainer_id": 3,
                        "trainer_name": "박트레이너",
                        "bio": "주 3회 50분, 유산소와 근력운동을 번갈아 진행하는 서킷 트레이닝 "
                        "프로그램입니다. 관절 부담이 적은 저충격 동작 위주로 구성되어 있습니다.",
                    },
                ],
                "profile": {
                    "exercise_goal": "근비대",
                    "exercise_period": "6개월 미만",
                    "exercise_frequency": "주 3회",
                    "pt_history_summary": "PT 이력 없음 (첫 PT 등록 예정)",
                },
                "has_pain": True,
                "pain_area": "무릎",
                "pain_onset": "CHRONIC",
            }
        }
    )


class RecommendedPtCourse(BaseModel):
    course_id: int
    course_name: str
    trainer_id: int
    trainer_name: str
    reason: str = Field(min_length=1, max_length=1000)


class PtRecommendationResponse(BaseModel):
    recommendations: list[RecommendedPtCourse]
