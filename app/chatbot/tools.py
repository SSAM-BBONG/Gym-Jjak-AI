"""읽기 전용 Function Calling 도구 실행기.

도구 JSON Schema(LangChain에 bind_tools로 노출할 스키마)에는 user_id/trainer_id/
subject_user_id를 두지 않는다. 실행 시에는 항상 ToolExecutionContext.actor.user_id만
사용하고, 모델이 args로 흘려보낸 신원 관련 값은 execute()가 전부 걸러낸다.
쓰기/취소/해지/예약 실행 도구는 이 레지스트리에 등록하지 않는다."""

import json
from typing import Any

from pydantic import BaseModel

from app.common.models import ActorContext
from app.common.user_data_client import UserDataClient
from app.core.settings import get_settings

TOOL_NAMES = (
    "get_payment_history",
    "get_pt_usage",
    "get_pt_history",
    "get_subscription_status",
    "get_onboarding",
    "get_recent_workouts",
    "get_recent_inbody",
)

# 도구별로 모델이 넘길 수 있는 "업무" 인자만 허용한다. user_id 같은 신원 키는
# 목록에 없으므로 execute()가 무조건 걸러낸다.
_ALLOWED_ARGS: dict[str, tuple[str, ...]] = {
    "get_payment_history": (),
    "get_pt_usage": (),
    "get_pt_history": (),
    "get_subscription_status": (),
    "get_onboarding": (),
    "get_recent_workouts": ("weeks",),
    "get_recent_inbody": ("months", "limit"),
}


class ToolExecutionContext(BaseModel):
    """도구 실행 시 서버가 고정하는 신원 컨텍스트. 모델이 만들거나 바꾸지 못한다."""

    actor: ActorContext


class ToolResult(BaseModel):
    """도구 실행 결과. user_id는 항상 서버 컨텍스트 값이며 모델이 넘긴 값이 아니다."""

    tool_name: str
    user_id: int
    data: Any


class DuplicateToolCallError(Exception):
    """같은 도구를 같은(신원 제외) 인자로 이미 이번 요청 안에서 호출했을 때."""


class ToolCallLimitExceededError(Exception):
    """한 요청 안에서 도구 호출 한도(settings.tool_call_limit)를 초과했을 때."""


def _canonical_key(tool_name: str, args: dict[str, Any]) -> str:
    """중복 호출 판정용 키. 정렬된 JSON이라 인자 순서가 달라도 같은 키가 된다."""
    return f"{tool_name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"


class ToolRegistry:
    """읽기 전용 개인 데이터 조회 도구 7종을 실행한다.

    한 채팅 요청(그래프 실행 1회)마다 새로 만들어서, 호출 횟수와 중복 호출을
    "이번 요청 범위 안에서만" 추적한다. 인스턴스를 요청 간에 재사용하지 않는다."""

    def __init__(
        self,
        *,
        user_data: UserDataClient,
        context: ToolExecutionContext,
        call_limit: int | None = None,
    ) -> None:
        self._user_data = user_data
        self._context = context
        self._call_limit = call_limit if call_limit is not None else get_settings().tool_call_limit
        self._call_count = 0
        self._visited: set[str] = set()

    async def execute(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        """도구를 실행한다.

        - 등록되지 않은 도구명은 예외를 던지지 않고 {"error": "UNKNOWN_TOOL"} 결과를 반환한다
          (그래프가 이 결과를 모델에게 다시 보여줄 수 있게).
        - 동일 (도구, 허용된 인자) 조합 재호출은 DuplicateToolCallError.
        - 호출 한도 초과는 ToolCallLimitExceededError.
        """
        if tool_name not in TOOL_NAMES:
            return ToolResult(
                tool_name=tool_name,
                user_id=self._context.actor.user_id,
                data={"error": "UNKNOWN_TOOL"},
            )

        # 모델이 무엇을 보내든 신원 관련 키는 버리고, 도구별로 허용된 업무 인자만 남긴다.
        allowed = _ALLOWED_ARGS[tool_name]
        filtered_args = {k: v for k, v in args.items() if k in allowed}

        key = _canonical_key(tool_name, filtered_args)
        if key in self._visited:
            raise DuplicateToolCallError(f"{tool_name} 재호출: {filtered_args}")
        if self._call_count >= self._call_limit:
            raise ToolCallLimitExceededError(f"도구 호출 한도({self._call_limit}회) 초과")

        self._visited.add(key)
        self._call_count += 1

        user_id = self._context.actor.user_id
        data = await self._dispatch(tool_name, user_id, filtered_args)
        return ToolResult(tool_name=tool_name, user_id=user_id, data=data)

    async def _dispatch(self, tool_name: str, user_id: int, args: dict[str, Any]) -> Any:
        """실제 UserDataClient 호출과 최소 필드 직렬화를 담당한다."""
        if tool_name == "get_payment_history":
            items = await self._user_data.get_payment_history(user_id)
            return [item.model_dump(mode="json") for item in items]
        if tool_name == "get_pt_usage":
            usage = await self._user_data.get_pt_usage(user_id)
            return usage.model_dump(mode="json")
        if tool_name == "get_pt_history":
            items = await self._user_data.get_pt_history(user_id)
            return [item.model_dump(mode="json") for item in items]
        if tool_name == "get_subscription_status":
            status = await self._user_data.get_subscription_status(user_id)
            return status.model_dump(mode="json")
        if tool_name == "get_onboarding":
            profile = await self._user_data.get_onboarding(user_id)
            return profile.model_dump(mode="json") if profile else None
        if tool_name == "get_recent_workouts":
            weeks = args.get("weeks", 4)
            items = await self._user_data.get_recent_workouts(user_id, weeks=weeks)
            return [item.model_dump(mode="json") for item in items]
        if tool_name == "get_recent_inbody":
            months = args.get("months", 6)
            limit = args.get("limit", 6)
            items = await self._user_data.get_recent_inbody(user_id, months=months, limit=limit)
            return [item.model_dump(mode="json") for item in items]
        # TOOL_NAMES와 _ALLOWED_ARGS가 항상 동기화되어 있어야 하므로 여기 도달하면 구현 버그다.
        raise AssertionError(f"unreachable: {tool_name}")
