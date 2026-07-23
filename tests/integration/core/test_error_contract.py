"""공통 오류 계약 검증: AppError/검증 오류/LLMError/500이 모두
같은 request_id를 응답 헤더 X-Request-ID와 본문 request_id에 일관되게 담는지 확인한다.
main.py와 core/exceptions.py에 흩어져 있던 핸들러를 error_handlers.py로 통합하면서,
LLMError 핸들러가 미들웨어의 request_id 대신 새 uuid를 생성하던 버그를 함께 검증한다."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_diet_service, get_llm_client
from app.llm.errors import LLMInvalidResponseError, LLMNetworkError
from main import app


def _assert_common_error_contract(response, expected_status: int, expected_code: str) -> None:
    assert response.status_code == expected_status
    body = response.json()
    assert body["code"] == expected_code
    assert body["request_id"]
    # 오류 계약의 핵심: 본문 request_id와 응답 헤더 X-Request-ID가 항상 일치해야
    # Spring이 로그를 추적할 수 있다.
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "retryable" in body


def _diet_payload() -> dict:
    return {
        "image_url": "https://example-bucket.s3.ap-northeast-2.amazonaws.com/meal.jpg?signature=x",
        "meal_type": "LUNCH",
        "meal_time": "2026-07-20T12:30:00",
        "nutrition_goal": None,
        "today_intake": {"kcal": 0, "carbohydrate": 0, "protein": 0, "fat": 0},
    }


async def test_app_error_contract() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/meals/analyze", json=_diet_payload())
    _assert_common_error_contract(response, 401, "INTERNAL_AUTH_FAILED")


async def test_validation_error_contract() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/meals/analyze",
            headers={"X-Internal-Api-Key": "local-development-only"},
            json={**_diet_payload(), "meal_type": "BRUNCH"},
        )
    _assert_common_error_contract(response, 422, "REQUEST_VALIDATION_ERROR")


async def test_llm_error_contract() -> None:
    class FailingLLMPort:
        async def generate(self, messages, tools=None):
            raise LLMNetworkError("연결 실패")

    app.dependency_overrides[get_llm_client] = lambda: FailingLLMPort()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/trainer-report",
                json={
                    "trainer_id": 1,
                    "market_trends": {
                        "popular_body_parts": [],
                        "price_distribution": [],
                        "price_per_session_distribution": [],
                        "session_count_distribution": [],
                        "location_distribution": [],
                    },
                    "my_pt_courses": [],
                },
            )
    finally:
        app.dependency_overrides.clear()
    _assert_common_error_contract(response, 503, "LLM_NETWORK_ERROR")
    assert response.json()["retryable"] is True


async def test_llm_invalid_response_is_not_retryable() -> None:
    """실제로 겪은 버그: 요청 자체가 잘못된 경우(예: thought_signature 누락으로 인한
    400 INVALID_ARGUMENT)까지 retryable=True로 나가면 사용자가 똑같이 실패할 재시도를
    반복하게 된다. LLM_INVALID_RESPONSE는 항상 retryable=False여야 한다."""

    class FailingLLMPort:
        async def generate(self, messages, tools=None):
            raise LLMInvalidResponseError("thought_signature 누락")

    app.dependency_overrides[get_llm_client] = lambda: FailingLLMPort()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/trainer-report",
                json={
                    "trainer_id": 1,
                    "market_trends": {
                        "popular_body_parts": [],
                        "price_distribution": [],
                        "price_per_session_distribution": [],
                        "session_count_distribution": [],
                        "location_distribution": [],
                    },
                    "my_pt_courses": [],
                },
            )
    finally:
        app.dependency_overrides.clear()
    _assert_common_error_contract(response, 502, "LLM_INVALID_RESPONSE")
    assert response.json()["retryable"] is False


@pytest.fixture
def _temporary_500_route():
    """예상 못한 500 오류 경로만 검증하기 위한 테스트 전용 라우트.
    영구 라우트를 추가하지 않고 테스트 동안만 붙였다가 제거한다."""

    async def _raise() -> None:
        raise RuntimeError("boom")

    app.add_api_route("/_test/unexpected-error", _raise, methods=["GET"])
    yield
    app.router.routes = [
        route for route in app.router.routes if getattr(route, "path", None) != "/_test/unexpected-error"
    ]


async def test_unexpected_error_contract(_temporary_500_route) -> None:
    # ServerErrorMiddleware는 500 응답을 보낸 뒤 예외를 재-raise하는 것이 정상 동작이라,
    # ASGITransport가 그대로 전파하지 않도록 raise_app_exceptions=False로 응답만 확인한다.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/_test/unexpected-error")
    _assert_common_error_contract(response, 500, "INTERNAL_SERVER_ERROR")
