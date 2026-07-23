from httpx import ASGITransport, AsyncClient

from app.chatbot.dependencies import get_routine_service
from app.common.exceptions import SubjectAccessDeniedError
from app.routine.schemas import RoutineDay, RoutineExercise, RoutineResult
from main import app

_HEADERS = {"X-Internal-Api-Key": "local-development-only"}


def _sample_result() -> RoutineResult:
    return RoutineResult(
        status="COMPLETE", title="상세 루틴", summary="담당 회원 상세 분석",
        days=[
            RoutineDay(
                day_label="Day 1", goal="전신", warm_up=["스트레칭"],
                exercises=[
                    RoutineExercise(
                        name="스쿼트", part="LEG", sets=3, reps="10회",
                        intensity="중강도", rest_seconds=60, rationale="근거",
                    )
                ],
                cool_down=["스트레칭"],
            )
        ],
        cautions=[], missing_data=[], sources=[],
    )


def _payload(**overrides) -> dict:
    payload = {"actor": {"user_id": 20, "role": "TRAINER"}, "subject_user_id": 10}
    payload.update(overrides)
    return payload


class FakeRoutineService:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.received: list = []

    async def recommend_for_trainer(self, *, actor, subject_user_id):
        self.received.append((actor, subject_user_id))
        if self.error:
            raise self.error
        return self.result


async def test_trainer_routine_analysis_returns_result() -> None:
    fake = FakeRoutineService(result=_sample_result())
    app.dependency_overrides[get_routine_service] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/routines/trainer-analysis", headers=_HEADERS, json=_payload()
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["title"] == "상세 루틴"
    assert fake.received == [(fake.received[0][0], 10)]


async def test_trainer_routine_analysis_requires_subject_user_id() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/routines/trainer-analysis",
            headers=_HEADERS,
            json={"actor": {"user_id": 20, "role": "TRAINER"}},
        )

    assert response.status_code == 422


async def test_trainer_routine_analysis_denies_unassigned_member() -> None:
    fake = FakeRoutineService(error=SubjectAccessDeniedError())
    app.dependency_overrides[get_routine_service] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/routines/trainer-analysis", headers=_HEADERS, json=_payload()
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["code"] == "TRAINER_SUBJECT_ACCESS_DENIED"


async def test_trainer_routine_analysis_requires_internal_api_key() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/routines/trainer-analysis", json=_payload())

    assert response.status_code == 401
