import app.pt_recommendation.service as service_module
from app.llm.models import LLMResponse
from app.pt_recommendation.schemas import (
    PainOnset,
    PtCourseCandidate,
    PtRecommendationRequest,
    UserProfile,
)
from app.pt_recommendation.service import PtRecommendationService
from tests.fakes.llm import FakeLLMPort

_CANDIDATE = PtCourseCandidate(
    course_id=101,
    course_name="무릎 재활 집중 코스",
    trainer_id=1,
    trainer_name="김트레이너",
    bio="10년차 재활 전문 트레이너입니다.",
)
_PROFILE = UserProfile(
    exercise_goal="근비대",
    exercise_period="6개월 미만",
    exercise_frequency="주 3회",
    pt_history_summary="PT 이력 없음",
)


def _request(pain_area: str | None = "무릎") -> PtRecommendationRequest:
    return PtRecommendationRequest(
        candidates=[_CANDIDATE],
        profile=_PROFILE,
        has_pain=True,
        pain_area=pain_area,
        pain_onset=PainOnset.CHRONIC,
    )


def _patch_retriever(monkeypatch) -> list[str]:
    """RAG 검색만 가짜로 대체한다. Spring이 후보·프로필을 이미 번들로 보내주는 설계라
    service.py는 더 이상 Java 조회 클라이언트를 호출하지 않는다."""
    search_calls: list[str] = []

    def fake_retriever_search(query, category, top_k=3):
        search_calls.append(category)
        return []

    monkeypatch.setattr(service_module.retriever, "search", fake_retriever_search)
    return search_calls


def _valid_response_text() -> str:
    return (
        '[{"course_id": 101, "course_name": "무릎 재활 집중 코스", '
        '"trainer_id": 1, "trainer_name": "김트레이너", "reason": "무릎 통증에 적합합니다."}]'
    )


async def test_recommend_returns_response_built_from_candidates(monkeypatch):
    _patch_retriever(monkeypatch)
    service = PtRecommendationService(llm=FakeLLMPort(response=LLMResponse(text=_valid_response_text())))

    response = await service.recommend(_request())

    assert len(response.recommendations) == 1
    assert response.recommendations[0].course_id == 101


async def test_recommend_skips_injury_search_when_pain_area_is_none(monkeypatch):
    search_calls = _patch_retriever(monkeypatch)
    service = PtRecommendationService(llm=FakeLLMPort(response=LLMResponse(text=_valid_response_text())))

    await service.recommend(_request(pain_area=None))

    assert "training_guide" in search_calls
    assert "injury_guide" not in search_calls


async def test_recommend_searches_injury_guide_when_pain_area_present(monkeypatch):
    search_calls = _patch_retriever(monkeypatch)
    service = PtRecommendationService(llm=FakeLLMPort(response=LLMResponse(text=_valid_response_text())))

    await service.recommend(_request(pain_area="무릎"))

    assert "training_guide" in search_calls
    assert "injury_guide" in search_calls
