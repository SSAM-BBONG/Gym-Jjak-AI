from pydantic import BaseModel, ConfigDict


class BodyPartTrend(BaseModel):
    body_part: str
    percentage: float


class PriceDistribution(BaseModel):
    price_range: str
    percentage: float


class LocationDistribution(BaseModel):
    region: str
    percentage: float


class MarketTrends(BaseModel):
    """전체 시장 집계 데이터. Java가 미리 조회해서 요청에 번들로 실어 보낸다."""

    popular_body_parts: list[BodyPartTrend]
    price_distribution: list[PriceDistribution]
    average_session_count: float
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
                        {"body_part": "하체", "percentage": 35.2},
                        {"body_part": "코어", "percentage": 22.8},
                    ],
                    "price_distribution": [
                        {"price_range": "15~20만원", "percentage": 40.0},
                        {"price_range": "20~25만원", "percentage": 28.5},
                    ],
                    "average_session_count": 9.5,
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
