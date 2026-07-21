from pydantic import BaseModel

from app.trainer_report.schemas import (
    MarketTrends,
    MyPtCourse,
    PriceDistribution,
    SessionCountDistribution,
)


class RankedItem(BaseModel):
    """구간(또는 값) 하나의 순위 정보. is_mine이 True인 항목이 트레이너 본인 상품이 속한 자리다."""

    label: str
    percentage: float
    is_mine: bool


class CourseComparison(BaseModel):
    """PT 상품 하나에 대한 세 축(가격/회차당가격/회차 수) 비교 결과.
    price/price_per_session/session_count는 원본 실제값 — 구간 매칭이 안 됐을 때
    "얼마인지"를 narration에 구체적으로 남기기 위해 함께 들고 있는다."""

    course_name: str
    price: int
    price_per_session: float
    session_count: int
    price_ranking: list[RankedItem]
    price_per_session_ranking: list[RankedItem]
    session_count_ranking: list[RankedItem]


def _price_in_bucket(price: float, bucket: PriceDistribution) -> bool:
    """min_price는 포함, max_price는 미포함 — [min, max) 구간으로 판정한다.
    이렇게 해야 "15~20만원"과 "20~25만원"처럼 맞닿은 구간의 경계값(20만원)이
    두 구간에 동시에 속하는 걸 방지할 수 있다."""
    if price < bucket.min_price:
        return False
    if bucket.max_price is not None and price >= bucket.max_price:
        return False
    return True


def rank_price_distribution(distribution: list[PriceDistribution], my_price: float) -> list[RankedItem]:
    sorted_buckets = sorted(distribution, key=lambda bucket: bucket.percentage, reverse=True)
    return [
        RankedItem(
            label=bucket.price_range,
            percentage=bucket.percentage,
            is_mine=_price_in_bucket(my_price, bucket),
        )
        for bucket in sorted_buckets
    ]


def rank_session_count_distribution(
    distribution: list[SessionCountDistribution], my_session_count: int
) -> list[RankedItem]:
    sorted_buckets = sorted(distribution, key=lambda bucket: bucket.percentage, reverse=True)
    return [
        RankedItem(
            label=f"{bucket.session_count}회",
            percentage=bucket.percentage,
            is_mine=bucket.session_count == my_session_count,
        )
        for bucket in sorted_buckets
    ]


def compare_course(course: MyPtCourse, market_trends: MarketTrends) -> CourseComparison:
    price_per_session = course.price / course.session_count
    return CourseComparison(
        course_name=course.name,
        price=course.price,
        price_per_session=price_per_session,
        session_count=course.session_count,
        price_ranking=rank_price_distribution(market_trends.price_distribution, course.price),
        price_per_session_ranking=rank_price_distribution(
            market_trends.price_per_session_distribution, price_per_session
        ),
        session_count_ranking=rank_session_count_distribution(
            market_trends.session_count_distribution, course.session_count
        ),
    )
