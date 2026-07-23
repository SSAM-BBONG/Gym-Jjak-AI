import json

import pytest

from app.core.exceptions import AppError
from app.llm.errors import LLMInvalidResponseError
from app.llm.models import LLMResponse
from app.pt_recommendation.chain import recommend_pt_courses
from app.pt_recommendation.schemas import PainOnset, PtCourseCandidate, UserProfile
from tests.fakes.llm import FakeLLMPort


def _candidates() -> list[PtCourseCandidate]:
    return [
        PtCourseCandidate(
            course_id=101,
            course_name="무릎 재활 집중 코스",
            trainer_id=1,
            trainer_name="김트레이너",
            bio="10년차 재활 전문 트레이너입니다.",
        ),
        PtCourseCandidate(
            course_id=202,
            course_name="근비대 8주 코스",
            trainer_id=2,
            trainer_name="이트레이너",
            bio="바디빌딩 대회 입상 경력의 근비대 전문 트레이너입니다.",
        ),
    ]


def _profile() -> UserProfile:
    return UserProfile(
        exercise_goal="근비대",
        exercise_period="6개월 미만",
        exercise_frequency="주 3회",
        pt_history_summary="PT 이력 없음 (첫 PT 등록 예정)",
    )


def _valid_response_text() -> str:
    return (
        '[{"course_id": 101, "course_name": "무릎 재활 집중 코스", '
        '"trainer_id": 1, "trainer_name": "김트레이너", "reason": "무릎 통증에 적합합니다."}]'
    )


async def test_recommend_pt_courses_parses_llm_json():
    fake_llm = FakeLLMPort(response=LLMResponse(text=_valid_response_text()))

    result = await recommend_pt_courses(
        llm=fake_llm,
        candidates=_candidates(),
        profile=_profile(),
        has_pain=True,
        pain_area="무릎",
        pain_onset=PainOnset.CHRONIC,
        training_chunks=["근비대 관련 가이드"],
        injury_chunks=["무릎 관련 가이드"],
    )

    assert len(result) == 1
    assert result[0].course_id == 101
    assert result[0].course_name == "무릎 재활 집중 코스"
    assert result[0].reason == "무릎 통증에 적합합니다."


async def test_recommend_pt_courses_includes_candidates_and_profile_in_prompt():
    fake_llm = FakeLLMPort(response=LLMResponse(text=_valid_response_text()))

    await recommend_pt_courses(
        llm=fake_llm,
        candidates=_candidates(),
        profile=_profile(),
        has_pain=True,
        pain_area="무릎",
        pain_onset=PainOnset.CHRONIC,
        training_chunks=["근비대 관련 가이드"],
        injury_chunks=["무릎 관련 가이드"],
    )

    sent_messages = fake_llm.received_messages[0]
    system_message = next(m for m in sent_messages if m.role == "system")
    user_message = next(m for m in sent_messages if m.role == "user")

    assert "PT 코스를 추천" in system_message.content
    assert "course_id=101" in user_message.content
    assert "근비대" in user_message.content
    assert "부위: 무릎, 시기: 만성(오래된 통증)" in user_message.content
    assert "근비대 관련 가이드" in user_message.content
    assert "무릎 관련 가이드" in user_message.content


async def test_recommend_pt_courses_reports_no_pain_when_has_pain_false():
    fake_llm = FakeLLMPort(response=LLMResponse(text=_valid_response_text()))

    await recommend_pt_courses(
        llm=fake_llm,
        candidates=_candidates(),
        profile=_profile(),
        has_pain=False,
        pain_area=None,
        pain_onset=None,
        training_chunks=[],
        injury_chunks=[],
    )

    user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user")
    assert "통증 없음" in user_message.content
    assert "(관련 참고 자료 없음)" in user_message.content


async def test_recommend_pt_courses_reports_unspecified_area_when_pain_area_none():
    """Q3-1에서 "그 외 부위"를 선택하면 pain_area=None이지만 has_pain=True인 경우."""
    fake_llm = FakeLLMPort(response=LLMResponse(text=_valid_response_text()))

    await recommend_pt_courses(
        llm=fake_llm,
        candidates=_candidates(),
        profile=_profile(),
        has_pain=True,
        pain_area=None,
        pain_onset=PainOnset.ACUTE,
        training_chunks=[],
        injury_chunks=[],
    )

    user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user")
    assert "특정 부위 명시 안 됨" in user_message.content
    assert "급성(최근에 다침)" in user_message.content


