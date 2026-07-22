from httpx import ASGITransport, AsyncClient

from app.chatbot.dependencies import get_chatbot_service
from app.chatbot.schemas import ChatResponse
from main import app

_HEADERS = {"X-Internal-Api-Key": "local-development-only"}


class FakeChatbotService:
    def __init__(self, response: ChatResponse) -> None:
        self.response = response
        self.received_requests: list = []

    async def chat(self, request):
        self.received_requests.append(request)
        return self.response


def _payload(**overrides) -> dict:
    payload = {
        "session_id": "019f0000-0000-7000-8000-000000000001",
        "message": "환불 정책이 궁금해요",
        "intent_hint": None,
        "actor": {"user_id": 10, "role": "USER"},
    }
    payload.update(overrides)
    return payload


async def test_chat_message_returns_common_response_contract() -> None:
    fake = FakeChatbotService(
        ChatResponse(
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
    body = response.json()
    assert body["answer"] == "환불은 7일 이내 가능합니다."
    assert body["category"] == "SERVICE_POLICY"
    assert body["limited"] is False
    assert len(fake.received_requests) == 1


async def test_chat_message_requires_internal_api_key() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/chatbot/messages", json=_payload())

    assert response.status_code == 401
    assert response.json()["code"] == "INTERNAL_AUTH_FAILED"


async def test_chat_message_rejects_blank_message() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chatbot/messages", headers=_HEADERS, json=_payload(message="")
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"


async def test_chat_message_maps_service_error_code_to_http_status() -> None:
    from app.routine.exceptions import SubscriptionRequiredError

    class FailingService:
        async def chat(self, request):
            raise SubscriptionRequiredError()

    app.dependency_overrides[get_chatbot_service] = lambda: FailingService()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chatbot/messages", headers=_HEADERS, json=_payload()
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["code"] == "CHATBOT_SUBSCRIPTION_REQUIRED"
