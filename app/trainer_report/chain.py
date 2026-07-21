from app.llm.errors import LLMInvalidResponseError
from app.llm.models import LLMMessage
from app.llm.port import LLMPort
from app.trainer_report.prompts import TRAINER_REPORT_SYSTEM_PROMPT
from app.trainer_report.schemas import MarketTrends, MyPtCourse


def _format_market_trends(trends: MarketTrends) -> str:
    body_parts = ", ".join(f"{t.body_part} {t.percentage}%" for t in trends.popular_body_parts)
    prices = ", ".join(f"{p.price_range} {p.percentage}%" for p in trends.price_distribution)
    locations = ", ".join(f"{loc.region} {loc.percentage}%" for loc in trends.location_distribution)
    return (
        f"- 인기 부위: {body_parts}\n"
        f"- 가격대 분포: {prices}\n"
        f"- 평균 회차: {trends.average_session_count}회\n"
        f"- 지역별 분포: {locations}"
    )


def _format_my_courses(courses: list[MyPtCourse]) -> str:
    if not courses:
        return "(현재 운영 중인 PT 상품 없음)"
    return "\n".join(
        f"- {c.name}: {c.price:,}원, {c.session_count}회, {c.body_part} 중심" for c in courses
    )


async def generate_trainer_report(
    llm: LLMPort,
    market_trends: MarketTrends,
    my_pt_courses: list[MyPtCourse],
) -> str:
    """시장 데이터 + 본인 PT 상품을 종합해서 트레이너용 리포트 텍스트를 생성한다.
    Function Calling과 RAG는 쓰지 않는다 — 필요한 데이터는 이미 인자로 확정적으로 들어온다."""

    user_content = (
        f"[시장 전체 동향]\n{_format_market_trends(market_trends)}\n\n"
        f"[내가 운영 중인 PT 상품]\n{_format_my_courses(my_pt_courses)}\n\n"
        "위 데이터를 바탕으로, 시장 동향을 요약하고 내 상품 구성에 대한 개선 조언을 포함한 "
        "리포트를 작성해줘."
    )

    messages = [
        LLMMessage(role="system", content=TRAINER_REPORT_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]

    response = await llm.generate(messages)

    if response.text is None:
        raise LLMInvalidResponseError("트레이너 리포트 생성 결과에 text가 없습니다.")

    return response.text
