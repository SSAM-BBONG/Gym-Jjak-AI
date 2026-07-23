"""고정 평가셋 기반 RAG 품질 게이트. 실제 Gemini Embedding API를 호출하므로
`pytest --run-rag-eval -m rag_eval tests/rag_eval`로만 명시적으로 실행한다
(기본 `pytest` 실행에는 포함되지 않는다 — conftest.py의 skip 로직 참고).

지표:
- Recall@3 >= 0.85
- source metadata 누락률 == 0
- 잘못된 category 반환률 <= 0.05
"""

import json
from pathlib import Path

import pytest

from app.core.settings import Settings
from app.rag.embeddings import GeminiEmbeddings
from app.rag.ingest import Ingestor
from app.rag.retriever import ChromaRetriever
from app.rag.vector_store import create_chroma_client, get_or_create_collection

pytestmark = pytest.mark.rag_eval

_CASES_PATH = Path(__file__).parent / "cases.jsonl"
_DOCUMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "documents"


def _load_cases() -> list[dict]:
    with _CASES_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture
async def retriever(tmp_path):
    from app.core.settings import get_settings

    base_settings = get_settings()  # .env를 정상적으로 읽은 실제 설정
    settings = base_settings.model_copy(
        update={
            "chroma_mode": "persistent",
            "chroma_persist_directory": tmp_path / "chroma",
        }
    )
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY가 없어 RAG 품질 평가를 건너뜁니다.")

    embeddings = GeminiEmbeddings()
    client = create_chroma_client(settings)
    collection = get_or_create_collection(client)
    ingestor = Ingestor(
        collection=collection,
        embeddings=embeddings,
        manifest_path=tmp_path / "manifest.json",
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
    )
    sources = sorted(_DOCUMENTS_DIR.rglob("*.md"))
    result = await ingestor.ingest(sources)
    assert result.failed_files == [], f"색인 실패한 문서가 있습니다: {result.failed_files}"

    return ChromaRetriever(collection, embeddings)


async def test_recall_at_3_meets_threshold(retriever) -> None:
    cases = _load_cases()
    assert len(cases) >= 20

    hits = 0
    for case in cases:
        results = await retriever.search(
            case["query"], category=case.get("category"), keywords=[], top_k=3
        )
        retrieved_ids = {r.document_id.split("::")[0] for r in results}
        if retrieved_ids & set(case["expected_document_ids"]):
            hits += 1

    recall = hits / len(cases)
    assert recall >= 0.85, f"Recall@3={recall:.2f} (기준 0.85 미달)"


async def test_all_results_have_source_metadata(retriever) -> None:
    cases = _load_cases()
    missing = 0
    total = 0
    for case in cases:
        results = await retriever.search(
            case["query"], category=case.get("category"), keywords=[], top_k=3
        )
        for r in results:
            total += 1
            if not r.source:
                missing += 1

    assert total > 0
    assert missing / total == 0


async def test_category_accuracy_within_threshold(retriever) -> None:
    cases = _load_cases()
    wrong = 0
    total = 0
    for case in cases:
        expected_category = case.get("category")
        if not expected_category:
            continue
        results = await retriever.search(case["query"], category=None, keywords=[], top_k=3)
        for r in results:
            total += 1
            if r.category != expected_category:
                wrong += 1

    assert total > 0
    assert wrong / total <= 0.05
