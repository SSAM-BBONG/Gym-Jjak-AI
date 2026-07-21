from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.dependencies import get_diet_service
from app.diet.schemas import DietAnalysisResponse
from main import app


class FakeDietService:
    async def analyze(self, request):
        return DietAnalysisResponse(
            menu="닭가슴살과 현미밥",
            kcal=554,
            carbohydrate=Decimal("67.00"),
            protein=Decimal("51.90"),
            fat=Decimal("7.60"),
            evaluation="단백질은 목표까지 22.9g 남았습니다.",
            confidence=Decimal("0.82"),
            warnings=["추정값입니다."],
        )


def spring_request() -> dict:
    return {
        "image_url": "https://example-bucket.s3.ap-northeast-2.amazonaws.com/meal.jpg?signature=x",
        "meal_type": "LUNCH",
        "meal_time": "2026-07-20T12:30:00",
        "nutrition_goal": {
            "protein": 120,
            "carbohydrate": 250,
            "fat": 60,
            "kcal": 2000,
        },
        "today_intake": {
            "kcal": 780,
            "carbohydrate": 90.50,
            "protein": 45.20,
            "fat": 20.00,
        },
    }


def test_spring_contract_request_and_response() -> None:
    app.dependency_overrides[get_diet_service] = lambda: FakeDietService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/meals/analyze",
                headers={"X-Internal-Api-Key": "local-development-only"},
                json=spring_request(),
            )
        assert response.status_code == 200
        assert response.json() == {
            "menu": "닭가슴살과 현미밥",
            "kcal": 554,
            "carbohydrate": 67.0,
            "protein": 51.9,
            "fat": 7.6,
            "evaluation": "단백질은 목표까지 22.9g 남았습니다.",
            "confidence": 0.82,
            "warnings": ["추정값입니다."],
        }
        assert response.headers["X-Request-ID"]
    finally:
        app.dependency_overrides.clear()


def test_internal_api_key_is_required() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/meals/analyze", json=spring_request())
    assert response.status_code == 401
    assert response.json()["code"] == "INTERNAL_AUTH_FAILED"


def test_validation_error_has_contract_error_code() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/meals/analyze",
            headers={"X-Internal-Api-Key": "local-development-only"},
            json={**spring_request(), "meal_type": "BRUNCH"},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"
