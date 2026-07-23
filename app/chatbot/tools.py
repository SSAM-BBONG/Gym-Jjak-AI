"""Spring 챗봇 내부 API를 위한 읽기 전용 Function Calling 도구 레지스트리."""

import json
from datetime import date
from typing import Any

from pydantic import BaseModel

from app.chatbot.spring_tool_client import SpringChatbotToolClient
from app.core.settings import get_settings

TOOL_NAMES = ("get_latest_inbody", "get_workout_history")
_ALLOWED_ARGS: dict[str, tuple[str, ...]] = {
    "get_latest_inbody": (),
    "get_workout_history": ("from", "to"),
}


class ToolResult(BaseModel):
    """모델에 전달할 도구명과 Spring 응답의 data만 담는다."""

    tool_name: str
    data: Any


class DuplicateToolCallError(Exception):
    """같은 도구를 같은 인자로 한 요청 안에서 다시 호출했을 때."""


class ToolCallLimitExceededError(Exception):
    """한 요청 안의 도구 호출 한도를 초과했을 때."""


class ToolArgumentValidationError(Exception):
    """LLM이 도구 schema를 벗어난 인자를 보냈을 때."""


def _canonical_key(tool_name: str, args: dict[str, Any]) -> str:
    return f"{tool_name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"


class ToolRegistry:
    """요청별 Spring 클라이언트로 두 도구만 실행한다.

    회원 신원은 모델 인자가 아닌 Spring의 세션/요청 헤더 검증으로 확정된다.
    """

    def __init__(self, *, client: SpringChatbotToolClient, call_limit: int | None = None) -> None:
        self._client = client
        self._call_limit = call_limit if call_limit is not None else get_settings().tool_call_limit
        self._call_count = 0
        self._visited: set[str] = set()

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Gemini에 공개할 Function Calling schema를 반환한다.

        schema 자체에 user_id를 두지 않는다. 모델은 기간이라는 업무 인자만 만들 수 있고,
        실제 조회 대상 회원은 Spring이 HTTP 헤더의 세션 정보로 확정한다.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_latest_inbody",
                    "description": "회원의 가장 최근 인바디 측정 기록을 조회합니다.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_workout_history",
                    "description": "지정한 기간의 회원 운동일지를 조회합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "string", "format": "date", "description": "조회 시작일"},
                            "to": {"type": "string", "format": "date", "description": "조회 종료일"},
                        },
                        "required": ["from", "to"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        """모델의 tool call을 Spring 내부 조회로 변환한다.

        동일 요청 안에서만 중복/호출 횟수를 추적한다. ToolRegistry는 ChatbotService가 매
        요청마다 새로 만들기 때문에 다른 회원이나 다른 대화의 호출 기록이 섞이지 않는다.
        """
        if tool_name not in TOOL_NAMES:
            return ToolResult(tool_name=tool_name, data={"error": "UNKNOWN_TOOL"})

        # schema 밖의 값은 실행 경계에서 다시 제거한다. 이중 방어로 LLM의 임의 인자가 Spring까지 가지 않는다.
        filtered_args = {key: value for key, value in args.items() if key in _ALLOWED_ARGS[tool_name]}
        key = _canonical_key(tool_name, filtered_args)
        if key in self._visited:
            raise DuplicateToolCallError(f"{tool_name} 재호출: {filtered_args}")
        if self._call_count >= self._call_limit:
            raise ToolCallLimitExceededError(f"도구 호출 한도({self._call_limit}회) 초과")

        if tool_name == "get_workout_history":
            from_date, to_date = self._parse_period(filtered_args)

        self._visited.add(key)
        self._call_count += 1
        if tool_name == "get_latest_inbody":
            return ToolResult(tool_name=tool_name, data=await self._client.get_latest_inbody())
        return ToolResult(
            tool_name=tool_name,
            data=await self._client.get_workout_history(from_date, to_date),
        )

    @staticmethod
    def _parse_period(args: dict[str, Any]) -> tuple[date, date]:
        """Spring과 동일하게 운동일지 조회 기간을 1~31일로 제한한다."""
        try:
            from_date = date.fromisoformat(args["from"])
            to_date = date.fromisoformat(args["to"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ToolArgumentValidationError("from/to는 ISO-8601 날짜여야 합니다.") from exc

        days = (to_date - from_date).days + 1
        if not 1 <= days <= 31:
            raise ToolArgumentValidationError("운동일지 조회 기간은 1일에서 31일 사이여야 합니다.")
        return from_date, to_date
