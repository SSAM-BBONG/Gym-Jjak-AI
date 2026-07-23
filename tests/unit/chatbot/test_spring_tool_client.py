from datetime import date

import httpx
import pytest

from app.core.exceptions import AppError


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(base_url="http://spring.test") as client:
        yield client


def build_client(http_client: httpx.AsyncClient):
    from app.chatbot.spring_tool_client import ChatbotToolContext, SpringChatbotToolClient

    return SpringChatbotToolClient(
        context=ChatbotToolContext(session_id="session-1", request_id="request-1"),
        http_client=http_client,
    )


async def test_get_latest_inbody_sends_server_context_headers_and_returns_empty_data(
    respx_mock, http_client: httpx.AsyncClient
) -> None:
    client = build_client(http_client)
    route = respx_mock.get("http://spring.test/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(200, json={"data": None})
    )

    assert await client.get_latest_inbody() is None

    headers = route.calls[0].request.headers
    assert headers["X-Internal-Api-Key"]
    assert headers["X-Chatbot-Session-Id"] == "session-1"
    assert headers["X-Request-ID"] == "request-1"
    assert len(route.calls) == 1


async def test_get_workout_history_sends_iso_date_parameters_and_returns_only_data(
    respx_mock, http_client: httpx.AsyncClient
) -> None:
    client = build_client(http_client)
    route = respx_mock.get("http://spring.test/internal/chatbot/tools/workout-history").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "from": "2026-07-01",
                    "to": "2026-07-23",
                    "diaries": [{"date": "2026-07-23", "exercise": "squat", "part": "LEG", "setCount": 4}],
                }
            },
        )
    )

    result = await client.get_workout_history(date(2026, 7, 1), date(2026, 7, 23))

    assert result == {
        "from": "2026-07-01",
        "to": "2026-07-23",
        "diaries": [{"date": "2026-07-23", "exercise": "squat", "part": "LEG", "setCount": 4}],
    }
    assert dict(route.calls[0].request.url.params) == {"from": "2026-07-01", "to": "2026-07-23"}
    assert len(route.calls) == 1


@pytest.mark.parametrize(
    "data",
    [
        {"weight": 70.0, "bodyFatPercentage": None, "skeletalMuscleMass": None},
        {"measuredDate": "2026-07-23", "weight": "not-a-number", "bodyFatPercentage": None, "skeletalMuscleMass": None},
        {"measuredDate": "2026-07-23", "weight": "70.0", "bodyFatPercentage": None, "skeletalMuscleMass": None},
        [],
    ],
)
async def test_get_latest_inbody_rejects_invalid_data_shape(
    respx_mock, http_client: httpx.AsyncClient, data
) -> None:
    client = build_client(http_client)
    respx_mock.get("http://spring.test/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(200, json={"data": data})
    )

    with pytest.raises(AppError) as exc_info:
        await client.get_latest_inbody()

    assert exc_info.value.code == "CHATBOT_TOOL_RESPONSE_INVALID"


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"from": "2026-07-01", "to": "2026-07-23", "diaries": [{}]},
        {
            "from": "2026-07-01",
            "to": "2026-07-23",
            "diaries": [{"date": "2026-07-23", "exercise": "squat", "part": "LEG", "setCount": "four"}],
        },
        {
            "from": "2026-07-01",
            "to": "2026-07-23",
            "diaries": [{"date": "2026-07-23", "exercise": "squat", "part": "LEG", "setCount": "4"}],
        },
    ],
)
async def test_get_workout_history_rejects_invalid_data_shape(
    respx_mock, http_client: httpx.AsyncClient, data
) -> None:
    client = build_client(http_client)
    respx_mock.get("http://spring.test/internal/chatbot/tools/workout-history").mock(
        return_value=httpx.Response(200, json={"data": data})
    )

    with pytest.raises(AppError) as exc_info:
        await client.get_workout_history(date(2026, 7, 1), date(2026, 7, 23))

    assert exc_info.value.code == "CHATBOT_TOOL_RESPONSE_INVALID"


async def test_non_200_success_status_maps_to_response_invalid_error(
    respx_mock, http_client: httpx.AsyncClient
) -> None:
    client = build_client(http_client)
    respx_mock.get("http://spring.test/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(302, json={"data": None})
    )

    with pytest.raises(AppError) as exc_info:
        await client.get_latest_inbody()

    assert exc_info.value.status_code == 302
    assert exc_info.value.code == "CHATBOT_TOOL_RESPONSE_INVALID"


@pytest.mark.parametrize("status_code", [401, 403])
async def test_access_denied_status_maps_to_access_denied_error(
    respx_mock, http_client: httpx.AsyncClient, status_code: int
) -> None:
    client = build_client(http_client)
    respx_mock.get("http://spring.test/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(status_code)
    )

    with pytest.raises(AppError) as exc_info:
        await client.get_latest_inbody()

    assert exc_info.value.status_code == status_code
    assert exc_info.value.code == "CHATBOT_TOOL_ACCESS_DENIED"
    assert exc_info.value.retryable is False


@pytest.mark.parametrize("status_code", [500, 503])
async def test_server_error_maps_to_retryable_unavailable_error(
    respx_mock, http_client: httpx.AsyncClient, status_code: int
) -> None:
    client = build_client(http_client)
    respx_mock.get("http://spring.test/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(status_code)
    )

    with pytest.raises(AppError) as exc_info:
        await client.get_latest_inbody()

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "CHATBOT_TOOL_UNAVAILABLE"
    assert exc_info.value.retryable is True


@pytest.mark.parametrize("exception", [httpx.ConnectError("refused"), httpx.ReadTimeout("timed out")])
async def test_connection_or_timeout_maps_to_retryable_unavailable_error(
    respx_mock, http_client: httpx.AsyncClient, exception: httpx.RequestError
) -> None:
    client = build_client(http_client)
    respx_mock.get("http://spring.test/internal/chatbot/tools/inbody/latest").mock(side_effect=exception)

    with pytest.raises(AppError) as exc_info:
        await client.get_latest_inbody()

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "CHATBOT_TOOL_UNAVAILABLE"
    assert exc_info.value.retryable is True


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"}), 502),
        (httpx.Response(200, json={"result": {}}), 502),
        (httpx.Response(400, json={"code": "CHATBOT_TOOL_400_1"}), 400),
    ],
)
async def test_invalid_or_unexpected_response_maps_to_response_invalid_error(
    respx_mock, http_client: httpx.AsyncClient, response: httpx.Response, expected_status: int
) -> None:
    client = build_client(http_client)
    respx_mock.get("http://spring.test/internal/chatbot/tools/inbody/latest").mock(return_value=response)

    with pytest.raises(AppError) as exc_info:
        await client.get_latest_inbody()

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.code == "CHATBOT_TOOL_RESPONSE_INVALID"
    assert exc_info.value.retryable is False
