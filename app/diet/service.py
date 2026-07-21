from decimal import Decimal, ROUND_HALF_UP

from app.diet.analyzer import MealImageAnalyzer
from app.diet.errors import food_not_detected, invalid_analysis_result
from app.diet.schemas import (
    DietAnalysisRequest,
    DietAnalysisResponse,
    NutritionGoal,
    NutritionIntake,
    RawMealAnalysis,
)


TWO_PLACES = Decimal("0.01")


class DietService:
    def __init__(self, analyzer: MealImageAnalyzer) -> None:
        self._analyzer = analyzer

    async def analyze(self, request: DietAnalysisRequest) -> DietAnalysisResponse:
        raw = await self._analyzer.analyze(str(request.image_url))
        if not raw.food_detected:
            raise food_not_detected()
        if not raw.menu:
            raise invalid_analysis_result()

        meal = self._normalize(raw)
        after_meal = self._sum_intake(request.today_intake, meal)
        evaluation = self._build_evaluation(request.nutrition_goal, after_meal)
        warnings = list(dict.fromkeys([
            *meal.warnings,
            "사진을 기반으로 추정한 영양성분이므로 실제 값과 차이가 날 수 있습니다.",
        ]))[:10]
        return DietAnalysisResponse(
            menu=meal.menu,
            kcal=meal.kcal,
            carbohydrate=meal.carbohydrate,
            protein=meal.protein,
            fat=meal.fat,
            evaluation=evaluation,
            confidence=meal.confidence,
            warnings=warnings,
        )

    def _normalize(self, raw: RawMealAnalysis) -> RawMealAnalysis:
        return raw.model_copy(update={
            "carbohydrate": raw.carbohydrate.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            "protein": raw.protein.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            "fat": raw.fat.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
        })

    def _sum_intake(self, current: NutritionIntake, meal: RawMealAnalysis) -> NutritionIntake:
        return NutritionIntake(
            kcal=current.kcal + meal.kcal,
            carbohydrate=current.carbohydrate + meal.carbohydrate,
            protein=current.protein + meal.protein,
            fat=current.fat + meal.fat,
        )

    def _build_evaluation(self, goal: NutritionGoal | None, total: NutritionIntake) -> str:
        if goal is None:
            return "등록된 일일 영양 목표가 없어 이번 식사의 추정 영양성분만 안내합니다."

        values = [
            ("칼로리", "는", Decimal(total.kcal), Decimal(goal.kcal), "kcal"),
            ("탄수화물", "은", total.carbohydrate, Decimal(goal.carbohydrate), "g"),
            ("단백질", "은", total.protein, Decimal(goal.protein), "g"),
            ("지방", "은", total.fat, Decimal(goal.fat), "g"),
        ]
        messages: list[str] = []
        for label, particle, consumed, target, unit in values:
            if target == 0:
                if consumed > 0:
                    messages.append(f"{label}{particle} 목표가 0이지만 {self._fmt(consumed)}{unit} 섭취했습니다")
                continue
            remaining = target - consumed
            if remaining >= 0:
                messages.append(f"{label}{particle} 목표까지 {self._fmt(remaining)}{unit} 남았습니다")
            else:
                messages.append(f"{label}{particle} 목표를 {self._fmt(-remaining)}{unit} 초과했습니다")
        return ". ".join(messages) + ("." if messages else "오늘의 영양 목표가 모두 0으로 설정되어 있습니다.")

    @staticmethod
    def _fmt(value: Decimal) -> str:
        normalized = value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return format(normalized, "f").rstrip("0").rstrip(".") or "0"
