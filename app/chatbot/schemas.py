"""회원 챗봇 API 요청/응답 DTO."""

from pydantic import BaseModel, Field

from app.common.models import ActorContext
from app.routine.schemas import RoutineResult, SourceReference


class ChatRequest(BaseModel):
    """회원 챗봇 대화 1턴 요청.

    actor는 인증 연동 전 Spring이 전달하는 임시 내부 컨텍스트 계약이다.
    공개 클라이언트가 이 필드를 신뢰하는 구조로 배포하지 않는다(내부망 전용 API)."""

    session_id: str
    message: str = Field(min_length=1)
    intent_hint: str | None = None
    actor: ActorContext


class ChatResponse(BaseModel):
    """회원 챗봇 대화 1턴 응답. non-streaming."""

    request_id: str
    session_id: str
    answer: str
    category: str
    routine: RoutineResult | None = None
    sources: list[SourceReference] = []
    limited: bool = False
