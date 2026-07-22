"""RAG 검색 결과의 provider 독립 모델. 벡터 저장소(Chroma)나 임베딩 provider가
바뀌어도 이 계약은 그대로 유지된다."""

from typing import Protocol

from pydantic import BaseModel, Field


class EmbeddingPort(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class RetrievedDocument(BaseModel):
    document_id: str
    content: str
    score: float
    source: str
    title: str
    category: str
    keywords: list[str] = Field(default_factory=list)
