import json

from pydantic import ValidationError

from app.llm.errors import LLMInvalidResponseError
from app.llm.models import LLMMessage
from app.llm.port import LLMPort
from app.pt_recommendation.errors import invalid_recommendation_result
from app.pt_recommendation.prompts import PT_RECOMMENDATION_SYSTEM_PROMPT
from app.pt_recommendation.schemas import (
    PainOnset,
    RecommendedTrainer,
    TrainerCandidate,
    UserProfile,
)

_ONSET_LABELS = {
    PainOnset.ACUTE: "급성(최근에 다침)",
    PainOnset.SUBACUTE: "아급성(회복 중)",
    PainOnset.CHRONIC: "만성(오래된 통증)",
}


def _format_candidates(candidates: list[TrainerCandidate]) -> str:
    return "\n".join(
        f"- trainer_id={c.trainer_id}, 이름={c.trainer_name}, 소개: {c.bio}"
        for c in candidates
    )


def _format_profile(profile: UserProfile) -> str:
    return (
        f"운동 목표: {profile.exercise_goal}\n"
        f"운동 경력: {profile.exercise_period}\n"
        f"운동 빈도: {profile.exercise_frequency}\n"
        f"PT 이력: {profile.pt_history_summary}"
    )


def _format_pain(has_pain: bool, pain_area: str | None, pain_onset: PainOnset | None) -> str:
    if not has_pain:
        return "통증 없음"
    area = pain_area or "특정 부위 명시 안 됨"
    return f"부위: {area}, 시기: {_ONSET_LABELS[pain_onset]}"


def _format_reference_docs(training_chunks: list[str], injury_chunks: list[str]) -> str:
    sections = []
    if training_chunks:
        sections.append("[운동 목표별 트레이닝 가이드]\n" + "\n---\n".join(training_chunks))
    if injury_chunks:
        sections.append("[통증 부위별 주의사항]\n" + "\n---\n".join(injury_chunks))
    return "\n\n".join(sections) if sections else "(관련 참고 자료 없음)"


def _parse_response(text: str, candidates: list[TrainerCandidate]) -> list[RecommendedTrainer]:
    """generate_structured가 아직 공용 포트에 없어 프롬프트로 JSON 출력을 강제하고 여기서
    직접 파싱한다. candidates에 없는 trainer_id는 LLM이 지어낸 것으로 보고 걸러낸다."""

    valid_ids = {c.trainer_id for c in candidates}
    try:
        raw = json.loads(text)
        recommendations = [RecommendedTrainer.model_validate(item) for item in raw]
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise invalid_recommendation_result() from exc

    recommendations = [r for r in recommendations if r.trainer_id in valid_ids]
    if not recommendations:
        raise invalid_recommendation_result()
    return recommendations


async def recommend_trainers(
    llm: LLMPort,
    candidates: list[TrainerCandidate],
    profile: UserProfile,
    has_pain: bool,
    pain_area: str | None,
    pain_onset: PainOnset | None,
    training_chunks: list[str],
    injury_chunks: list[str],
) -> list[RecommendedTrainer]:
    """후보 트레이너 + 회원 프로필 + RAG 참고자료를 종합해서 LLM이 최적 후보를 선정하고
    추천 이유를 생성한다."""

    user_content = (
        f"[후보 트레이너 목록]\n{_format_candidates(candidates)}\n\n"
        f"[회원 프로필]\n{_format_profile(profile)}\n\n"
        f"[통증 정보]\n{_format_pain(has_pain, pain_area, pain_onset)}\n\n"
        f"[참고 자료]\n{_format_reference_docs(training_chunks, injury_chunks)}"
    )

    messages = [
        LLMMessage(role="system", content=PT_RECOMMENDATION_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]

    response = await llm.generate(messages)
    if response.text is None:
        raise LLMInvalidResponseError("PT 추천 생성 결과에 text가 없습니다.")

    return _parse_response(response.text, candidates)