async def test_recommend_pt_courses_raises_when_text_missing():
    fake_llm = FakeLLMPort(response=LLMResponse(text=None))

    with pytest.raises(LLMInvalidResponseError):
        await recommend_pt_courses(
            llm=fake_llm,
            candidates=_candidates(),
            profile=_profile(),
            has_pain=False,
            pain_area=None,
            pain_onset=None,
            training_chunks=[],
            injury_chunks=[],
        )


async def test_recommend_pt_courses_raises_on_malformed_json():
    fake_llm = FakeLLMPort(response=LLMResponse(text="이건 JSON이 아닙니다"))

    with pytest.raises(AppError) as caught:
        await recommend_pt_courses(
            llm=fake_llm,
            candidates=_candidates(),
            profile=_profile(),
            has_pain=False,
            pain_area=None,
            pain_onset=None,
            training_chunks=[],
            injury_chunks=[],
        )
    assert caught.value.code == "PT_RECOMMENDATION_INVALID_RESULT"


async def test_recommend_pt_courses_filters_out_hallucinated_course_id():
    """후보 목록에 없는 course_id를 LLM이 지어내면 걸러내고, 다 걸러지면 에러여야 한다."""
    fake_llm = FakeLLMPort(
        response=LLMResponse(
            text='[{"course_id": 999, "course_name": "없는 코스", '
            '"trainer_id": 9, "trainer_name": "없는 트레이너", "reason": "지어낸 이유"}]'
        )
    )

    with pytest.raises(AppError) as caught:
        await recommend_pt_courses(
            llm=fake_llm,
            candidates=_candidates(),
            profile=_profile(),
            has_pain=False,
            pain_area=None,
            pain_onset=None,
            training_chunks=[],
            injury_chunks=[],
        )
    assert caught.value.code == "PT_RECOMMENDATION_INVALID_RESULT"


async def test_recommend_pt_courses_ignores_llm_provided_course_and_trainer_fields():
    """course_id가 유효해도 course_name/trainer_id/trainer_name은 LLM 값이 아니라
    후보 목록의 정본 값으로 채워야 한다(LLM이 다른 코스 정보와 뒤섞어 줘도 방지)."""
    fake_llm = FakeLLMPort(
        response=LLMResponse(
            text='[{"course_id": 101, "course_name": "가짜 이름", '
            '"trainer_id": 999, "trainer_name": "가짜 트레이너", "reason": "적합합니다."}]'
        )
    )

    result = await recommend_pt_courses(
        llm=fake_llm,
        candidates=_candidates(),
        profile=_profile(),
        has_pain=False,
        pain_area=None,
        pain_onset=None,
        training_chunks=[],
        injury_chunks=[],
    )

    assert result[0].course_name == "무릎 재활 집중 코스"
    assert result[0].trainer_id == 1
    assert result[0].trainer_name == "김트레이너"


async def test_recommend_pt_courses_dedupes_duplicate_course_ids():
    """같은 course_id가 여러 번 나오면 첫 번째만 남긴다."""
    fake_llm = FakeLLMPort(
        response=LLMResponse(
            text='[{"course_id": 101, "course_name": "무릎 재활 집중 코스", '
            '"trainer_id": 1, "trainer_name": "김트레이너", "reason": "이유1"},'
            '{"course_id": 101, "course_name": "무릎 재활 집중 코스", '
            '"trainer_id": 1, "trainer_name": "김트레이너", "reason": "이유2"}]'
        )
    )

    result = await recommend_pt_courses(
        llm=fake_llm,
        candidates=_candidates(),
        profile=_profile(),
        has_pain=False,
        pain_area=None,
        pain_onset=None,
        training_chunks=[],
        injury_chunks=[],
    )

    assert len(result) == 1
    assert result[0].reason == "이유1"


async def test_recommend_pt_courses_caps_at_three_recommendations():
    """LLM이 규칙(최대 3개)을 무시하고 더 많이 반환해도 코드가 3개로 제한한다."""
    candidates = _candidates() + [
        PtCourseCandidate(
            course_id=303, course_name="코스3", trainer_id=3, trainer_name="트레이너3", bio="설명3"
        ),
        PtCourseCandidate(
            course_id=404, course_name="코스4", trainer_id=4, trainer_name="트레이너4", bio="설명4"
        ),
    ]
    fake_llm = FakeLLMPort(
        response=LLMResponse(
            text=json.dumps(
                [{"course_id": c.course_id, "reason": f"이유{c.course_id}"} for c in candidates]
            )
        )
    )

    result = await recommend_pt_courses(
        llm=fake_llm,
        candidates=candidates,
        profile=_profile(),
        has_pain=False,
        pain_area=None,
        pain_onset=None,
        training_chunks=[],
        injury_chunks=[],
    )

    assert len(result) == 3
