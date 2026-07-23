"""LocalDevUserDataClient는 실제 서비스 코드가 아니라 로컬 Swagger 확인용 샘플이지만,
구독 활성/트레이너 접근 제한 같은 핵심 동작은 최소한으로 검증해둔다."""

import pytest

from app.common.dev_user_data import SAMPLE_TRAINER_ID, SAMPLE_USER_ID, LocalDevUserDataClient
from app.common.exceptions import SubjectAccessDeniedError


async def test_subscription_is_always_active() -> None:
    client = LocalDevUserDataClient()

    status = await client.get_subscription_status(SAMPLE_USER_ID)

    assert status.is_active is True


async def test_recent_workouts_are_within_default_four_weeks() -> None:
    client = LocalDevUserDataClient()

    workouts = await client.get_recent_workouts(SAMPLE_USER_ID)

    assert len(workouts) == 2


async def test_trainer_access_allowed_only_for_sample_pair() -> None:
    client = LocalDevUserDataClient()

    access = await client.assert_trainer_can_access(
        trainer_id=SAMPLE_TRAINER_ID, subject_user_id=SAMPLE_USER_ID
    )

    assert access.is_allowed is True


async def test_trainer_access_denied_for_other_pairs() -> None:
    client = LocalDevUserDataClient()

    with pytest.raises(SubjectAccessDeniedError):
        await client.assert_trainer_can_access(trainer_id=999, subject_user_id=SAMPLE_USER_ID)
