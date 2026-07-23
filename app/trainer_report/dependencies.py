from functools import lru_cache

from fastapi import Depends

from app.core.settings import get_settings
from app.llm.gemini_adapter import GeminiAdapter
from app.llm.port import LLMPort
from app.trainer_report.service import TrainerReportService


@lru_cache
def get_trainer_report_llm_client() -> LLMPort:
    return GeminiAdapter(temperature=get_settings().trainer_report_llm_temperature)


def get_trainer_report_service(
    llm: LLMPort = Depends(get_trainer_report_llm_client),
) -> TrainerReportService:
    return TrainerReportService(llm=llm)
