from datetime import date, timedelta
from decimal import Decimal

from app.routine.analyzer import WorkoutAnalyzer, analyze_inbody_trend
from tests.fixtures.user_data import inbody_record, workout_diary, workout_set


def diary(*, diary_date: date, part: str, exercise: str, sets: list) -> object:
    return workout_diary(diary_date=diary_date, part=part, exercise=exercise, sets=sets)


def test_analyzer_calculates_volume_and_part_frequency() -> None:
    today = date.today()
    diaries = [
        diary(
            diary_date=today,
            part="CHEST",
            exercise="벤치프레스",
            sets=[workout_set(1, 40, 10), workout_set(2, 40, 8)],
        ),
        diary(
            diary_date=today,
            part="CHEST",
            exercise="푸시업",
            sets=[workout_set(1, 0, 15)],
        ),
    ]

    result = WorkoutAnalyzer().analyze(diaries, today=today)

    assert result.total_volume == Decimal("720.00")
    assert result.part_session_counts["CHEST"] == 1


def test_analyzer_excludes_data_older_than_four_weeks() -> None:
    today = date.today()
    diaries = [
        diary(
            diary_date=today - timedelta(weeks=1),
            part="BACK",
            exercise="랫풀다운",
            sets=[workout_set(1, 30, 10)],
        ),
        diary(
            diary_date=today - timedelta(weeks=8),
            part="BACK",
            exercise="랫풀다운",
            sets=[workout_set(1, 30, 10)],
        ),
    ]

    result = WorkoutAnalyzer().analyze(diaries, today=today)

    assert result.part_session_counts["BACK"] == 1
    assert result.total_volume == Decimal("300.00")


def test_analyzer_counts_same_date_and_part_as_one_session() -> None:
    today = date.today()
    diaries = [
        diary(diary_date=today, part="LEG", exercise="스쿼트", sets=[workout_set(1, 50, 10)]),
        diary(diary_date=today, part="LEG", exercise="런지", sets=[workout_set(1, 20, 10)]),
    ]

    result = WorkoutAnalyzer().analyze(diaries, today=today)

    assert result.part_session_counts["LEG"] == 1


def test_analyzer_excludes_zero_weight_sets_from_volume_but_counts_session() -> None:
    today = date.today()
    diaries = [
        diary(diary_date=today, part="CORE", exercise="플랭크", sets=[workout_set(1, 0, 60)]),
    ]

    result = WorkoutAnalyzer().analyze(diaries, today=today)

    assert result.total_volume == Decimal("0.00")
    assert result.part_session_counts["CORE"] == 1


def test_weight_range_reported_when_enough_history() -> None:
    today = date.today()
    diaries = [
        diary(
            diary_date=today - timedelta(days=i),
            part="CHEST",
            exercise="벤치프레스",
            sets=[workout_set(1, 40 + i, 10)],
        )
        for i in range(3)
    ]

    result = WorkoutAnalyzer().analyze(diaries, today=today)

    assert result.exercise_weight_ranges["벤치프레스"] is not None
    assert result.exercise_weight_ranges["벤치프레스"].min_weight == Decimal("40")
    assert result.exercise_weight_ranges["벤치프레스"].max_weight == Decimal("42")


def test_weight_range_is_none_when_history_insufficient() -> None:
    today = date.today()
    diaries = [
        diary(diary_date=today, part="CHEST", exercise="벤치프레스", sets=[workout_set(1, 40, 10)]),
    ]

    result = WorkoutAnalyzer().analyze(diaries, today=today)

    assert result.exercise_weight_ranges["벤치프레스"] is None


def test_inbody_trend_computes_change_between_earliest_and_latest() -> None:
    today = date.today()
    records = [
        inbody_record(measured_at=today, weight=68, body_fat_percentage=18),
        inbody_record(measured_at=today - timedelta(days=60), weight=70, body_fat_percentage=20),
    ]

    trend = analyze_inbody_trend(records)

    assert trend.weight_change == Decimal("-2")
    assert trend.body_fat_change == Decimal("-2")
    assert trend.records_used == 2


def test_inbody_trend_handles_single_record() -> None:
    trend = analyze_inbody_trend([inbody_record(measured_at=date.today(), weight=70)])

    assert trend.weight_change is None
    assert trend.records_used == 1


def test_inbody_trend_handles_no_records() -> None:
    trend = analyze_inbody_trend([])

    assert trend.weight_change is None
    assert trend.records_used == 0
