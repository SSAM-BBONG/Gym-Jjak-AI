"""챗봇의 고정 선택지와 루틴 선호도 해석 규칙."""

import json

from pydantic import BaseModel, Field

from app.chatbot.schemas import QuickReply
from app.common.conversation import ConversationContext

GREETING_MESSAGE = (
    "안녕하세요. 짐짝 AI입니다. 궁금한 내용을 선택해 주세요."
)

_GREETING_REPLIES = [
    QuickReply(question_id="GREETING_ACTION", label="서비스 이용 문의", value="SERVICE_POLICY"),
    QuickReply(question_id="GREETING_ACTION", label="루틴 추천", value="ROUTINE_RECOMMENDATION"),
    QuickReply(question_id="GREETING_ACTION", label="운동 기록 확인", value="PERSONAL_RECORD"),
]

_ROUTINE_GOAL_REPLIES = [
    QuickReply(question_id="ROUTINE_GOAL", label="근육 증가", value="MUSCLE_GAIN"),
    QuickReply(question_id="ROUTINE_GOAL", label="체지방 감량", value="FAT_LOSS"),
    QuickReply(question_id="ROUTINE_GOAL", label="체력 향상", value="FITNESS"),
]

_ROUTINE_DAYS_REPLIES = [
    QuickReply(question_id="ROUTINE_DAYS_PER_WEEK", label="주 2회", value="TWO"),
    QuickReply(question_id="ROUTINE_DAYS_PER_WEEK", label="주 3회", value="THREE"),
    QuickReply(question_id="ROUTINE_DAYS_PER_WEEK", label="주 4회 이상", value="FOUR_PLUS"),
]

_ROUTINE_LOCATION_REPLIES = [
    QuickReply(question_id="ROUTINE_LOCATION", label="헬스장", value="GYM"),
    QuickReply(question_id="ROUTINE_LOCATION", label="집", value="HOME"),
    QuickReply(question_id="ROUTINE_LOCATION", label="둘 다 가능", value="BOTH"),
]

_QUESTION_TEXT = {
    "ROUTINE_GOAL": "더 맞춤 추천을 위해 운동 목표를 선택해 주세요.",
    "ROUTINE_DAYS_PER_WEEK": "일주일에 가능한 운동 횟수를 선택해 주세요.",
    "ROUTINE_LOCATION": "주로 어디에서 운동하시나요?",
}


class RoutinePreference(BaseModel):
    """Spring의 ROUTINE_PREFERENCE value에 저장되는 선택값 부분집합."""

    goal: str | None = None
    days_per_week: str | None = Field(default=None, alias="daysPerWeek")
    location: str | None = None

    def has_selected_value(self) -> bool:
        return any((self.goal, self.days_per_week, self.location))


def greeting_replies() -> list[QuickReply]:
    return list(_GREETING_REPLIES)


def parse_routine_preference(contexts: list[ConversationContext]) -> RoutinePreference:
    value = next((context.value for context in contexts if context.kind == "ROUTINE_PREFERENCE"), None)
    if value is None:
        return RoutinePreference()
    try:
        return RoutinePreference.model_validate(json.loads(value))
    except (TypeError, ValueError):
        return RoutinePreference()


def next_routine_replies(preference: RoutinePreference) -> list[QuickReply]:
    if preference.goal is None:
        return list(_ROUTINE_GOAL_REPLIES)
    if preference.days_per_week is None:
        return list(_ROUTINE_DAYS_REPLIES)
    if preference.location is None:
        return list(_ROUTINE_LOCATION_REPLIES)
    return []


def question_text(replies: list[QuickReply]) -> str:
    return _QUESTION_TEXT[replies[0].question_id] if replies else ""
