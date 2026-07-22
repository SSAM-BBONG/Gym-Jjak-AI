import pytest

from app.routine.safety import assess_safety


@pytest.mark.parametrize(
    "message",
    [
        "운동하다가 흉통이 느껴지는데 그래도 루틴 추천해줘",
        "어제 운동 중에 실신할 뻔했어요",
        "숨쉬기가 너무 힘들고 호흡곤란이 와요",
    ],
)
def test_high_risk_signal_is_always_blocked(message: str) -> None:
    result = assess_safety(message)

    assert result.status == "BLOCKED"
    assert result.caution


def test_general_soreness_returns_limited_with_expert_referral() -> None:
    result = assess_safety("어제 운동해서 근육통이 좀 있어요")

    assert result.status == "LIMITED"
    assert result.caution


def test_no_risk_signal_returns_ok() -> None:
    result = assess_safety("주 3회 전신 루틴 추천해줘")

    assert result.status == "OK"
    assert result.caution is None
