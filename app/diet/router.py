from fastapi import APIRouter, Depends

from app.core.dependencies import get_diet_service
from app.core.security import verify_internal_api_key
from app.diet.schemas import DietAnalysisRequest, DietAnalysisResponse
from app.diet.service import DietService


router = APIRouter(prefix="/api/v1/meals", tags=["diet"])


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
