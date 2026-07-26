"""회원 챗봇 API 계약 테스트. SSE(text/event-stream) 응답 헤더, done/error 이벤트
포맷, 인증/검증 오류(스트림 진입 전 실패)를 검증한다."""

import json

from httpx import ASGITransport, AsyncClient

from app.chatbot.dependencies import get_chatbot_service
from app.chatbot.schemas import ChatResponse
from main import app

_HEADERS = {"X-Internal-Api-Key": "local-development-only"}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


class FakeChatbotService:
    """라우터 배선(SSE 헤더, 이벤트 포맷)만 검증하면 되므로 delta 없이
    done 또는 error 이벤트 하나만 낸다."""

    def __init__(self, *, done: ChatResponse | None = None, error: dict | None = None) -> None:
        self.done = done
        self.error = error
        self.received_requests: list = []

    async def chat(self, request):
        self.received_requests.append(request)
        if self.error is not None:
            yield _sse_event("error", self.error)
            return
        yield _sse_event("done", self.done.model_dump(mode="json"))


def _payload(**overrides) -> dict:
    payload = {
        "session_id": "019f0000-0000-7000-8000-000000000001",
        "message": "환불 정책이 궁금해요",
        "intent_hint": None,
        "actor": {"user_id": 10, "role": "USER"},
    }
    payload.update(overrides)
    return payload


async def test_chat_message_streams_done_event_with_common_response_contract() -> None:
    fake = FakeChatbotService(
        done=ChatResponse(
            request_id="req-1", session_id="019f0000-0000-7000-8000-000000000001",
            answer="환불은 7일 이내 가능합니다.", category="SERVICE_POLICY",
            routine=None, sources=[], limited=False,
        )
    )
    app.dependency_overrides[get_chatbot_service] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chatbot/messages", headers=_HEADERS, json=_payload()
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert events == [
        (
            "done",
            {
                "request_id": "req-1",
                "session_id": "019f0000-0000-7000-8000-000000000001",
                "answer": "환불은 7일 이내 가능합니다.",
                "category": "SERVICE_POLICY",
                    "routine": None,
                    "sources": [],
                    "limited": False,
                    "quick_replies": [],
                },
        )
    ]
    assert len(fake.received_requests) == 1


async def test_chat_message_requires_internal_api_key() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/chatbot/messages", json=_payload())

    assert response.status_code == 401
    assert response.json()["code"] == "INTERNAL_AUTH_FAILED"


async def test_chat_message_rejects_blank_message() -> None:
    app.dependency_overrides[get_chatbot_service] = lambda: FakeChatbotService()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chatbot/messages", headers=_HEADERS, json=_payload(message="")
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"


async def test_chat_message_parses_spring_personal_data_snapshot() -> None:
    fake = FakeChatbotService(
        done=ChatResponse(
            request_id="req-1", session_id="019f0000-0000-7000-8000-000000000001",
            answer="ok", category="ROUTINE",
        )
    )
    app.dependency_overrides[get_chatbot_service] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chatbot/messages",
                headers=_HEADERS,
                json=_payload(
                    intent_hint="ROUTINE_RECOMMENDATION",
                    personal_data={
                        "onboarding": {
                            "exercise_goal": "MUSCLE_GAIN",
                            "exercise_period": "OVER_6_MONTHS",
                            "exercise_frequency": "THREE_TO_FOUR",
                            "preferred_exercise": "WEIGHT_TRAINING",
                        },
                        "recent_workouts": [{
                            "diary_date": "2026-07-25",
                            "part": "CHEST",
                            "exercise": "Bench Press",
                            "sets": [{"set_number": 1, "weight": 60, "reps": 10}],
                        }],
                        "workout_summary": {
                            "period_days": 28,
                            "workout_days": 3,
                            "part_session_counts": {"CHEST": 2, "BACK": 1},
                            "part_total_volume_kg": {"CHEST": 3600, "BACK": 1800},
                        },
                        "inbodies": [{
                            "measured_at": "2026-07-01",
                            "weight": 70,
                            "body_fat_percentage": 20,
                            "skeletal_muscle_mass": 30,
                        }],
                    },
                ),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    request = fake.received_requests[0]
    assert request.personal_data.workout_summary.period_days == 28
    assert request.personal_data.recent_workouts[0].exercise == "Bench Press"


async def test_chat_message_streams_error_event_for_service_error_code() -> None:
    fake = FakeChatbotService(
        error={
            "code": "ROLE_NOT_ALLOWED",
            "message": "이 기능을 사용할 권한이 없습니다.",
            "request_id": "req-1",
            "retryable": False,
        }
    )
    app.dependency_overrides[get_chatbot_service] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chatbot/messages", headers=_HEADERS, json=_payload()
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200  # 스트림은 항상 200으로 시작하고, 에러는 이벤트로 전달된다.
    events = _parse_sse(response.text)
    assert events == [
        (
            "error",
            {
                "code": "ROLE_NOT_ALLOWED",
                "message": "이 기능을 사용할 권한이 없습니다.",
                "request_id": "req-1",
                "retryable": False,
            },
        )
    ]
