"""고위험 의료 신호 차단 정책. 흉통·실신·호흡곤란 등은 LLM 호출 전에 BLOCKED로
종료하고, 일반 근육통은 제한적 안내와 전문가 권고만 덧붙인다. 의료 진단은 하지 않는다."""

from typing import Literal

from pydantic import BaseModel

# 고위험: 즉시 BLOCKED. 의학적 응급 신호로 보이는 표현만 포함한다.
_HIGH_RISK_KEYWORDS = (
    "흉통",
    "가슴 통증",
    "가슴이 아프",
    "실신",
    "기절",
    "의식을 잃",
    "의식 잃",
    "호흡곤란",
    "숨쉬기가 힘들",
    "숨쉬기 힘들",
    "숨이 차",
    "심한 어지럼",
    "마비",
)

# 일반 근육통: LIMITED로 안내하되 계속 진행한다.
_GENERAL_SORENESS_KEYWORDS = (
    "근육통",
    "뻐근",
    "알이 배겼",
    "알배김",
)

_HIGH_RISK_CAUTION = (
    "말씀하신 증상은 운동과 무관하게 응급 상황일 수 있습니다. "
    "루틴을 추천해 드릴 수 없으니 즉시 의료진의 진료를 받아 주세요."
)
_GENERAL_SORENESS_CAUTION = (
    "일반적인 근육통으로 보입니다. 통증이 지속되거나 악화되면 무리하지 말고 "
    "전문가와 상담해 주세요."
)


class SafetyAssessment(BaseModel):
    status: Literal["BLOCKED", "LIMITED", "OK"]
    caution: str | None = None


def assess_safety(message: str) -> SafetyAssessment:
    if any(keyword in message for keyword in _HIGH_RISK_KEYWORDS):
        return SafetyAssessment(status="BLOCKED", caution=_HIGH_RISK_CAUTION)
    if any(keyword in message for keyword in _GENERAL_SORENESS_KEYWORDS):
        return SafetyAssessment(status="LIMITED", caution=_GENERAL_SORENESS_CAUTION)
    return SafetyAssessment(status="OK", caution=None)
