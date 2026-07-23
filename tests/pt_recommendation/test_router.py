import pytest
from httpx import ASGITransport, AsyncClient

import app.pt_recommendation.service as service_module
from app.core.settings import settings
from app.llm.errors import LLMNetworkError
from app.llm.models import LLMResponse
from app.pt_recommendation.dependencies import get_pt_recommendation_llm_client
from main import app
from tests.fakes.llm import FakeLLMPort

_PAYLOAD = {
    "candidates": [
        {
            "course_id": 101,
            "course_name": "무릎 재활 집중 코스",
            "trainer_id": 1,
            "trainer_name": "김트레이너",
            "bio": "10년차 재활 전문 트레이너입니다.",
        }
    ],
    "profile": {
        "exercise_goal": "근비대",
        "exercise_period": "6개월 미만",
        "exercise_frequency": "주 3회",
        "pt_history_summary": "PT 이력 없음",
    },
    "has_pain": True,
    "pain_area": "무릎",
    "pain_onset": "CHRONIC",
}
_HEADERS = {"X-Internal-Api-Key": settings.internal_api_key}


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _patch_retriever(monkeypatch):
    def fake_retriever_search(query, category, top_k=3):
        return []

    monkeypatch.setattr(service_module.retriever, "search", fake_retriever_search)


def _valid_response_text() -> str:
    return (
        '[{"course_id": 101, "course_name": "무릎 재활 집중 코스", '
        '"trainer_id": 1, "trainer_name": "김트레이너", "reason": "무릎 통증에 적합합니다."}]'
    )


async def test_create_pt_recommendation_success(monkeypatch):
    _patch_retriever(monkeypatch)
    app.dependency_overrides[get_pt_recommendation_llm_client] = lambda: FakeLLMPort(
        response=LLMResponse(text=_valid_response_text())
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/pt-recommendations", json=_PAYLOAD, headers=_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"][0]["course_id"] == 101


async def test_create_pt_recommendation_rejects_missing_auth_header(monkeypatch):
    _patch_retriever(monkeypatch)
    app.dependency_overrides[get_pt_recommendation_llm_client] = lambda: FakeLLMPort()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/pt-recommendations", json=_PAYLOAD)

    assert response.status_code == 401


async def test_create_pt_recommendation_llm_network_error_returns_common_format(monkeypatch):
    _patch_retriever(monkeypatch)

    class FailingLLMPort:
        async def generate(self, messages, tools=None):
            raise LLMNetworkError("연결 실패")

    app.dependency_overrides[get_pt_recommendation_llm_client] = lambda: FailingLLMPort()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/pt-recommendations", json=_PAYLOAD, headers=_HEADERS)

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "LLM_NETWORK_ERROR"
    assert body["retryable"] is True


async def test_create_pt_recommendation_rejects_invalid_body(monkeypatch):
    _patch_retriever(monkeypatch)
    app.dependency_overrides[get_pt_recommendation_llm_client] = lambda: FakeLLMPort()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/pt-recommendations",
            json={"candidates": [], "has_pain": True},
            headers=_HEADERS,
        )

    assert response.status_code == 422


async def test_create_pt_recommendation_rejects_empty_candidates(monkeypatch):
    _patch_retriever(monkeypatch)
    app.dependency_overrides[get_pt_recommendation_llm_client] = lambda: FakeLLMPort()

    payload = {**_PAYLOAD, "candidates": []}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/pt-recommendations", json=payload, headers=_HEADERS)

    assert response.status_code == 422


async def test_create_pt_recommendation_rejects_duplicate_candidate_course_ids(monkeypatch):
    _patch_retriever(monkeypatch)
    app.dependency_overrides[get_pt_recommendation_llm_client] = lambda: FakeLLMPort()

    payload = {**_PAYLOAD, "candidates": [_PAYLOAD["candidates"][0], _PAYLOAD["candidates"][0]]}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/pt-recommendations", json=payload, headers=_HEADERS)

    assert response.status_code == 422
