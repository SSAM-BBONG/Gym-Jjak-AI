from functools import lru_cache

from app.diet.analyzer import MealImageAnalyzer
from app.diet.service import DietService
from app.llm.gemini_adapter import GeminiAdapter
from app.llm.port import LLMPort


@lru_cache
def get_llm_client() -> LLMPort:
    """DI 조립부. 여기 한 곳만 바꾸면 어댑터(구현체)를 통째로 교체할 수 있다."""
    return GeminiAdapter()


@lru_cache
def get_diet_service() -> DietService:
    return DietService(MealImageAnalyzer(get_llm_client()))
