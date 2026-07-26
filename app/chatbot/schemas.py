"""회원 챗봇 API 요청/응답 DTO."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from app.common.models import ActorContext, ChatbotPersonalData
from app.routine.schemas import RoutineResult, SourceReference


class ChatMemoryMessage(BaseModel):
    """Spring이 저장한 과거 대화 1건."""

    role: Literal["user", "assistant"]
    content: str


class ChatMemoryContext(BaseModel):
    """Spring이 소유·저장하는 세션 컨텍스트 1건."""

    kind: str
    value: str


class ChatMemory(BaseModel):
    """Spring이 FastAPI에 전달하는 대화 메모리. FastAPI는 이를 영속화하지 않는다."""

    summary: str | None = None
    recent_messages: list[ChatMemoryMessage] = Field(
        default_factory=list,
        validation_alias=AliasChoices("recentMessages", "recent_messages"),
    )
    contexts: list[ChatMemoryContext] = Field(default_factory=list)


class QuickReply(BaseModel):
    """프론트가 버튼으로 렌더링할 선택지 1개."""

    question_id: str
    label: str
    value: str


class ChatRequest(BaseModel):
    """회원 챗봇 대화 1턴 요청.

    actor는 인증 연동 전 Spring이 전달하는 임시 내부 컨텍스트 계약이다.
    공개 클라이언트가 이 필드를 신뢰하는 구조로 배포하지 않는다(내부망 전용 API)."""

    session_id: str
    message: str = Field(min_length=1)
    intent_hint: str | None = None
    actor: ActorContext
    memory: ChatMemory = Field(default_factory=ChatMemory)
    personal_data: ChatbotPersonalData | None = None


class ChatResponse(BaseModel):
    """회원 챗봇 대화 1턴 응답. non-streaming."""

    request_id: str
    session_id: str
    answer: str
    category: str
    routine: RoutineResult | None = None
    sources: list[SourceReference] = []
    limited: bool = False
    quick_replies: list[QuickReply] = Field(default_factory=list)
