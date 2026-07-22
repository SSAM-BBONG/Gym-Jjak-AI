"""회원 챗봇 API. LangGraph/LangChain/Gemini를 직접 import하지 않는다 —
요청 변환과 ChatbotService 호출만 담당한다."""

from fastapi import APIRouter, Depends

from app.chatbot.dependencies import get_chatbot_service
from app.chatbot.schemas import ChatRequest, ChatResponse
from app.chatbot.service import ChatbotService
from app.common.auth import verify_internal_api_key

router = APIRouter(
    prefix="/api/v1/chatbot",
    tags=["chatbot"],
    dependencies=[Depends(verify_internal_api_key)],
)


@router.post("/messages", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    service: ChatbotService = Depends(get_chatbot_service),
) -> ChatResponse:
    """회원 챗봇 대화 1턴. non-streaming JSON 응답."""
    return await service.chat(request)
