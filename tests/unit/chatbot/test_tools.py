from datetime import date

import pytest

from app.chatbot.tools import (
    TOOL_NAMES,
    DuplicateToolCallError,
    ToolArgumentValidationError,
    ToolCallLimitExceededError,
    ToolRegistry,
)


class FakeSpringChatbotToolClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def get_latest_inbody(self) -> dict | None:
        self.calls.append(("get_latest_inbody", None))
        return {"measuredDate": "2026-07-23", "weight": 70.0}

    async def get_workout_history(self, from_date: date, to_date: date) -> dict:
        self.calls.append(("get_workout_history", (from_date, to_date)))
        return {"from": from_date.isoformat(), "to": to_date.isoformat(), "diaries": []}


def build_tool_registry(*, call_limit: int | None = None) -> tuple[ToolRegistry, FakeSpringChatbotToolClient]:
    client = FakeSpringChatbotToolClient()
    return ToolRegistry(client=client, call_limit=call_limit), client


def test_only_spring_backed_tools_are_registered() -> None:
    assert TOOL_NAMES == ("get_latest_inbody", "get_workout_history")
    registry, _ = build_tool_registry()
    schemas = registry.tool_definitions()
    assert [schema["function"]["name"] for schema in schemas] == list(TOOL_NAMES)
    assert all("user_id" not in schema["function"]["parameters"]["properties"] for schema in schemas)


async def test_get_latest_inbody_calls_spring_client_without_model_identity() -> None:
    registry, client = build_tool_registry()

    result = await registry.execute("get_latest_inbody", {"user_id": 999})

    assert result.tool_name == "get_latest_inbody"
    assert result.data == {"measuredDate": "2026-07-23", "weight": 70.0}
    assert client.calls == [("get_latest_inbody", None)]


async def test_get_workout_history_parses_only_from_and_to() -> None:
    registry, client = build_tool_registry()

    result = await registry.execute(
        "get_workout_history",
        {"from": "2026-07-01", "to": "2026-07-23", "user_id": 999},
    )

    assert result.data["diaries"] == []
    assert client.calls == [("get_workout_history", (date(2026, 7, 1), date(2026, 7, 23)))]


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"from": "not-a-date", "to": "2026-07-23"},
        {"from": "2026-07-23", "to": "2026-07-01"},
        {"from": "2026-06-01", "to": "2026-07-23"},
    ],
)
async def test_get_workout_history_rejects_invalid_period_before_spring_call(args: dict) -> None:
    registry, client = build_tool_registry()

    with pytest.raises(ToolArgumentValidationError):
        await registry.execute("get_workout_history", args)

    assert client.calls == []


async def test_same_tool_and_args_cannot_repeat() -> None:
    registry, _ = build_tool_registry()
    await registry.execute("get_latest_inbody", {})

    with pytest.raises(DuplicateToolCallError):
        await registry.execute("get_latest_inbody", {})


async def test_call_limit_exceeded_raises() -> None:
    registry, _ = build_tool_registry(call_limit=1)
    await registry.execute("get_latest_inbody", {})

    with pytest.raises(ToolCallLimitExceededError):
        await registry.execute("get_workout_history", {"from": "2026-07-01", "to": "2026-07-23"})


async def test_unknown_tool_returns_error_result_without_raising() -> None:
    registry, _ = build_tool_registry()

    result = await registry.execute("get_payment_history", {})

    assert result.data == {"error": "UNKNOWN_TOOL"}
