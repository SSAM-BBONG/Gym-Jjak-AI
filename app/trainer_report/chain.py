from app.llm.errors import LLMInvalidResponseError
from app.llm.models import LLMMessage
from app.llm.port import LLMPort
from app.trainer_report.comparison import CourseComparison, RankedItem, compare_course
from app.trainer_report.prompts import TRAINER_REPORT_SYSTEM_PROMPT
from app.trainer_report.schemas import MarketTrends, MyPtCourse


def _with_delta(label: str, percentage: float, delta: float | None) -> str:
    """delta가 있으면(Java가 계산해서 보내준 경우) 전월 대비 변화를 같이 표시한다.
    없으면(예: 첫 달이라 비교 대상이 없는 경우) 그냥 현재 값만 표시한다."""
    if delta is None:
        return f"{label} {percentage}%"
    return f"{label} {percentage}%(전월 대비 {delta:+.1f}%p)"


_NEGLIGIBLE_PERCENTAGE_THRESHOLD = 1.0  # 이 미만은 서술에서 의미 없는 지표로 보고 생략(사용자 결정)


def _format_market_trends(trends: MarketTrends) -> str:
    """구간 폭은 고정이라(예: 가격 5만원 단위, 0원부터) 실제 수강생이 거의 없는 구간도
    낮은 percentage로 옴 — 1% 미만은 의미 없는 지표로 보고 서술에서 생략한다(비교용 원본
    데이터는 그대로 둠, 본인 상품이 그 구간에 속하는 경우도 있을 수 있어서 comparison.py에는
    전체를 넘김 — Section 2의 본인 위치 표시는 이 임계값과 무관하게 항상 정확히 나옴)."""
    body_parts = ", ".join(
        _with_delta(t.body_part, t.percentage, t.percentage_change_from_last_month)
        for t in trends.popular_body_parts
        if t.percentage >= _NEGLIGIBLE_PERCENTAGE_THRESHOLD
    )
    prices = ", ".join(
        _with_delta(p.price_range, p.percentage, p.percentage_change_from_last_month)
        for p in trends.price_distribution
        if p.percentage >= _NEGLIGIBLE_PERCENTAGE_THRESHOLD
    )
    price_per_session = ", ".join(
        f"{p.price_range} {p.percentage}%"
        for p in trends.price_per_session_distribution
        if p.percentage >= _NEGLIGIBLE_PERCENTAGE_THRESHOLD
    )
    session_counts = ", ".join(
        f"{s.session_count}회 {s.percentage}%"
        for s in trends.session_count_distribution
        if s.percentage >= _NEGLIGIBLE_PERCENTAGE_THRESHOLD
    )
    locations = ", ".join(
        f"{loc.region} {loc.percentage}%"
        for loc in trends.location_distribution
        if loc.percentage >= _NEGLIGIBLE_PERCENTAGE_THRESHOLD
    )
    return (
        f"- 인기 부위: {body_parts}\n"
        f"- 가격대 분포: {prices}\n"
        f"- 회차당가격 분포: {price_per_session}\n"
        f"- 회차 수 분포: {session_counts}\n"
        f"- 지역별 분포: {locations}"
    )


def _format_position(label: str, my_value_label: str, items: list[RankedItem]) -> str:
    """본인 상품이 전체 구간 중 몇 위에 있는지만 짚어준다. 전체 구간 순위 자체는 이미
    [이번 달 시장 동향]에서 한 번 다 보여줬으므로, 여기서 다시 나열하지 않는다(중복 방지)."""
    matched_index = next((i for i, item in enumerate(items) if item.is_mine), None)
    if matched_index is None:
        return (
            f"{label}: 본인 값 {my_value_label}은 제공된 구간 데이터 범위 밖이라 "
            f"순위상 위치가 확인되지 않음"
        )
    matched = items[matched_index]
    return (
        f"{label}: {matched.label} 구간({matched.percentage}%, "
        f"전체 {len(items)}개 구간 중 {matched_index + 1}위)"
    )


def _format_course_comparison(comparison: CourseComparison) -> str:
    price_per_session_label = f"{comparison.price_per_session:,.0f}원"
    return (
        f"- {comparison.course_name}\n"
        f"  {_format_position('가격', f'{comparison.price:,}원', comparison.price_ranking)}\n"
        f"  {_format_position('회차당가격', price_per_session_label, comparison.price_per_session_ranking)}\n"
        f"  {_format_position('회차 수', f'{comparison.session_count}회', comparison.session_count_ranking)}"
    )


def _format_my_courses(courses: list[MyPtCourse], market_trends: MarketTrends) -> str:
    if not courses:
        return "(현재 운영 중인 PT 상품 없음)"
    comparisons = [compare_course(course, market_trends) for course in courses]
    return "\n".join(_format_course_comparison(comparison) for comparison in comparisons)


async def generate_trainer_report(
    llm: LLMPort,
    market_trends: MarketTrends,
    my_pt_courses: list[MyPtCourse],
) -> str:
    """시장 데이터 + 본인 PT 상품을 종합해서 트레이너용 리포트 텍스트를 생성한다.
    Function Calling과 RAG는 쓰지 않는다 — 필요한 데이터는 이미 인자로 확정적으로 들어온다.
    구간 순위/본인 위치 판정은 comparison.py가 미리 계산해서 넘기고, LLM은 그 결과를 narration만 한다."""

    user_content = (
        f"[이번 달 시장 동향]\n{_format_market_trends(market_trends)}\n\n"
        f"[운영 중인 PT 상품 비교]\n{_format_my_courses(my_pt_courses, market_trends)}"
    )

    messages = [
        LLMMessage(role="system", content=TRAINER_REPORT_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]

    response = await llm.generate(messages)

    if response.text is None:
        raise LLMInvalidResponseError("트레이너 리포트 생성 결과에 text가 없습니다.")

    return response.text
