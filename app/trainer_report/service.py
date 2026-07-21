from app.llm.port import LLMPort
from app.trainer_report.chain import generate_trainer_report
from app.trainer_report.schemas import TrainerReportRequest, TrainerReportResponse


class TrainerReportService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def create_report(self, request: TrainerReportRequest) -> TrainerReportResponse:
        # trainer_id는 리포트 생성 로직(chain)에 넘기지 않는다 — Java가 이미 이 trainer_id의
        # 데이터만 조회해서 담아 보낸 것이므로, LLM 프롬프트에는 필요하지 않다.
        report_text = await generate_trainer_report(
            llm=self._llm,
            market_trends=request.market_trends,
            my_pt_courses=request.my_pt_courses,
        )
        return TrainerReportResponse(report=report_text)
