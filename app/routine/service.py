"""회원 챗봇과 트레이너 분석이 공유하는 루틴 생성 Use Case.

회원 경로: role 확인 -> 구독 확인 -> 안전 검사(고위험이면 LLM 호출 전 BLOCKED) ->
개인 데이터 조회 -> 결정론적 분석 -> RAG 검색 -> LLM 구조화 출력 1회.

트레이너 경로: role 확인 -> 담당 회원 관계 확인 -> subject 회원의 온보딩/운동/인바디만
조회(결제·구독은 조회하지 않음) -> 상세 분석용 프롬프트로 LLM 구조화 출력 1회.
"""

from app.common.models import ActorContext, InBodyRecord, Role, WorkoutDiary
from app.common.user_data_client import UserDataClient
from app.llm.port import LLMPort
from app.rag.models import RetrievedDocument
from app.rag.retriever import RetrieverPort
from app.routine.analyzer import WorkoutAnalyzer, analyze_inbody_trend
from app.routine.exceptions import ActorRoleNotAllowedError
from app.routine.prompts import build_member_routine_prompt, build_trainer_routine_prompt
from app.routine.safety import assess_safety
from app.routine.schemas import RoutineRequest, RoutineResult, SourceReference

_TRAINER_DEFAULT_QUERY = "루틴 추천"


class RoutineService:
    """회원 챗봇과 트레이너 분석이 공유하는 루틴 생성 서비스."""

    def __init__(
        self,
        *,
        user_data: UserDataClient,
        analyzer: WorkoutAnalyzer,
        retriever: RetrieverPort,
        llm: LLMPort,
    ) -> None:
        self._user_data = user_data
        self._analyzer = analyzer
        self._retriever = retriever
        self._llm = llm

    async def recommend_for_member(
        self, *, actor: ActorContext, request: RoutineRequest
    ) -> RoutineResult:
        """회원용 루틴 추천. role/구독/안전 검사를 통과해야 LLM을 호출한다."""
        if actor.role != Role.USER:
            raise ActorRoleNotAllowedError()

        safety = assess_safety(request.message)
        if safety.status == "BLOCKED":
            return RoutineResult(
                status="BLOCKED",
                title="루틴 추천 불가",
                summary=safety.caution or "",
                days=[],
                cautions=[safety.caution] if safety.caution else [],
                missing_data=[],
                sources=[],
            )

        onboarding = await self._user_data.get_onboarding(actor.user_id)
        workouts = await self._user_data.get_recent_workouts(actor.user_id)
        inbody = await self._user_data.get_recent_inbody(actor.user_id)

        missing_data = self._missing_data(workouts, inbody)
        analysis = self._analyzer.analyze(workouts)
        inbody_trend = analyze_inbody_trend(inbody)
        documents = await self._retriever.search(
            request.message, category="routine", keywords=[], top_k=3
        )

        prompt = build_member_routine_prompt(
            message=request.message,
            onboarding=onboarding,
            analysis=analysis,
            inbody_trend=inbody_trend,
            documents=documents,
            safety_caution=safety.caution,
        )
        result = await self._llm.generate_structured(prompt=prompt, output_schema=RoutineResult)
        return self._finalize(result, missing_data=missing_data, documents=documents, extra_caution=safety.caution)

    async def recommend_for_trainer(
        self, *, actor: ActorContext, subject_user_id: int
    ) -> RoutineResult:
        """트레이너용 상세 루틴 분석. 담당 회원 관계를 확인한 뒤 결제/구독 정보 없이 진행한다."""
        if actor.role != Role.TRAINER:
            raise ActorRoleNotAllowedError()

        await self._user_data.assert_trainer_can_access(
            trainer_id=actor.user_id, subject_user_id=subject_user_id
        )

        onboarding = await self._user_data.get_onboarding(subject_user_id)
        workouts = await self._user_data.get_recent_workouts(subject_user_id)
        inbody = await self._user_data.get_recent_inbody(subject_user_id)

        missing_data = self._missing_data(workouts, inbody)
        analysis = self._analyzer.analyze(workouts)
        inbody_trend = analyze_inbody_trend(inbody)
        documents = await self._retriever.search(
            _TRAINER_DEFAULT_QUERY, category="routine", keywords=[], top_k=3
        )

        prompt = build_trainer_routine_prompt(
            subject_user_id=subject_user_id,
            onboarding=onboarding,
            analysis=analysis,
            inbody_trend=inbody_trend,
            documents=documents,
        )
        result = await self._llm.generate_structured(prompt=prompt, output_schema=RoutineResult)
        return self._finalize(result, missing_data=missing_data, documents=documents, extra_caution=None)

    @staticmethod
    def _missing_data(workouts: list[WorkoutDiary], inbody: list[InBodyRecord]) -> list[str]:
        """운동일지/인바디 중 비어 있는 항목의 이름을 모은다."""
        missing = []
        if not workouts:
            missing.append("workout_diaries")
        if not inbody:
            missing.append("inbody")
        return missing

    @staticmethod
    def _finalize(
        result: RoutineResult,
        *,
        missing_data: list[str],
        documents: list[RetrievedDocument],
        extra_caution: str | None,
    ) -> RoutineResult:
        """LLM 결과의 status/missing_data/sources를 서버가 결정론적으로 덮어쓴다.
        source는 LLM이 지어내지 않도록 항상 서버가 채운다."""
        sources = [
            SourceReference(source=d.source, title=d.title, category=d.category) for d in documents
        ]
        cautions = list(result.cautions)
        if extra_caution and extra_caution not in cautions:
            cautions = [extra_caution] + cautions
        status = "LIMITED" if missing_data else "COMPLETE"
        return result.model_copy(
            update={
                "status": status,
                "missing_data": missing_data,
                "sources": sources,
                "cautions": cautions,
            }
        )
