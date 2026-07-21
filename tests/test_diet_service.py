from decimal import Decimal

import pytest

from app.core.exceptions import AppError
from app.diet.schemas import (
    DietAnalysisRequest,
    MealType,
    NutritionGoal,
    NutritionIntake,
    RawMealAnalysis,
)
from app.diet.service import DietService


class FakeAnalyzer:
    def __init__(self, result: RawMealAnalysis) -> None:
        self.result = result
        self.calls = 0

    async def analyze(self, image_url: str) -> RawMealAnalysis:
        self.calls += 1
        return self.result


def request(goal: NutritionGoal | None = None) -> DietAnalysisRequest:
    return DietAnalysisRequest(
        image_url="https://example-bucket.s3.ap-northeast-2.amazonaws.com/meal.jpg?signature=x",
        meal_type=MealType.LUNCH,
        meal_time="2026-07-20T12:30:00",
        nutrition_goal=goal,
        today_intake=NutritionIntake(
            kcal=780,
            carbohydrate=Decimal("90.50"),
            protein=Decimal("45.20"),
            fat=Decimal("20.00"),
        ),
    )


def analysis(food_detected: bool = True) -> RawMealAnalysis:
    return RawMealAnalysis(
        food_detected=food_detected,
        menu="닭가슴살과 현미밥" if food_detected else "",
        kcal=554 if food_detected else 0,
        carbohydrate=Decimal("67.00") if food_detected else Decimal("0"),
        protein=Decimal("51.90") if food_detected else Decimal("0"),
        fat=Decimal("7.60") if food_detected else Decimal("0"),
        confidence=Decimal("0.82") if food_detected else Decimal("0"),
        warnings=[],
    )


@pytest.mark.asyncio
async def test_goal_is_applied_to_evaluation() -> None:
    service = DietService(FakeAnalyzer(analysis()))
    response = await service.analyze(request(NutritionGoal(
        protein=120, carbohydrate=250, fat=60, kcal=2000
    )))

    assert response.menu == "닭가슴살과 현미밥"
    assert response.protein == Decimal("51.90")
    assert "칼로리는 목표까지 666kcal 남았습니다" in response.evaluation
    assert "단백질은 목표까지 22.9g 남았습니다" in response.evaluation
    assert response.warnings


@pytest.mark.asyncio
async def test_analysis_without_goal_still_succeeds() -> None:
    service = DietService(FakeAnalyzer(analysis()))
    response = await service.analyze(request(None))
    assert "등록된 일일 영양 목표가 없어" in response.evaluation


@pytest.mark.asyncio
async def test_food_not_detected_is_distinct_error() -> None:
    service = DietService(FakeAnalyzer(analysis(food_detected=False)))
    with pytest.raises(AppError) as caught:
        await service.analyze(request())
    assert caught.value.status_code == 422
    assert caught.value.code == "DIET_FOOD_NOT_DETECTED"
