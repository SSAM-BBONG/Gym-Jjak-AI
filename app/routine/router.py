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
    """담당 회원(subject_user_id)에 대한 상세 루틴 분석. 담당 관계 검증 실패 시
    RoutineService가 SubjectAccessDeniedError(403 TRAINER_SUBJECT_ACCESS_DENIED)를 던진다."""
    return await service.recommend_for_trainer(actor=request.actor, subject_user_id=request.subject_user_id)
