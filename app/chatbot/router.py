"""회원 챗봇 API. LangGraph/LangChain/Gemini를 직접 import하지 않는다 —
요청 변환과 ChatbotService 호출만 담당한다."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.chatbot.dependencies import get_chatbot_service
from app.chatbot.schemas import ChatRequest
from app.chatbot.service import ChatbotService
from app.common.auth import verify_internal_api_key

router = APIRouter(
    prefix="/api/v1/chatbot",
    tags=["chatbot"],
    dependencies=[Depends(verify_internal_api_key)],
)


@router.post("/messages")
async def send_message(
    request: ChatRequest,
    service: ChatbotService = Depends(get_chatbot_service),
) -> StreamingResponse:
    """회원 챗봇 대화 1턴. SSE(text/event-stream)로 델타를 흘려보내고
    마지막에 done 또는 error 이벤트로 마무리한다."""
    return StreamingResponse(service.chat(request), media_type="text/event-stream")
