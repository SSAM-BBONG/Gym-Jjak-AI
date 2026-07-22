"""Gemini Embedding 어댑터. gemini-embedding-001, 출력 차원 768을 사용하고
문서는 RETRIEVAL_DOCUMENT, 질문은 RETRIEVAL_QUERY task type으로 호출한다.
오류 시 자동 재시도하지 않는다(LLM 호출 정책과 동일)."""

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.settings import settings

EMBEDDING_DIMENSIONS = 768


class GeminiEmbeddings:
    """EmbeddingPort 구현체. LangChain은 이 파일 안에서만 사용한다."""

    def __init__(self) -> None:
        self._model: GoogleGenerativeAIEmbeddings | None = None

    def _get_model(self) -> GoogleGenerativeAIEmbeddings:
        if self._model is not None:
            return self._model
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY 환경변수가 필요합니다.")
        self._model = GoogleGenerativeAIEmbeddings(
            model=f"models/{settings.gemini_embedding_model}",
            google_api_key=settings.gemini_api_key,
            output_dimensionality=EMBEDDING_DIMENSIONS,
        )
        return self._model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._get_model().aembed_documents(texts, task_type="RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return await self._get_model().aembed_query(text, task_type="RETRIEVAL_QUERY")
