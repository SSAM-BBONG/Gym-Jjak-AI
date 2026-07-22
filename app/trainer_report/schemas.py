from pydantic import BaseModel, ConfigDict


class BodyPartTrend(BaseModel):
    body_part: str
    percentage: float
    percentage_change_from_last_month: float | None = None  # Java가 계산. 데이터 없으면 None(첫 달 등)


class PriceDistribution(BaseModel):
    """가격대 구간별 분포. percentage는 상품 개수가 아니라 수강생 수 기준 비중이다.
    price_range는 사람이 읽는 표시용 라벨이고, 실제 구간 소속 판정은 min_price/max_price로 한다.
    percentage_change_from_last_month는 price_distribution(총액)에만 의미가 있다 —
    price_per_session_distribution에는 Java가 이 필드를 채우지 않는다(항상 None)."""

    price_range: str
    min_price: int
    max_price: int | None = None  # None이면 상한 없음(최고 구간)
    percentage: float
    percentage_change_from_last_month: float | None = None


class SessionCountDistribution(BaseModel):
    """회차 수별 분포. 가격과 달리 연속 구간이 아니라 특정 회차 값 단위로 집계한다."""

    session_count: int
    percentage: float


class LocationDistribution(BaseModel):
    region: str
    percentage: float


class MarketTrends(BaseModel):
    """전체 시장 집계 데이터. Java가 미리 조회해서 요청에 번들로 실어 보낸다."""

    popular_body_parts: list[BodyPartTrend]
    price_distribution: list[PriceDistribution]
    price_per_session_distribution: list[PriceDistribution]
    session_count_distribution: list[SessionCountDistribution]
    location_distribution: list[LocationDistribution]


class MyPtCourse(BaseModel):
    """이 트레이너가 현재 운영 중인 PT 상품 하나."""

    name: str
    price: int
    session_count: int
    body_part: str


class TrainerReportRequest(BaseModel):
    trainer_id: int
    market_trends: MarketTrends
    my_pt_courses: list[MyPtCourse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trainer_id": 1,
                "market_trends": {
                    "popular_body_parts": [
                        {"body_part": "하체", "percentage": 35.2, "percentage_change_from_last_month": 5.0},
                        {"body_part": "코어", "percentage": 22.8, "percentage_change_from_last_month": -1.2},
                    ],
                    "price_distribution": [
                        {
                            "price_range": "15~20만원",
                            "min_price": 150000,
                            "max_price": 200000,
                            "percentage": 40.0,
                            "percentage_change_from_last_month": -3.0,
                        },
                        {
                            "price_range": "20~25만원",
                            "min_price": 200000,
                            "max_price": 250000,
                            "percentage": 28.5,
                            "percentage_change_from_last_month": 2.1,
                        },
                    ],
                    "price_per_session_distribution": [
                        {"price_range": "2~2.5만원", "min_price": 20000, "max_price": 25000, "percentage": 32.0},
                        {"price_range": "2.5~3만원", "min_price": 25000, "max_price": 30000, "percentage": 27.4},
                    ],
                    "session_count_distribution": [
                        {"session_count": 8, "percentage": 40.0},
                        {"session_count": 10, "percentage": 25.0},
                    ],
                    "location_distribution": [
                        {"region": "강남구", "percentage": 25.0},
                        {"region": "서초구", "percentage": 18.3},
                    ],
                },
                "my_pt_courses": [
                    {"name": "8회 전신 패키지", "price": 240000, "session_count": 8, "body_part": "전신"}
                ],
            }
        }
    )


class TrainerReportResponse(BaseModel):
    report: str
