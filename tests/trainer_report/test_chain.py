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
    SessionCountDistribution,
)
from tests.fakes.llm import FakeLLMPort


def _sample_market_trends() -> MarketTrends:
    return MarketTrends(
        popular_body_parts=[BodyPartTrend(body_part="하체", percentage=35.2)],
        price_distribution=[
            PriceDistribution(price_range="15~20만원", min_price=150000, max_price=200000, percentage=40.0)
        ],
        price_per_session_distribution=[
            PriceDistribution(price_range="2~2.5만원", min_price=20000, max_price=25000, percentage=40.0)
        ],
        session_count_distribution=[SessionCountDistribution(session_count=8, percentage=40.0)],
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


async def test_generate_trainer_report_includes_delta_when_present():
    fake_llm = FakeLLMPort(response=LLMResponse(text="ok"))
    market_trends = MarketTrends(
        popular_body_parts=[
            BodyPartTrend(body_part="하체", percentage=35.2, percentage_change_from_last_month=5.0)
        ],
        price_distribution=[
            PriceDistribution(
                price_range="15~20만원",
                min_price=150000,
                max_price=200000,
                percentage=40.0,
                percentage_change_from_last_month=-3.0,
            )
        ],
        price_per_session_distribution=[
            PriceDistribution(price_range="2~2.5만원", min_price=20000, max_price=25000, percentage=40.0)
        ],
        session_count_distribution=[SessionCountDistribution(session_count=8, percentage=40.0)],
        location_distribution=[LocationDistribution(region="강남구", percentage=25.0)],
    )

    await generate_trainer_report(llm=fake_llm, market_trends=market_trends, my_pt_courses=[])

    user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user")
    assert "하체 35.2%(전월 대비 +5.0%p)" in user_message.content
    assert "15~20만원 40.0%(전월 대비 -3.0%p)" in user_message.content


async def test_generate_trainer_report_omits_delta_when_absent():
    fake_llm = FakeLLMPort(response=LLMResponse(text="ok"))

    await generate_trainer_report(
        llm=fake_llm,
        market_trends=_sample_market_trends(),
        my_pt_courses=[],
    )

    user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user")
    assert "전월 대비" not in user_message.content


async def test_generate_trainer_report_notes_when_no_bucket_matches():
    """트레이너 상품 가격이 어느 구간에도 안 걸리면(예: 데이터가 그 범위를 안 다루는 경우),
    아무 표시 없이 넘어가지 않고 "확인되지 않음"을 명시적으로 narration에 남겨야 한다."""
    fake_llm = FakeLLMPort(response=LLMResponse(text="ok"))
    courses = [MyPtCourse(name="고가 상품", price=900000, session_count=8, body_part="전신")]

    await generate_trainer_report(
        llm=fake_llm,
        market_trends=_sample_market_trends(),
        my_pt_courses=courses,
    )

    user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user")
    assert "본인 값 900,000원은 제공된 구간 데이터 범위 밖이라 순위상 위치가 확인되지 않음" in user_message.content
    assert "본인 값 112,500원은 제공된 구간 데이터 범위 밖이라 순위상 위치가 확인되지 않음" in user_message.content


async def test_generate_trainer_report_course_position_shows_rank_without_repeating_full_list():
    """Section 2는 전체 구간 순위를 다시 나열하지 않고, 본인 상품이 몇 위인지만 짚어야 한다.
    전체 구간 목록은 이미 Section 1(시장 동향)에 한 번만 나와야 한다(중복 방지)."""
    fake_llm = FakeLLMPort(response=LLMResponse(text="ok"))
    market_trends = MarketTrends(
        popular_body_parts=[BodyPartTrend(body_part="하체", percentage=35.2)],
        price_distribution=[
            PriceDistribution(price_range="15~20만원", min_price=150000, max_price=200000, percentage=60.0),
            PriceDistribution(price_range="20~25만원", min_price=200000, max_price=250000, percentage=40.0),
        ],
        price_per_session_distribution=[
            PriceDistribution(price_range="2~2.5만원", min_price=20000, max_price=25000, percentage=40.0)
        ],
        session_count_distribution=[SessionCountDistribution(session_count=8, percentage=40.0)],
        location_distribution=[LocationDistribution(region="강남구", percentage=25.0)],
    )
    courses = [MyPtCourse(name="상품A", price=220000, session_count=8, body_part="전신")]

    await generate_trainer_report(llm=fake_llm, market_trends=market_trends, my_pt_courses=courses)

    user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user").content
    assert "20~25만원 구간(40.0%, 전체 2개 구간 중 2위)" in user_message
    assert user_message.count("15~20만원") == 1


async def test_generate_trainer_report_omits_negligible_bucket_from_market_summary_but_still_matches_course():
    """1% 미만은 의미 없는 지표로 보고 [이번 달 시장 동향] 서술에서는 생략하지만,
    본인 상품이 그 구간에 속하는 경우 Section 2에서는 여전히 정상적으로 매칭돼야 한다
    (비교용 원본 데이터는 필터링 안 함, 임계값과 무관하게 본인 위치는 항상 정확히 표시)."""
    fake_llm = FakeLLMPort(response=LLMResponse(text="ok"))
    market_trends = MarketTrends(
        popular_body_parts=[BodyPartTrend(body_part="하체", percentage=35.2)],
        price_distribution=[
            PriceDistribution(price_range="0~5만원", min_price=0, max_price=50000, percentage=0.5),
            PriceDistribution(price_range="5~10만원", min_price=50000, max_price=100000, percentage=99.5),
        ],
        price_per_session_distribution=[
            PriceDistribution(price_range="2~2.5만원", min_price=20000, max_price=25000, percentage=40.0)
        ],
        session_count_distribution=[SessionCountDistribution(session_count=8, percentage=40.0)],
        location_distribution=[LocationDistribution(region="강남구", percentage=25.0)],
    )
    courses = [MyPtCourse(name="초저가 체험 패키지", price=20000, session_count=8, body_part="전신")]

    await generate_trainer_report(llm=fake_llm, market_trends=market_trends, my_pt_courses=courses)

    user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user").content
    assert "0~5만원" not in user_message.split("[운영 중인 PT 상품 비교]")[0]  # Section 1 서술엔 없음
    assert "0~5만원 구간(0.5%, 전체 2개 구간 중 2위)" in user_message  # Section 2엔 여전히 매칭됨


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
