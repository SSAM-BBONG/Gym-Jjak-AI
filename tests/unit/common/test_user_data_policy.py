from datetime import date, timedelta

from tests.fakes.user_data import FakeUserDataClient
from tests.fixtures.user_data import inbody_record


async def test_recent_inbody_limited_to_six_most_recent_within_six_months() -> None:
    today = date.today()
    records = [
        inbody_record(measured_at=today - timedelta(days=30 * i), weight=70 - i)
        for i in range(8)  # 0~7개월 전, 총 8건 (6개월 초과분 포함)
    ]
    client = FakeUserDataClient(inbody_records={10: records})

    result = await client.get_recent_inbody(user_id=10, months=6, limit=6)

    assert len(result) <= 6
    assert all(r.measured_at >= today - timedelta(days=6 * 30) for r in result)
    assert result == sorted(result, key=lambda r: r.measured_at, reverse=True)


async def test_onboarding_returns_none_when_not_registered() -> None:
    client = FakeUserDataClient()

    result = await client.get_onboarding(user_id=999)

    assert result is None


async def test_payment_history_defaults_to_empty_list() -> None:
    client = FakeUserDataClient()

    result = await client.get_payment_history(user_id=999)

    assert result == []
