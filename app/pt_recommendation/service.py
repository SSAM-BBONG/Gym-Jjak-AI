from app.common import user_data_client
from app.llm.port import LLMPort
from app.pt_recommendation.chain import recommend_trainers
from app.pt_recommendation.errors import no_candidates_found
from app.pt_recommendation.schemas import (
    PtRecommendationRequest,
    PtRecommendationResponse,
    UserProfile,
)
from app.rag import retriever


class PtRecommendationService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def recommend(self, request: PtRecommendationRequest) -> PtRecommendationResponse:
        candidates = await user_data_client.search_trainers(
            user_id=request.user_id,
            target_parts=request.target_parts,
            distance_level=request.distance_level,
        )
        if not candidates:
            raise no_candidates_found()

        onboarding = await user_data_client.get_onboarding_profile(request.user_id)
        pt_history_summary = await user_data_client.get_pt_history_summary(request.user_id)
        profile = UserProfile(
            exercise_goal=onboarding["exercise_goal"],
            exercise_period=onboarding["exercise_period"],
            exercise_frequency=onboarding["exercise_frequency"],
            pt_history_summary=pt_history_summary,
        )

        training_chunks = retriever.search(query=profile.exercise_goal, category="training_guide")
        # "그 외 부위"(pain_area=None)면 injury_guide 문서와 매칭할 구체적 부위가 없으므로 검색 자체를 생략한다.
        injury_chunks = (
            retriever.search(query=request.pain_area, category="injury_guide")
            if request.pain_area
            else []
        )

        recommendations = await recommend_trainers(
            llm=self._llm,
            candidates=candidates,
            profile=profile,
            has_pain=request.has_pain,
            pain_area=request.pain_area,
            pain_onset=request.pain_onset,
            training_chunks=training_chunks,
            injury_chunks=injury_chunks,
        )
        return PtRecommendationResponse(recommendations=recommendations)
