import secrets

from fastapi import APIRouter, Depends, Header

from app.core.exceptions import internal_auth_failed
from app.core.settings import settings
from app.pt_recommendation.dependencies import get_pt_recommendation_service
from app.pt_recommendation.schemas import PtRecommendationRequest, PtRecommendationResponse
from app.pt_recommendation.service import PtRecommendationService

router = APIRouter(prefix="/api/v1/pt-recommendations", tags=["pt-recommendation"])


def verify_internal_api_key(
    api_key: str | None = Header(default=None, alias="X-Internal-Api-Key"),
) -> None:
    if not api_key or not secrets.compare_digest(api_key, settings.internal_api_key):
        raise internal_auth_failed()


@router.post(
    "",
    response_model=PtRecommendationResponse,
    dependencies=[Depends(verify_internal_api_key)],
)
async def create_pt_recommendation(
    request: PtRecommendationRequest,
    service: PtRecommendationService = Depends(get_pt_recommendation_service),
) -> PtRecommendationResponse:
    return await service.recommend(request)
