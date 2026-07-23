"""ChromaDB 연결/설정. chroma_mode 설정값에 따라 개발환경(PersistentClient, 로컬 디스크)과
배포환경(HttpClient)을 전환한다 — 이 파일 밖은 전혀 안 바꿔도 된다.
PT추천 전용(app/pt_recommendation) — 공용 app/rag/는 챗봇 도메인 소유라 별도로 둔다."""

from functools import lru_cache

import chromadb

from app.core.settings import settings

COLLECTION_NAME = "pt_recommendation_documents"


class VectorStore:
    def __init__(self) -> None:
        if settings.chroma_mode == "http":
            self._client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
                settings=chromadb.Settings(
                    chroma_query_request_timeout_seconds=settings.chroma_timeout_seconds
                ),
            )
        else:
            self._client = chromadb.PersistentClient(path=str(settings.chroma_persist_directory))
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        self._collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def query(self, query_embedding: list[float], n_results: int, where: dict | None = None) -> dict:
        return self._collection.query(
            query_embeddings=[query_embedding], n_results=n_results, where=where
        )

    def delete(self, where: dict) -> None:
        self._collection.delete(where=where)

    def count(self) -> int:
        return self._collection.count()


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
