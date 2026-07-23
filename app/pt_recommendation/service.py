import asyncio

from app.llm.port import LLMPort
from app.pt_recommendation.chain import recommend_pt_courses
from app.pt_recommendation.rag import retriever
from app.pt_recommendation.schemas import PtRecommendationRequest, PtRecommendationResponse


class PtRecommendationService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def recommend(self, request: PtRecommendationRequest) -> PtRecommendationResponse:
        """1차 필터링(부위·거리)과 온보딩/PT이력 조회는 Spring이 이미 끝내고 후보·프로필을
        요청에 번들로 실어 보낸다(diet/trainer_report와 동일한 패턴) — 여기서는
        RAG 검색과 LLM 호출만 담당한다."""

        # retriever.search()는 동기 함수(Gemini 임베딩 호출 + Chroma 쿼리라 수 초 소요)라
        # 스레드로 넘겨서 이벤트 루프가 다른 요청을 막지 않게 한다.
        training_chunks = await asyncio.to_thread(
            retriever.search, query=request.profile.exercise_goal, category="training_guide"
        )
        # "그 외 부위"(pain_area=None)면 injury_guide 문서와 매칭할 구체적 부위가 없으므로 검색 자체를 생략한다.
        injury_chunks = (
            await asyncio.to_thread(retriever.search, query=request.pain_area, category="injury_guide")
            if request.pain_area
            else []
        )

        recommendations = await recommend_pt_courses(
            llm=self._llm,
            candidates=request.candidates,
            profile=request.profile,
            has_pain=request.has_pain,
            pain_area=request.pain_area,
            pain_onset=request.pain_onset,
            training_chunks=training_chunks,
            injury_chunks=injury_chunks,
        )
        return PtRecommendationResponse(recommendations=recommendations)
