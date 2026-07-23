"""실제 Gemini API를 호출해서 LLM 호출부가 진짜로 동작하는지 확인하는 smoke test.
기본 pytest 실행에서는 스킵되고, pytest --run-smoke로만 실행된다."""

import time

import pytest

from app.core.dependencies import get_llm_client
from app.pt_recommendation.chain import recommend_pt_courses
from app.pt_recommendation.schemas import PainOnset, PtCourseCandidate, UserProfile


@pytest.mark.smoke
async def test_pt_recommendation_real_gemini_call():
    llm = get_llm_client()

    candidates = [
        PtCourseCandidate(
            course_id=101,
            course_name="무릎 재활 집중 코스",
            trainer_id=1,
            trainer_name="김트레이너",
            bio="10년차 재활 전문 트레이너입니다. 무릎 통증 회원 지도 경험이 많습니다.",
        ),
        PtCourseCandidate(
            course_id=202,
            course_name="근비대 8주 코스",
            trainer_id=2,
            trainer_name="이트레이너",
            bio="바디빌딩 대회 입상 경력의 근비대 전문 트레이너입니다.",
        ),
    ]
    profile = UserProfile(
        exercise_goal="근비대",
        exercise_period="6개월 미만",
        exercise_frequency="주 3회",
        pt_history_summary="PT 이력 없음 (첫 PT 등록 예정)",
    )

    start = time.monotonic()
    result = await recommend_pt_courses(
        llm=llm,
        candidates=candidates,
        profile=profile,
        has_pain=True,
        pain_area="무릎",
        pain_onset=PainOnset.CHRONIC,
        training_chunks=[],
        injury_chunks=[],
    )
    elapsed = time.monotonic() - start

    print(f"\n[smoke] 응답 시간: {elapsed:.2f}s, 추천 개수: {len(result)}")

    assert len(result) >= 1
    assert result[0].course_id in {101, 202}
