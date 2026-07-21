from fastapi import APIRouter, Depends

from app.core.dependencies import get_llm_client
from app.llm.port import LLMPort
from app.trainer_report.schemas import TrainerReportRequest, TrainerReportResponse
from app.trainer_report.service import TrainerReportService

router = APIRouter(prefix="/trainer-report", tags=["trainer-report"])


def get_trainer_report_service(llm: LLMPort = Depends(get_llm_client)) -> TrainerReportService:
    return TrainerReportService(llm=llm)


@router.post("", response_model=TrainerReportResponse)
async def create_trainer_report(
    request: TrainerReportRequest,
    service: TrainerReportService = Depends(get_trainer_report_service),
) -> TrainerReportResponse:
    """Java 스케줄러가 트레이너별로 주기 호출한다.
    market_trends, my_pt_courses는 Java가 미리 조회해서 요청에 번들로 실어 보낸다."""
    return await service.create_report(request)
