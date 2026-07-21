from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, field_serializer, field_validator


NutrientDecimal = Decimal


class MealType(str, Enum):
    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    DINNER = "DINNER"
    SNACK = "SNACK"


class NutritionGoal(BaseModel):
    protein: int = Field(ge=0)
    carbohydrate: int = Field(ge=0)
    fat: int = Field(ge=0)
    kcal: int = Field(ge=0)


class NutritionIntake(BaseModel):
    kcal: int = Field(ge=0)
    carbohydrate: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)
    protein: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)
    fat: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)


class DietAnalysisRequest(BaseModel):
    image_url: HttpUrl
    meal_type: MealType
    meal_time: datetime
    nutrition_goal: NutritionGoal | None
    today_intake: NutritionIntake


class RawMealAnalysis(BaseModel):
    """Gemini 구조화 출력 전용 모델."""

    food_detected: bool
    menu: str = Field(max_length=255)
    kcal: int = Field(ge=0)
    carbohydrate: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)
    protein: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)
    fat: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)
    confidence: Decimal = Field(ge=0, le=1, decimal_places=3)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("menu")
    @classmethod
    def trim_menu(cls, value: str) -> str:
        return value.strip()

    @field_validator("warnings")
    @classmethod
    def clean_warnings(cls, values: list[str]) -> list[str]:
        return [value.strip()[:300] for value in values if value and value.strip()]


class DietAnalysisResponse(BaseModel):
    menu: str = Field(min_length=1, max_length=255)
    kcal: int = Field(ge=0)
    carbohydrate: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)
    protein: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)
    fat: NutrientDecimal = Field(ge=0, decimal_places=2, max_digits=8)
    evaluation: str = Field(min_length=1, max_length=1000)
    confidence: Decimal = Field(ge=0, le=1, decimal_places=3)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @field_serializer("carbohydrate", "protein", "fat", "confidence", when_used="json")
    def serialize_decimal(self, value: Decimal) -> float:
        return float(value)


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool
