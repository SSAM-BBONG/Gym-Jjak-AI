"""질문 + 카테고리 필터 -> 관련 문서 조각 반환. 출처 metadata가 없는 chunk는
결과에서 제외하고 경고 로그만 남긴다. Chroma distance는 score = 1 - distance로 정규화한다."""

import logging
from typing import Protocol

from chromadb.api.models.Collection import Collection

from app.rag.models import EmbeddingPort, RetrievedDocument

logger = logging.getLogger(__name__)


class RetrieverPort(Protocol):
    """카테고리 필터 + 키워드 힌트로 관련 문서를 검색하는 계약."""

    async def search(
        self,
        query: str,
        *,
        category: str | None,
        keywords: list[str],
        top_k: int = 3,
    ) -> list[RetrievedDocument]: ...


class ChromaRetriever:
    """RetrieverPort의 Chroma 구현체."""

    def __init__(self, collection: Collection, embeddings: EmbeddingPort) -> None:
        self._collection = collection
        self._embeddings = embeddings

    async def search(
        self,
        query: str,
        *,
        category: str | None = None,
        keywords: list[str] | None = None,
        top_k: int = 3,
    ) -> list[RetrievedDocument]:
        """질의를 임베딩해 category로 필터링한 뒤 top_k개를 반환한다.
        source metadata가 없는 chunk는 결과에서 제외하고 경고 로그만 남긴다."""
        # 키워드는 사용자에게 노출되지 않는 검색 힌트로만 쿼리에 결합한다.
        search_text = " ".join([query, *(keywords or [])])
        query_vector = await self._embeddings.embed_query(search_text)

        where = {"category": category} if category else None
        raw = self._collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = raw["ids"][0]
        documents = raw["documents"][0]
        metadatas = raw["metadatas"][0]
        distances = raw["distances"][0]

        results: list[RetrievedDocument] = []
        for chunk_id, content, metadata, distance in zip(ids, documents, metadatas, distances):
            source = metadata.get("source")
            if not source:
                logger.warning("rag_missing_source_metadata chunk_id=%s", chunk_id)
                continue
            keywords_str = metadata.get("keywords", "")
            results.append(
                RetrievedDocument(
                    document_id=chunk_id,
                    content=content,
                    score=1 - distance,
                    source=source,
                    title=metadata.get("title", ""),
                    category=metadata.get("category", ""),
                    keywords=[k for k in keywords_str.split(",") if k],
                )
            )
        return results
