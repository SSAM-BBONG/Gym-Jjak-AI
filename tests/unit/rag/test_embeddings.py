from app.rag.embeddings import EMBEDDING_DIMENSIONS
from tests.fakes.embeddings import FakeEmbeddings


async def test_fake_embeddings_embed_documents_returns_fixed_dimension_vectors() -> None:
    embeddings = FakeEmbeddings()

    vectors = await embeddings.embed_documents(["문서1", "문서2"])

    assert len(vectors) == 2
    assert all(len(v) == EMBEDDING_DIMENSIONS for v in vectors)


async def test_fake_embeddings_embed_query_returns_fixed_dimension_vector() -> None:
    embeddings = FakeEmbeddings()

    vector = await embeddings.embed_query("질문")

    assert len(vector) == EMBEDDING_DIMENSIONS


async def test_fake_embeddings_records_calls_for_assertions() -> None:
    embeddings = FakeEmbeddings()

    await embeddings.embed_documents(["문서1"])
    await embeddings.embed_query("질문")

    assert embeddings.document_calls == [["문서1"]]
    assert embeddings.query_calls == ["질문"]
