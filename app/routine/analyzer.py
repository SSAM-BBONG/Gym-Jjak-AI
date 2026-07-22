"""운동기록·인바디 결정론적 계산. LLM에 넘기기 전에 사실 관계(볼륨, 세션 빈도,
과거 중량 범위, 인바디 변화량)를 코드로 확정해, 모델이 수치를 추측하지 않게 한다."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

from app.common.models import InBodyRecord, WorkoutDiary

RECENT_WEEKS = 4
MIN_HISTORY_SETS_FOR_WEIGHT_RANGE = 3
TWO_PLACES = Decimal("0.01")


class WeightRange(BaseModel):
    min_weight: Decimal
    max_weight: Decimal


class WorkoutAnalysisResult(BaseModel):
    total_volume: Decimal
    part_session_counts: dict[str, int]
    exercise_weight_ranges: dict[str, WeightRange | None]


class InBodyTrend(BaseModel):
    weight_change: Decimal | None
    body_fat_change: Decimal | None
    records_used: int


class WorkoutAnalyzer:
    def analyze(
        self,
        diaries: list[WorkoutDiary],
        *,
        today: date | None = None,
    ) -> WorkoutAnalysisResult:
        reference_date = today or date.today()
        cutoff = reference_date - timedelta(weeks=RECENT_WEEKS)
        recent = [d for d in diaries if d.diary_date >= cutoff]

        total_volume = Decimal("0")
        sessions: set[tuple[date, str]] = set()
        exercise_weights: dict[str, list[Decimal]] = {}

        for diary in recent:
            sessions.add((diary.diary_date, diary.part))
            weights = exercise_weights.setdefault(diary.exercise, [])
            for workout_set in diary.sets:
                if workout_set.weight > 0:
                    total_volume += workout_set.weight * workout_set.reps
                    weights.append(workout_set.weight)

        part_session_counts: dict[str, int] = {}
        for _, part in sessions:
            part_session_counts[part] = part_session_counts.get(part, 0) + 1

        exercise_weight_ranges: dict[str, WeightRange | None] = {}
        for exercise, weights in exercise_weights.items():
            if len(weights) >= MIN_HISTORY_SETS_FOR_WEIGHT_RANGE:
                exercise_weight_ranges[exercise] = WeightRange(
                    min_weight=min(weights), max_weight=max(weights)
                )
            else:
                exercise_weight_ranges[exercise] = None

        return WorkoutAnalysisResult(
            total_volume=total_volume.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            part_session_counts=part_session_counts,
            exercise_weight_ranges=exercise_weight_ranges,
        )


def analyze_inbody_trend(records: list[InBodyRecord]) -> InBodyTrend:
    if len(records) < 2:
        return InBodyTrend(weight_change=None, body_fat_change=None, records_used=len(records))

    ordered = sorted(records, key=lambda r: r.measured_at)
    earliest, latest = ordered[0], ordered[-1]

    body_fat_change = None
    if earliest.body_fat_percentage is not None and latest.body_fat_percentage is not None:
        body_fat_change = latest.body_fat_percentage - earliest.body_fat_percentage

    return InBodyTrend(
        weight_change=latest.weight - earliest.weight,
        body_fat_change=body_fat_change,
        records_used=len(records),
    )
