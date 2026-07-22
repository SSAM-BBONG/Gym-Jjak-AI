from app.trainer_report.comparison import (
    compare_course,
    rank_price_distribution,
    rank_session_count_distribution,
)
from app.trainer_report.schemas import (
    BodyPartTrend,
    LocationDistribution,
    MarketTrends,
    MyPtCourse,
    PriceDistribution,
    SessionCountDistribution,
)


def _price_distribution() -> list[PriceDistribution]:
    return [
        PriceDistribution(price_range="15~20만원", min_price=150000, max_price=200000, percentage=35.0),
        PriceDistribution(price_range="20~25만원", min_price=200000, max_price=250000, percentage=45.0),
        PriceDistribution(price_range="25만원 이상", min_price=250000, max_price=None, percentage=20.0),
    ]


def test_rank_price_distribution_sorts_by_percentage_descending():
    ranking = rank_price_distribution(_price_distribution(), my_price=300000)

    assert [item.percentage for item in ranking] == [45.0, 35.0, 20.0]


def test_rank_price_distribution_marks_matching_bucket():
    ranking = rank_price_distribution(_price_distribution(), my_price=220000)

    matched = [item for item in ranking if item.is_mine]
    assert len(matched) == 1
    assert matched[0].label == "20~25만원"


def test_rank_price_distribution_marks_open_ended_top_bucket():
    ranking = rank_price_distribution(_price_distribution(), my_price=500000)

    matched = [item for item in ranking if item.is_mine]
    assert len(matched) == 1
    assert matched[0].label == "25만원 이상"


def test_rank_price_distribution_no_match_when_out_of_range():
    ranking = rank_price_distribution(_price_distribution(), my_price=50000)

    assert all(not item.is_mine for item in ranking)


def test_rank_price_distribution_boundary_value_belongs_to_upper_bucket():
    """맞닿은 두 구간의 경계값(20만원)은 상한 쪽("20~25만원")에만 속해야 하고,
    하한 쪽("15~20만원")에는 속하면 안 된다."""
    ranking = rank_price_distribution(_price_distribution(), my_price=200000)

    matched = [item for item in ranking if item.is_mine]
    assert len(matched) == 1
    assert matched[0].label == "20~25만원"


def test_rank_session_count_distribution_marks_exact_value():
    distribution = [
        SessionCountDistribution(session_count=8, percentage=40.0),
        SessionCountDistribution(session_count=10, percentage=25.0),
    ]

    ranking = rank_session_count_distribution(distribution, my_session_count=10)

    matched = [item for item in ranking if item.is_mine]
    assert len(matched) == 1
    assert matched[0].label == "10회"


def test_compare_course_computes_all_three_axes():
    market_trends = MarketTrends(
        popular_body_parts=[BodyPartTrend(body_part="하체", percentage=35.2)],
        price_distribution=_price_distribution(),
        price_per_session_distribution=[
            PriceDistribution(price_range="2~2.5만원", min_price=20000, max_price=25000, percentage=60.0),
            PriceDistribution(price_range="2.5~3만원", min_price=25000, max_price=30000, percentage=40.0),
        ],
        session_count_distribution=[
            SessionCountDistribution(session_count=8, percentage=40.0),
            SessionCountDistribution(session_count=10, percentage=25.0),
        ],
        location_distribution=[LocationDistribution(region="강남구", percentage=25.0)],
    )
    course = MyPtCourse(name="8회 전신 패키지", price=180000, session_count=8, body_part="전신")

    result = compare_course(course, market_trends)

    assert result.course_name == "8회 전신 패키지"
    assert next(item for item in result.price_ranking if item.is_mine).label == "15~20만원"
    assert next(item for item in result.price_per_session_ranking if item.is_mine).label == "2~2.5만원"
    assert next(item for item in result.session_count_ranking if item.is_mine).label == "8회"
