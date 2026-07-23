from unittest.mock import Mock, sentinel

from app.core.settings import Settings
from app.rag.vector_store import COLLECTION_NAME, create_chroma_client, get_or_create_collection


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, gemini_api_key="test-key", **overrides)


def test_local_mode_builds_persistent_client(tmp_path) -> None:
    settings = _settings(chroma_mode="persistent", chroma_persist_directory=tmp_path)
    persistent_factory = Mock(return_value=sentinel.client)

    client = create_chroma_client(settings, persistent_factory=persistent_factory)

    assert client is sentinel.client
    persistent_factory.assert_called_once_with(path=str(tmp_path))


def test_production_mode_builds_http_client() -> None:
    settings = _settings(chroma_mode="http", chroma_host="chroma", chroma_port=8000)
    http_factory = Mock(return_value=sentinel.client)

    client = create_chroma_client(settings, http_factory=http_factory)

    assert client is sentinel.client
    http_factory.assert_called_once_with(host="chroma", port=8000)


def test_get_or_create_collection_uses_fixed_name_and_cosine_space() -> None:
    fake_client = Mock()
    fake_client.get_or_create_collection.return_value = sentinel.collection

    collection = get_or_create_collection(fake_client)

    assert collection is sentinel.collection
    fake_client.get_or_create_collection.assert_called_once_with(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def test_persistent_client_actually_usable(tmp_path) -> None:
    """실제 chromadb.PersistentClient까지 연결해 tmp_path만 건드리는지 확인한다."""
    settings = _settings(chroma_mode="persistent", chroma_persist_directory=tmp_path)

    client = create_chroma_client(settings)
    collection = get_or_create_collection(client)

    assert collection.name == COLLECTION_NAME
    assert any(tmp_path.iterdir())
