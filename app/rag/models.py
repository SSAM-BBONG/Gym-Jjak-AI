"""RAG 검색 결과의 provider 독립 모델. 벡터 저장소(Chroma)나 임베딩 provider가
바뀌어도 이 계약은 그대로 유지된다."""

from typing import Protocol

from pydantic import BaseModel, Field


class EmbeddingPort(Protocol):
    """텍스트를 벡터로 변환하는 계약. provider(Gemini 등)를 숨긴다."""

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """색인 대상 문서 여러 건을 한 번에 임베딩한다."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """검색 질의 1건을 임베딩한다."""
        ...


class RetrievedDocument(BaseModel):
    """검색 결과 chunk 1건. 항상 출처(source/title/category)를 동반한다."""

    document_id: str
    content: str
    score: float
    source: str
    title: str
    category: str
    keywords: list[str] = Field(default_factory=list)
