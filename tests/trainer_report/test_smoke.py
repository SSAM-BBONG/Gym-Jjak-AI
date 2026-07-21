"""실제 Gemini API를 호출해서 LLM 호출부가 진짜로 동작하는지 확인하는 smoke test.
기본 `pytest` 실행에서는 스킵되고, `pytest --run-smoke`로만 실행된다."""

import time

import pytest

from app.core.dependencies import get_llm_client
from app.trainer_report.chain import generate_trainer_report
from app.trainer_report.schemas import (
    BodyPartTrend,
    LocationDistribution,
    MarketTrends,
    MyPtCourse,
    PriceDistribution,
)


@pytest.mark.smoke
async def test_trainer_report_real_gemini_call():
    llm = get_llm_client()

    market_trends = MarketTrends(
        popular_body_parts=[BodyPartTrend(body_part="하체", percentage=35.2)],
        price_distribution=[PriceDistribution(price_range="15~20만원", percentage=40.0)],
        average_session_count=9.5,
        location_distribution=[LocationDistribution(region="강남구", percentage=25.0)],
    )
    courses = [MyPtCourse(name="8회 패키지", price=200000, session_count=8, body_part="전신")]

    start = time.monotonic()
    result = await generate_trainer_report(llm, market_trends, courses)
    elapsed = time.monotonic() - start

    print(f"\n[smoke] 응답 시간: {elapsed:.2f}s, 응답 길이: {len(result)}자")

    # 프롬프트 원문·API 키는 출력하지 않는다 (ERROR_HANDLING.md 로그 정책)
    assert isinstance(result, str)
    assert len(result) > 0
