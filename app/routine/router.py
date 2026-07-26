"""트레이너 전용 1회성 상세 루틴 분석 API. 채팅 세션/메시지를 생성하지 않는다."""

from fastapi import APIRouter, Depends

from app.chatbot.dependencies import get_routine_service
from app.common.auth import verify_internal_api_key
from app.routine.schemas import RoutineResult, TrainerRoutineRequest
from app.routine.service import RoutineService

router = APIRouter(
    prefix="/api/v1/routines",
    tags=["routine"],
    dependencies=[Depends(verify_internal_api_key)],
)


@router.post("/trainer-analysis", response_model=RoutineResult)
async def trainer_routine_analysis(
    request: TrainerRoutineRequest,
    service: RoutineService = Depends(get_routine_service),
) -> RoutineResult:
    """Spring이 검증·조회한 수강생 스냅샷으로 상세 루틴을 생성한다."""
    return await service.recommend_for_trainer(request=request)
