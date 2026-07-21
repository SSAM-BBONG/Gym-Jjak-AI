"""Java(Spring) 조회 API 호출 클라이언트.
팀 원칙(ARCHITECTURE.md)대로 초기 구현은 Mock 데이터를 반환하고, Spring 연동은 마지막
단계에서 진행한다. 실제 연동 시 httpx.AsyncClient로 settings.spring_base_url +
X-Internal-Api-Key 헤더를 사용해 호출하도록 교체할 것."""

from app.pt_recommendation.schemas import PartType, TrainerCandidate


async def search_trainers(
    user_id: int,
    target_parts: list[PartType],
    distance_level: int,
) -> list[TrainerCandidate]:
    """TODO: 실제 연동 시 부위·거리 조건 기반 트레이너 검색 API 호출로 교체."""
    return [
        TrainerCandidate(
            trainer_id=1,
            trainer_name="김트레이너",
            bio="10년차 재활 전문 트레이너입니다. 무릎·허리 통증 회원 지도 경험이 많습니다.",
        ),
        TrainerCandidate(
            trainer_id=2,
            trainer_name="이트레이너",
            bio="바디빌딩 대회 입상 경력의 근비대 전문 트레이너입니다.",
        ),
    ]


async def get_onboarding_profile(user_id: int) -> dict:
    """TODO: 실제 연동 시 온보딩 조회 API 호출로 교체."""
    return {
        "exercise_goal": "근비대",
        "exercise_period": "6개월 미만",
        "exercise_frequency": "주 3회",
    }


async def get_pt_history_summary(user_id: int) -> str:
    """TODO: 실제 연동 시 PT 이력 조회 API 호출로 교체."""
    return "PT 이력 없음 (첫 PT 등록 예정)"
