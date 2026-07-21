import secrets

from fastapi import APIRouter, Depends, Header

from app.core.dependencies import get_diet_service
from app.core.exceptions import internal_auth_failed
from app.core.settings import settings
from app.diet.schemas import DietAnalysisRequest, DietAnalysisResponse
from app.diet.service import DietService


router = APIRouter(prefix="/api/v1/meals", tags=["diet"])


def verify_internal_api_key(
    api_key: str | None = Header(default=None, alias="X-Internal-Api-Key"),
) -> None:
    if not api_key or not secrets.compare_digest(api_key, settings.internal_api_key):
        raise internal_auth_failed()


@router.post(
    "/analyze",
    response_model=DietAnalysisResponse,
    dependencies=[Depends(verify_internal_api_key)],
)
async def analyze_meal(
    request: DietAnalysisRequest,
    service: DietService = Depends(get_diet_service),
) -> DietAnalysisResponse:
    return await service.analyze(request)
