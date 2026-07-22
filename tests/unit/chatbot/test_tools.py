from datetime import date, timedelta

import pytest

from app.chatbot.tools import (
    TOOL_NAMES,
    DuplicateToolCallError,
    ToolCallLimitExceededError,
    ToolExecutionContext,
    ToolRegistry,
)
from app.common.models import (
    ActorContext,
    OnboardingProfile,
    PaymentHistory,
    PtUsageSummary,
    Role,
    SubscriptionStatus,
)
from tests.fakes.user_data import FakeUserDataClient
from tests.fixtures.user_data import workout_diary, workout_set

_USER_ID = 10


def member_actor(user_id: int = _USER_ID) -> ActorContext:
    return ActorContext(user_id=user_id, role=Role.USER)


def build_tool_registry(*, actor=None, user_data=None, call_limit=None) -> ToolRegistry:
    actor = actor or member_actor()
    user_data = user_data or FakeUserDataClient(
        payment_histories={_USER_ID: [PaymentHistory(paid_at="2026-07-01T00:00:00", amount="50000", item_name="1개월 이용권")]},
        pt_usages={_USER_ID: PtUsageSummary(total_sessions=10, used_sessions=3, remaining_sessions=7)},
        subscriptions={_USER_ID: SubscriptionStatus(is_active=True)},
        onboarding_profiles={_USER_ID: OnboardingProfile(goal="다이어트")},
        workout_diaries={
            _USER_ID: [
                workout_diary(
                    diary_date=date.today() - timedelta(weeks=6),
                    part="CHEST",
                    exercise="벤치프레스",
                    sets=[workout_set(1, 40, 10)],
                )
            ]
        },
    )
    return ToolRegistry(user_data=user_data, context=ToolExecutionContext(actor=actor), call_limit=call_limit), user_data


async def test_tool_ignores_model_supplied_user_identifier() -> None:
    registry, user_data = build_tool_registry()

    result = await registry.execute("get_payment_history", {"user_id": 999})

    assert result.user_id == _USER_ID
    assert user_data.calls[-1] == ("get_payment_history", _USER_ID)


async def test_same_tool_and_args_cannot_repeat() -> None:
    registry, _ = build_tool_registry()
    await registry.execute("get_pt_usage", {})

    with pytest.raises(DuplicateToolCallError):
        await registry.execute("get_pt_usage", {})


async def test_different_args_are_not_treated_as_duplicate() -> None:
    registry, _ = build_tool_registry()

    first = await registry.execute("get_recent_workouts", {"weeks": 4})
    second = await registry.execute("get_recent_workouts", {"weeks": 8})

    assert first.data == []
    assert len(second.data) == 1


async def test_call_limit_exceeded_raises() -> None:
    registry, _ = build_tool_registry(call_limit=2)
    await registry.execute("get_pt_usage", {})
    await registry.execute("get_subscription_status", {})

    with pytest.raises(ToolCallLimitExceededError):
        await registry.execute("get_onboarding", {})


async def test_unknown_tool_returns_error_result_without_raising() -> None:
    registry, _ = build_tool_registry()

    result = await registry.execute("cancel_subscription", {})

    assert result.data == {"error": "UNKNOWN_TOOL"}


def test_no_write_tools_registered() -> None:
    assert set(TOOL_NAMES) == {
        "get_payment_history",
        "get_pt_usage",
        "get_pt_history",
        "get_subscription_status",
        "get_onboarding",
        "get_recent_workouts",
        "get_recent_inbody",
    }
    assert "cancel_subscription" not in TOOL_NAMES
    assert "reserve_pt_session" not in TOOL_NAMES


async def test_get_recent_workouts_uses_only_allowed_business_args() -> None:
    registry, user_data = build_tool_registry()

    result = await registry.execute(
        "get_recent_workouts", {"weeks": 8, "trainer_id": 999, "subject_user_id": 1}
    )

    assert len(result.data) == 1
    assert user_data.calls[-1] == ("get_recent_workouts", _USER_ID)
