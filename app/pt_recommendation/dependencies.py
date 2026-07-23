"""PT추천 서비스 조립부. 공용 팩토리(app.core.dependencies.get_llm_client)를
주입받아 이 도메인의 서비스를 조립한다 (MODULE_OWNERSHIP.md §5)."""

from fastapi import Depends

from app.core.dependencies import get_llm_client
from app.llm.port import LLMPort
from app.pt_recommendation.service import PtRecommendationService


def get_pt_recommendation_service(
    llm: LLMPort = Depends(get_llm_client),
) -> PtRecommendationService:
    return PtRecommendationService(llm=llm)
