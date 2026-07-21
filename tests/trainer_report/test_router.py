import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_llm_client
from app.llm.errors import LLMNetworkError
from app.llm.models import LLMResponse
from main import app
from tests.fakes.llm import FakeLLMPort

_PAYLOAD = {
    "trainer_id": 1,
    "market_trends": {
        "popular_body_parts": [{"body_part": "하체", "percentage": 35.2}],
        "price_distribution": [
            {"price_range": "15~20만원", "min_price": 150000, "max_price": 200000, "percentage": 40.0}
        ],
        "price_per_session_distribution": [
            {"price_range": "2~2.5만원", "min_price": 20000, "max_price": 25000, "percentage": 40.0}
        ],
        "session_count_distribution": [{"session_count": 8, "percentage": 40.0}],
        "location_distribution": [{"region": "강남구", "percentage": 25.0}],
    },
    "my_pt_courses": [
        {"name": "8회 패키지", "price": 200000, "session_count": 8, "body_part": "전신"}
    ],
}


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


async def test_create_trainer_report_success():
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMPort(
        response=LLMResponse(text="생성된 리포트")
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/trainer-report", json=_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"report": "생성된 리포트"}


async def test_create_trainer_report_llm_network_error_returns_common_error_format():
    class FailingLLMPort:
        async def generate(self, messages, tools=None):
            raise LLMNetworkError("연결 실패")

    app.dependency_overrides[get_llm_client] = lambda: FailingLLMPort()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/trainer-report", json=_PAYLOAD)

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "LLM_NETWORK_ERROR"
    assert body["retryable"] is True
    assert "request_id" in body


async def test_create_trainer_report_rejects_invalid_body():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/trainer-report", json={"trainer_id": 1})

    assert response.status_code == 422
