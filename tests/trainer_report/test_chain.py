import pytest

from app.llm.errors import LLMInvalidResponseError
from app.llm.models import LLMResponse
from app.trainer_report.chain import generate_trainer_report
from app.trainer_report.schemas import (
    BodyPartTrend,
    LocationDistribution,
    MarketTrends,
    MyPtCourse,
    PriceDistribution,
)
from tests.fakes.llm import FakeLLMPort


def _sample_market_trends() -> MarketTrends:
    return MarketTrends(
        popular_body_parts=[BodyPartTrend(body_part="하체", percentage=35.2)],
        price_distribution=[PriceDistribution(price_range="15~20만원", percentage=40.0)],
        average_session_count=9.5,
        location_distribution=[LocationDistribution(region="강남구", percentage=25.0)],
    )


def _sample_courses() -> list[MyPtCourse]:
    return [MyPtCourse(name="8회 패키지", price=200000, session_count=8, body_part="전신")]


async def test_generate_trainer_report_returns_llm_text():
    fake_llm = FakeLLMPort(response=LLMResponse(text="테스트 리포트"))

    result = await generate_trainer_report(
        llm=fake_llm,
        market_trends=_sample_market_trends(),
        my_pt_courses=_sample_courses(),
    )

    assert result == "테스트 리포트"


async def test_generate_trainer_report_includes_data_in_prompt():
    fake_llm = FakeLLMPort(response=LLMResponse(text="ok"))

    await generate_trainer_report(
        llm=fake_llm,
        market_trends=_sample_market_trends(),
        my_pt_courses=_sample_courses(),
    )

    sent_messages = fake_llm.received_messages[0]
    system_message = next(m for m in sent_messages if m.role == "system")
    user_message = next(m for m in sent_messages if m.role == "user")

    assert "비서" in system_message.content
    assert "트레이닝 지도 방식" in system_message.content  # 방법론 개입 금지 문구 포함 확인
    assert "하체" in user_message.content
    assert "8회 패키지" in user_message.content


async def test_generate_trainer_report_raises_when_text_missing():
    fake_llm = FakeLLMPort(response=LLMResponse(text=None))

    with pytest.raises(LLMInvalidResponseError):
        await generate_trainer_report(
            llm=fake_llm,
            market_trends=_sample_market_trends(),
            my_pt_courses=[],
        )


async def test_generate_trainer_report_handles_no_courses():
    fake_llm = FakeLLMPort(response=LLMResponse(text="ok"))

    await generate_trainer_report(
        llm=fake_llm,
        market_trends=_sample_market_trends(),
        my_pt_courses=[],
    )

    user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user")
    assert "현재 운영 중인 PT 상품 없음" in user_message.content
