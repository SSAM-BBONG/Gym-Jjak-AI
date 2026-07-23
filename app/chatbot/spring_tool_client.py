"""FastAPI가 Spring의 챗봇 내부 읽기 도구 API를 호출하는 HTTP 어댑터.

이 모듈은 LLM이 만든 user_id를 절대 사용하지 않는다. Spring이 세션/활성 요청 헤더로
세션 소유자를 확정하므로, FastAPI는 응답의 data만 받아 ToolMessage로 전달한다.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr, ValidationError

from app.core.exceptions import (
    chatbot_tool_access_denied,
    chatbot_tool_response_invalid,
    chatbot_tool_unavailable,
)
from app.core.settings import get_settings


@dataclass(frozen=True, slots=True)
class ChatbotToolContext:
    """한 대화 요청에만 유효한 Spring 검증용 식별자.

    user_id를 보관하지 않는 것이 핵심이다. Spring은 이 두 값을 검증한 뒤 DB에서
    세션 소유자 user_id를 직접 조회한다.
    """

    session_id: str
    request_id: str


class _InbodyData(BaseModel):
    """Spring 최신 인바디 응답의 data 전용 DTO(외부 API DTO가 아닌 내부 검증용)."""

    measured_date: date = Field(alias="measuredDate")
    weight: StrictFloat
    body_fat_percentage: StrictFloat | None = Field(alias="bodyFatPercentage")
    skeletal_muscle_mass: StrictFloat | None = Field(alias="skeletalMuscleMass")


class _WorkoutDiaryData(BaseModel):
    """운동일지 한 건의 최소 근거 데이터만 검증한다."""

    diary_date: date = Field(alias="date")
    exercise: StrictStr
    part: StrictStr
    set_count: StrictInt = Field(alias="setCount")


class _WorkoutHistoryData(BaseModel):
    """Spring 운동일지 응답의 data 전용 DTO."""

    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    diaries: list[_WorkoutDiaryData]


class SpringChatbotToolClient:
    """Spring 내부 도구 API 호출과 응답 계약 검증을 담당한다.

    http_client는 ChatbotService가 요청 단위로 만들고 닫는다. 이 클래스는 연결 수명이나
    LangGraph 상태를 소유하지 않아 HTTP 경계만 독립적으로 테스트할 수 있다.
    """

    def __init__(self, *, context: ChatbotToolContext, http_client: httpx.AsyncClient) -> None:
        self._context = context
        self._http_client = http_client

    async def get_latest_inbody(self) -> dict[str, Any] | None:
        """최신 인바디를 조회한다. 기록이 없다는 의미의 data=null만 정상으로 허용한다."""
        data = await self._get_data("/internal/chatbot/tools/inbody/latest")
        if data is None:
            return None
        return self._validate_inbody(data)

    async def get_workout_history(
        self, from_date: date, to_date: date
    ) -> dict[str, Any]:
        """지정 기간의 운동일지를 조회하고, Spring 계약 DTO로 검증한 data만 반환한다."""
        data = await self._get_data(
            "/internal/chatbot/tools/workout-history",
            params={"from": from_date.isoformat(), "to": to_date.isoformat()},
        )
        return self._validate_workout_history(data)

    async def _get_data(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        """모든 도구가 공유하는 보안 헤더·상태 코드·envelope 검증 단계.

        재시도는 하지 않는다. active request의 유효 시간이 짧으므로 실패한 요청을
        FastAPI에서 반복하는 대신 오류를 상위 SSE 경로로 전달한다.
        """
        try:
            response = await self._http_client.get(
                path,
                params=params,
                headers={
                    # API key는 서버 간 인증, 나머지 두 값은 Spring의 세션 소유자/요청 만료 검증에 사용한다.
                    "X-Internal-Api-Key": get_settings().internal_api_key,
                    "X-Chatbot-Session-Id": self._context.session_id,
                    "X-Request-ID": self._context.request_id,
                },
            )
        except httpx.RequestError as exc:
            raise chatbot_tool_unavailable() from exc

        if response.status_code in (401, 403):
            raise chatbot_tool_access_denied(response.status_code)
        if response.status_code >= 500:
            raise chatbot_tool_unavailable()
        if response.status_code != 200:
            raise chatbot_tool_response_invalid(response.status_code)

        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise chatbot_tool_response_invalid() from exc

        if not isinstance(payload, dict) or "data" not in payload:
            raise chatbot_tool_response_invalid()
        return payload["data"]

    @staticmethod
    def _validate_inbody(data: Any) -> dict[str, Any]:
        """Spring data가 인바디 계약을 지킬 때만 alias(camelCase)를 유지해 반환한다."""
        try:
            return _InbodyData.model_validate(data).model_dump(by_alias=True, mode="json")
        except ValidationError as exc:
            raise chatbot_tool_response_invalid() from exc

    @staticmethod
    def _validate_workout_history(data: Any) -> dict[str, Any]:
        """잘못된 운동일지 근거가 LLM에 전달되지 않도록 필수 필드와 타입을 엄격히 검사한다."""
        try:
            return _WorkoutHistoryData.model_validate(data).model_dump(by_alias=True, mode="json")
        except ValidationError as exc:
            raise chatbot_tool_response_invalid() from exc
