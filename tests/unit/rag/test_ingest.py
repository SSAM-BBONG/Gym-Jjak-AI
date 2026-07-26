import shutil
from pathlib import Path

from app.core.settings import Settings
from app.rag.ingest import Ingestor, _parse_document
from app.rag.vector_store import create_chroma_client, get_or_create_collection
from tests.fakes.embeddings import FakeEmbeddings

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "rag" / "sample_routine.md"
_POLICY_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "rag" / "sample_policy.md"


def test_all_document_corpus_files_have_required_frontmatter_and_expected_categories() -> None:
    documents_root = Path(__file__).resolve().parents[3] / "data" / "documents"
    expected_guide_files = {
        "policy/subscription-cancel.md",
        "policy/refund.md",
        "policy/pt-reservation-cancel.md",
        "policy/customer-center.md",
        "guide/짐짝_정책문서.md",
    }

    parsed_by_relative_path = {
        path.relative_to(documents_root).as_posix(): _parse_document(path)
        for path in sorted(documents_root.rglob("*.md"))
    }

    assert parsed_by_relative_path
    assert all(parsed.id and parsed.source for parsed in parsed_by_relative_path.values())
    assert {
        relative_path
        for relative_path, parsed in parsed_by_relative_path.items()
        if parsed.category == "guide"
    } >= expected_guide_files


def _build_ingestor(tmp_path: Path, embeddings: FakeEmbeddings) -> Ingestor:
    settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        chroma_mode="persistent",
        chroma_persist_directory=tmp_path / "chroma",
    )
    client = create_chroma_client(settings)
    collection = get_or_create_collection(client)
    return Ingestor(
        collection=collection,
        embeddings=embeddings,
        manifest_path=tmp_path / "manifest.json",
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
    )


def _copy_fixture(tmp_path: Path, fixture: Path = _FIXTURE) -> Path:
    dest = tmp_path / fixture.name
    shutil.copyfile(fixture, dest)
    return dest


async def test_unchanged_document_is_not_embedded_twice(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    ingestor = _build_ingestor(tmp_path, embeddings)
    source = _copy_fixture(tmp_path)

    first = await ingestor.ingest([source])
    second = await ingestor.ingest([source])

    assert first.added_chunks > 0
    assert second.added_chunks == 0
    assert second.skipped_chunks == first.added_chunks
    assert len(embeddings.document_calls) == 1


async def test_changed_document_replaces_chunks_and_re_embeds(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    ingestor = _build_ingestor(tmp_path, embeddings)
    source = _copy_fixture(tmp_path)

    await ingestor.ingest([source])
    source.write_text(source.read_text(encoding="utf-8") + "\n\n추가된 문단입니다.", encoding="utf-8")
    second = await ingestor.ingest([source])

    assert second.updated_chunks > 0
    assert second.added_chunks == 0
    assert len(embeddings.document_calls) == 2


async def test_missing_required_frontmatter_field_is_reported_as_failed(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    ingestor = _build_ingestor(tmp_path, embeddings)
    broken = tmp_path / "broken.md"
    broken.write_text(
        "---\ntitle: 제목만 있음\ncategory: routine\n---\n\n본문",
        encoding="utf-8",
    )

    result = await ingestor.ingest([broken])

    assert result.added_chunks == 0
    assert str(broken) in result.failed_files


async def test_ingest_multiple_new_documents_counts_processed_files(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    ingestor = _build_ingestor(tmp_path, embeddings)
    sources = [_copy_fixture(tmp_path, _FIXTURE), _copy_fixture(tmp_path, _POLICY_FIXTURE)]

    result = await ingestor.ingest(sources)

    assert result.processed_files == 2
    assert result.added_chunks > 0
    assert result.failed_files == []
