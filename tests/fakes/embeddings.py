from app.rag.embeddings import EMBEDDING_DIMENSIONS


class FakeEmbeddings:
    """EmbeddingPort의 가짜 구현체. 실제 Gemini 호출 없이 고정 차원의 결정론적
    벡터를 반환한다. 텍스트 길이 기반이라 같은 입력은 항상 같은 벡터를 낸다."""

    def __init__(self) -> None:
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def _vector_for(self, text: str) -> list[float]:
        seed = len(text) or 1
        return [((i + seed) % 97) / 97 for i in range(EMBEDDING_DIMENSIONS)]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(texts)
        return [self._vector_for(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return self._vector_for(text)
