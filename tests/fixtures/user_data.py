"""tests/fakes/user_data.py의 FakeUserDataClient를 채울 샘플 데이터 빌더.
app/common은 챗봇 도메인이 신설·소유하므로 diet/trainer_report와 겹치지 않는다."""

from datetime import date
from decimal import Decimal

from app.common.models import InBodyRecord, WorkoutDiary, WorkoutSet


def workout_set(set_number: int, weight: float, reps: int) -> WorkoutSet:
    return WorkoutSet(set_number=set_number, weight=Decimal(str(weight)), reps=reps)


def workout_diary(
    *,
    diary_date: date,
    part: str,
    exercise: str,
    sets: list[WorkoutSet],
) -> WorkoutDiary:
    return WorkoutDiary(diary_date=diary_date, part=part, exercise=exercise, sets=sets)


def inbody_record(
    *,
    measured_at: date,
    weight: float,
    body_fat_percentage: float | None = None,
) -> InBodyRecord:
    return InBodyRecord(
        measured_at=measured_at,
        weight=Decimal(str(weight)),
        body_fat_percentage=(
            Decimal(str(body_fat_percentage)) if body_fat_percentage is not None else None
        ),
    )
