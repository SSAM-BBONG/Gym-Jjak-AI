from functools import lru_cache

from app.core.settings import get_settings
from app.diet.analyzer import MealImageAnalyzer
from app.diet.service import DietService
from app.llm.gemini_adapter import GeminiAdapter
from app.llm.port import LLMPort


@lru_cache
def get_diet_llm_client() -> LLMPort:
    return GeminiAdapter(temperature=get_settings().diet_llm_temperature)


@lru_cache
def get_diet_service() -> DietService:
    return DietService(MealImageAnalyzer(get_diet_llm_client()))
