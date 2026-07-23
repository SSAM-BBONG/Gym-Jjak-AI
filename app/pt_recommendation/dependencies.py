"""PT 추천 도메인의 LLM과 서비스를 조립한다."""

from functools import lru_cache
from fastapi import Depends

from app.core.settings import get_settings
from app.llm.gemini_adapter import GeminiAdapter
from app.llm.port import LLMPort
from app.pt_recommendation.service import PtRecommendationService


@lru_cache
def get_pt_recommendation_llm_client() -> LLMPort:
    return GeminiAdapter(temperature=get_settings().pt_recommendation_llm_temperature)


def get_pt_recommendation_service(
    llm: LLMPort = Depends(get_pt_recommendation_llm_client),
) -> PtRecommendationService:
    return PtRecommendationService(llm=llm)
