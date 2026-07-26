from pathlib import Path

from app.core.settings import Settings
from app.rag.ingest import Ingestor
from app.rag.retriever import ChromaRetriever
from app.rag.vector_store import create_chroma_client, get_or_create_collection
from tests.fakes.embeddings import FakeEmbeddings

_ROUTINE_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "rag" / "sample_routine.md"
_POLICY_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "rag" / "sample_policy.md"


async def _seed_collection(tmp_path: Path, embeddings: FakeEmbeddings):
    settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        chroma_mode="persistent",
        chroma_persist_directory=tmp_path / "chroma",
    )
    client = create_chroma_client(settings)
    collection = get_or_create_collection(client)
    ingestor = Ingestor(
        collection=collection,
        embeddings=embeddings,
        manifest_path=tmp_path / "manifest.json",
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
    )
    await ingestor.ingest([_ROUTINE_FIXTURE, _POLICY_FIXTURE])
    return collection


async def test_search_results_always_have_source_title_category(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    collection = await _seed_collection(tmp_path, embeddings)
    retriever = ChromaRetriever(collection, embeddings)

    results = await retriever.search("루틴 추천해줘", category=None, keywords=[], top_k=5)

    assert results
    assert all(r.source and r.title and r.category for r in results)


async def test_category_filter_returns_guide_policy_document(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    collection = await _seed_collection(tmp_path, embeddings)
    retriever = ChromaRetriever(collection, embeddings)

    results = await retriever.search("환불", category="guide", keywords=[], top_k=5)

    assert results
    assert all(r.category == "guide" for r in results)


async def test_keywords_are_folded_into_query_text_not_returned_to_caller(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    collection = await _seed_collection(tmp_path, embeddings)
    retriever = ChromaRetriever(collection, embeddings)

    await retriever.search("루틴", category=None, keywords=["초보자", "주 3회"], top_k=3)

    assert embeddings.query_calls
    sent_query = embeddings.query_calls[-1]
    assert "초보자" in sent_query
    assert "주 3회" in sent_query


async def test_missing_source_metadata_is_excluded_from_results(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    collection = await _seed_collection(tmp_path, embeddings)
    retriever = ChromaRetriever(collection, embeddings)

    query = "출처 없는 문서 테스트"
    query_vector = await embeddings.embed_query(query)
    collection.add(
        ids=["broken::0"],
        embeddings=[query_vector],
        documents=["출처 메타데이터가 없는 청크"],
        metadatas=[{"title": "출처 없음", "category": "routine", "document_id": "broken"}],
    )

    results = await retriever.search(query, category=None, keywords=[], top_k=5)

    assert all(r.document_id != "broken::0" for r in results)


async def test_identical_text_scores_close_to_one(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    collection = await _seed_collection(tmp_path, embeddings)
    retriever = ChromaRetriever(collection, embeddings)

    results = await retriever.search(
        "초보자를 위한 주 3회 전신 루틴입니다. 가슴, 등, 하체를 골고루 자극합니다.",
        category="routine",
        keywords=[],
        top_k=1,
    )

    assert results[0].score > 0.9
