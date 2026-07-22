"""Chroma 클라이언트 조립. local/test는 PersistentClient, production은 HttpClient를
사용한다. 컬렉션 이름과 거리 함수는 환경과 무관하게 고정한다."""

from typing import Callable

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

from app.core.settings import Settings

COLLECTION_NAME = "gym_jjak_knowledge_v1"


def create_chroma_client(
    settings: Settings,
    *,
    persistent_factory: Callable[..., ClientAPI] = chromadb.PersistentClient,
    http_factory: Callable[..., ClientAPI] = chromadb.HttpClient,
) -> ClientAPI:
    if settings.chroma_mode == "http":
        return http_factory(host=settings.chroma_host, port=settings.chroma_port)
    return persistent_factory(path=str(settings.chroma_persist_directory))


def get_or_create_collection(client: ClientAPI) -> Collection:
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
