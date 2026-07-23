from datetime import date, timedelta

import pytest

from app.common.exceptions import SubjectAccessDeniedError
from tests.fakes.user_data import FakeUserDataClient
from tests.fixtures.user_data import workout_diary, workout_set


async def test_trainer_cannot_read_unassigned_member() -> None:
    client = FakeUserDataClient(trainer_subject_access={(20, 10)})

    with pytest.raises(SubjectAccessDeniedError):
        await client.assert_trainer_can_access(trainer_id=20, subject_user_id=999)


async def test_trainer_can_read_assigned_member() -> None:
    client = FakeUserDataClient(trainer_subject_access={(20, 10)})

    access = await client.assert_trainer_can_access(trainer_id=20, subject_user_id=10)

    assert access.is_allowed is True
    assert access.trainer_id == 20
    assert access.subject_user_id == 10


async def test_workouts_are_limited_to_recent_four_weeks() -> None:
    today = date.today()
    recent = workout_diary(
        diary_date=today - timedelta(weeks=1),
        part="CHEST",
        exercise="벤치프레스",
        sets=[workout_set(1, 40, 10)],
    )
    old = workout_diary(
        diary_date=today - timedelta(weeks=8),
        part="CHEST",
        exercise="벤치프레스",
        sets=[workout_set(1, 40, 10)],
    )
    client = FakeUserDataClient(workout_diaries={10: [recent, old]})

    result = await client.get_recent_workouts(user_id=10, weeks=4)

    assert result == [recent]
    assert all(item.diary_date >= today - timedelta(weeks=4) for item in result)
