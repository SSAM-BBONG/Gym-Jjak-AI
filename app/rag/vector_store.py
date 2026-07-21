"""ChromaDB 연결/설정. 개발환경은 PersistentClient(로컬 디스크)를 사용한다.
배포환경(HttpClient 전환)은 이 파일과 설정만 바꾸면 되도록 격리한다."""

from functools import lru_cache

import chromadb

PERSIST_DIRECTORY = "data/indexes/chroma"
COLLECTION_NAME = "pt_recommendation_documents"


class VectorStore:
    def __init__(self, persist_directory: str = PERSIST_DIRECTORY) -> None:
        self._client = chromadb.PersistentClient(path=persist_directory)
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

    def count(self) -> int:
        return self._collection.count()


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
