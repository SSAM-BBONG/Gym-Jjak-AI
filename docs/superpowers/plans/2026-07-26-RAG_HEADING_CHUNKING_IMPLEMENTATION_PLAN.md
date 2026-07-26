# RAG Heading Chunking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `data/documents` Markdown 문서를 H2 단위로 안정적으로 청킹하고, 서비스·정책 안내와 루틴 추천이 각각 `guide`와 `routine` 범위에서 정확히 검색되도록 만든다.

**Architecture:** 인덱싱 시 `app.rag.ingest`가 Front Matter의 제목과 Markdown H1/H2 계층을 읽어 검색용 브레드크럼이 붙은 청크를 생성한다. H2가 없는 기존 문서는 현재의 빈 줄 문단 경계를 유지하되, 긴 문단만 500자 제한으로 추가 분할한다. 챗봇 서비스 안내 경로는 `guide` 메타데이터 필터를 사용하고, 기존 루틴 서비스는 `routine` 필터를 유지한다.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, ChromaDB, Gemini Embeddings, pytest, PyYAML

## Global Constraints

- `.env` 파일과 그 안의 비밀 값은 읽거나 수정하거나 커밋하지 않는다.
- Spring Boot 서버 코드는 이 작업 범위에서 수정하지 않는다.
- 모든 Markdown 문서는 UTF-8로 저장하고, 새 Markdown 파일명은 대문자를 사용한다.
- H1은 독립 청크 경계가 아니라 H2 청크의 문맥으로만 사용한다.
- H2가 있으면 H2 단위로 청킹하고, H2가 없으면 빈 줄 문단 단위로 폴백한다.
- 생성되는 각 임베딩 문자열 전체 길이는 브레드크럼을 포함해 최대 500자이며, 청크 간 overlap은 0이다.
- 서비스 안내·결제·환불·구독·예약 관련 문서 메타데이터는 물리 경로와 무관하게 `category: guide`를 사용한다.
- 루틴 추천 검색은 `category="routine"`, 챗봇 서비스 안내 검색은 `category="guide"`, 기본 `top_k`는 모두 3을 유지한다.
- 청킹 규칙 식별자는 `paragraph-v1`에서 `markdown-heading-v1`로 변경해 기존 manifest hash가 전 문서를 재임베딩하도록 한다.
- PDF 직접 인덱싱, stale chunk 자동 삭제, 기본 `top_k=5` 전환, 임베딩 모델·차원 변경은 범위에서 제외한다.
- 실제 Gemini Embedding API를 호출하는 전체 코퍼스 인덱싱은 비용이 발생하므로 자동 테스트에 넣지 않고, 코드·단위 테스트 검증 뒤 명시적으로 한 번 실행한다.

---

## Target File Structure

| 파일 | 책임 |
| --- | --- |
| `app/rag/ingest.py` | Markdown 계층 파싱, 500자 제한 분할, breadcrumb 생성, manifest 청킹 버전 갱신 |
| `app/chatbot/nodes.py` | 서비스·정책 안내 RAG 검색에 `guide` 필터 전달 |
| `data/documents/policy/*.md` | 기존 정책 문서의 검색 메타데이터를 `guide`로 통일 |
| `data/documents/guide/짐짝_정책문서.md` | 새 정책 문서의 검색 메타데이터를 `guide`로 통일 |
| `data/documents/pt_recommendation/*.md` | 전체 코퍼스 인덱싱 가능하도록 필수 Front Matter `id`, `source` 보완 |
| `tests/unit/rag/test_ingest.py` | H2, H2 없는 문서, 500자 제한, config 변경 재임베딩 검증 |
| `tests/unit/rag/test_retriever.py` | `guide` 메타데이터 필터 검증 |
| `tests/graph/test_chatbot_graph.py` | 챗봇 서비스 안내 노드가 `guide` 필터를 전달하는지 검증 |
| `tests/rag_eval/cases.jsonl` | 서비스 안내 평가 케이스의 기대 카테고리를 `guide`로 갱신 |
| `tests/rag_eval/test_retrieval_quality.py` | 변경된 코퍼스의 Recall@3 및 출처·카테고리 품질 회귀 검증 |

## Shared Interfaces

```python
# app/rag/ingest.py
_CHUNK_CONFIG = "markdown-heading-v1"

def _chunk_text(
    body: str,
    *,
    title: str,
    max_chunk_size: int = 500,
) -> list[str]:
    """Return non-overlapping embedding strings, each at most max_chunk_size characters."""
```

```python
# app/rag/ingest.py inside Ingestor.ingest
chunks = _chunk_text(parsed.body, title=parsed.title)

# app/chatbot/nodes.py inside rag_node
documents = await deps.retriever.search(
    state["message"], category="guide", keywords=[], top_k=3
)
```

### Task 1: Normalize Corpus Metadata Before Reindexing

**Files:**
- Modify: `data/documents/policy/subscription-cancel.md`
- Modify: `data/documents/policy/refund.md`
- Modify: `data/documents/policy/pt-reservation-cancel.md`
- Modify: `data/documents/policy/customer-center.md`
- Modify: `data/documents/guide/짐짝_정책문서.md`
- Modify: `data/documents/pt_recommendation/training-by-goal.md`
- Modify: `data/documents/pt_recommendation/injury-precautions.md`
- Modify: `tests/unit/rag/test_ingest.py`

**Interfaces:**
- Consumes: `_parse_document(path)` in `app.rag.ingest`, which requires `id`, `title`, `category`, `source`, and `keywords` in YAML Front Matter.
- Produces: every Markdown file under `data/documents` passes Front Matter parsing; all service/policy documents are searchable with `category="guide"`.

- [ ] **Step 1: Write the failing corpus Front Matter test**

Add this test and imports to `tests/unit/rag/test_ingest.py`. It intentionally encodes the required category mapping so that missing `id`/`source` fields and old `policy` categories fail visibly.

```python
from app.rag.ingest import _parse_document


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/rag/test_ingest.py::test_all_document_corpus_files_have_required_frontmatter_and_expected_categories -v`

Expected: FAIL because the two `pt_recommendation` documents do not yet satisfy all mandatory Front Matter fields and/or policy documents still use `category: policy`.

- [ ] **Step 3: Apply the minimal metadata corrections**

In each of the five service/policy files, change only the Front Matter category value to the following exact value; do not move files solely for categorization.

```yaml
category: guide
```

Add the missing fields to the two existing PT recommendation documents without changing their body content. Preserve their existing `title`, `category`, and `keywords` values.

```yaml
# data/documents/pt_recommendation/training-by-goal.md
id: training-by-goal-001
source: data/documents/pt_recommendation/training-by-goal.md

# data/documents/pt_recommendation/injury-precautions.md
id: injury-precautions-001
source: data/documents/pt_recommendation/injury-precautions.md
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `pytest tests/unit/rag/test_ingest.py::test_all_document_corpus_files_have_required_frontmatter_and_expected_categories -v`

Expected: PASS. The test proves the full Markdown corpus can proceed to the ingestion parser and the intended guide filter will include all five service/policy documents.

- [ ] **Step 5: Commit the corpus metadata correction**

```bash
git add -- data/documents/policy/subscription-cancel.md data/documents/policy/refund.md data/documents/policy/pt-reservation-cancel.md data/documents/policy/customer-center.md data/documents/guide/짐짝_정책문서.md data/documents/pt_recommendation/training-by-goal.md data/documents/pt_recommendation/injury-precautions.md tests/unit/rag/test_ingest.py
git commit -m "docs: normalize rag document metadata"
```

### Task 2: Implement Bounded Heading-Aware Markdown Chunking

**Files:**
- Modify: `app/rag/ingest.py`
- Modify: `tests/unit/rag/test_ingest.py`

**Interfaces:**
- Consumes: `ParsedDocument.body` and `ParsedDocument.title` created by `_parse_document`.
- Produces: `_chunk_text(body, title=..., max_chunk_size=500) -> list[str]`; each returned string is non-empty, contains its applicable breadcrumb, is at most 500 characters, and overlaps no neighbouring string.

- [ ] **Step 1: Write the failing H2 breadcrumb and fallback tests**

Add these tests to `tests/unit/rag/test_ingest.py`. Import `_chunk_text` beside `Ingestor`.

```python
from app.rag.ingest import Ingestor, _chunk_text


def test_chunk_text_uses_h2_as_boundary_and_keeps_h1_as_breadcrumb() -> None:
    body = """# 회원 안내

## 결제 확인

결제 내역은 마이페이지에서 확인할 수 있습니다.

## 환불 안내

환불 신청 방법은 고객센터 안내를 확인하세요.
"""

    chunks = _chunk_text(body, title="짐짝 이용안내")

    assert chunks == [
        "짐짝 이용안내 > 회원 안내 > 결제 확인\n\n결제 내역은 마이페이지에서 확인할 수 있습니다.",
        "짐짝 이용안내 > 회원 안내 > 환불 안내\n\n환불 신청 방법은 고객센터 안내를 확인하세요.",
    ]


def test_chunk_text_without_h2_uses_title_and_blank_paragraphs() -> None:
    body = "첫 번째 완결 문단입니다.\n\n두 번째 완결 문단입니다."

    chunks = _chunk_text(body, title="기존 정책")

    assert chunks == [
        "기존 정책\n\n첫 번째 완결 문단입니다.",
        "기존 정책\n\n두 번째 완결 문단입니다.",
    ]


def test_chunk_text_splits_long_h2_body_without_exceeding_limit() -> None:
    body = "# 상위 제목\n\n## 긴 항목\n\n" + ("가" * 700)

    chunks = _chunk_text(body, title="긴 문서", max_chunk_size=500)

    assert len(chunks) >= 2
    assert all(chunk.startswith("긴 문서 > 상위 제목 > 긴 항목\n\n") for chunk in chunks)
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert "".join(chunk.split("\n\n", 1)[1] for chunk in chunks) == "가" * 700
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/unit/rag/test_ingest.py -k "chunk_text" -v`

Expected: FAIL because `_chunk_text` currently has no `title` or `max_chunk_size` parameters and splits every blank paragraph without breadcrumb context.

- [ ] **Step 3: Implement a deterministic bounded splitter and heading parser**

Replace the current paragraph-only `_chunk_text` with focused private helpers. Use `re.MULTILINE` heading matches, preserve document order, and strip only surrounding whitespace. The complete returned string, rather than only the body, must satisfy the 500-character limit.

```python
_CHUNK_CONFIG = "markdown-heading-v1"


def _split_to_limit(text: str, *, limit: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    pieces: list[str] = []
    for paragraph in paragraphs:
        while len(paragraph) > limit:
            pieces.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        if paragraph:
            pieces.append(paragraph)
    return pieces


def _with_breadcrumb(*, breadcrumb: str, text: str, max_chunk_size: int) -> list[str]:
    separator = "\n\n"
    body_limit = max_chunk_size - len(breadcrumb) - len(separator)
    if body_limit < 1:
        raise ValueError("breadcrumb exceeds max_chunk_size")
    return [f"{breadcrumb}{separator}{piece}" for piece in _split_to_limit(text, limit=body_limit)]
```

Then parse `# ` and `## ` lines in one forward scan. Keep the latest H1 value, accumulate each H2 body until the next H2, and produce one or more `_with_breadcrumb(...)` chunks for every non-empty H2 body. If no H2 appears anywhere in the document, call `_with_breadcrumb(breadcrumb=title, text=body, max_chunk_size=max_chunk_size)` so legacy policy and routine documents retain paragraph behaviour. Do not create a standalone H1 chunk and do not concatenate neighbouring paragraphs.

Use the following complete function body; the two helpers above remain directly above it in `app/rag/ingest.py`.

```python
def _chunk_text(
    body: str,
    *,
    title: str,
    max_chunk_size: int = 500,
) -> list[str]:
    h1: str | None = None
    h2: str | None = None
    h2_body: list[str] = []
    chunks: list[str] = []
    found_h2 = False

    def flush_h2() -> None:
        if h2 is None:
            return
        text = "\n".join(h2_body).strip()
        if not text:
            return
        parts = [title]
        if h1:
            parts.append(h1)
        parts.append(h2)
        chunks.extend(
            _with_breadcrumb(
                breadcrumb=" > ".join(parts),
                text=text,
                max_chunk_size=max_chunk_size,
            )
        )

    for line in body.splitlines():
        if line.startswith("## "):
            flush_h2()
            h2 = line.removeprefix("## ").strip()
            h2_body = []
            found_h2 = True
        elif line.startswith("# "):
            h1 = line.removeprefix("# ").strip()
        elif h2 is not None:
            h2_body.append(line)

    flush_h2()
    if found_h2:
        return chunks
    return _with_breadcrumb(
        breadcrumb=title,
        text=body,
        max_chunk_size=max_chunk_size,
    )
```

Finally, pass the Front Matter title from `Ingestor.ingest`.

```python
chunks = _chunk_text(parsed.body, title=parsed.title)
```

- [ ] **Step 4: Add and run the manifest-version re-embedding regression test**

Add this test after the existing changed-document test. It proves changing only `chunk_config` invalidates the manifest rather than silently keeping paragraph-shaped vectors.

```python
async def test_changed_chunk_config_replaces_existing_document_chunks(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    source = _copy_fixture(tmp_path)

    first_ingestor = _build_ingestor(tmp_path, embeddings)
    first = await first_ingestor.ingest([source])
    settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        chroma_mode="persistent",
        chroma_persist_directory=tmp_path / "chroma",
    )
    client = create_chroma_client(settings)
    collection = get_or_create_collection(client)
    changed_ingestor = Ingestor(
        collection=collection,
        embeddings=embeddings,
        manifest_path=tmp_path / "manifest.json",
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        chunk_config="markdown-heading-v2-test",
    )

    second = await changed_ingestor.ingest([source])

    assert first.added_chunks > 0
    assert second.updated_chunks > 0
    assert len(embeddings.document_calls) == 2
```

Run: `pytest tests/unit/rag/test_ingest.py -v`

Expected: PASS. Both ingestors use the same temporary persistent Chroma path, so the second run observes the first run's manifest and collection entries.

- [ ] **Step 5: Commit the chunking implementation**

```bash
git add -- app/rag/ingest.py tests/unit/rag/test_ingest.py
git commit -m "feat: add heading-aware rag chunking"
```

### Task 3: Apply the Guide Filter to the Chatbot Service-Policy Path

**Files:**
- Modify: `app/chatbot/nodes.py`
- Modify: `tests/graph/test_chatbot_graph.py`
- Modify: `tests/unit/rag/test_retriever.py`
- Modify: `tests/fixtures/rag/sample_policy.md`

**Interfaces:**
- Consumes: `RetrieverPort.search(query, *, category, keywords, top_k)`.
- Produces: `rag_node` always requests `category="guide"`; routine service calls remain `category="routine"` and are not modified.

- [ ] **Step 1: Write failing graph and retriever tests**

In `tests/graph/test_chatbot_graph.py`, extend `test_service_policy_question_uses_rag_and_returns_sources` with the fake retriever call assertion already supported by the test builder.

```python
assert builder.retriever.queries[-1]["category"] == "guide"
assert builder.retriever.queries[-1]["top_k"] == 3
```

In `tests/unit/rag/test_retriever.py`, replace the routine-only assertion with a guide-specific lookup that proves the stored policy fixture is available through the actual intended filter.

```python
async def test_category_filter_returns_guide_policy_document(tmp_path) -> None:
    embeddings = FakeEmbeddings()
    collection = await _seed_collection(tmp_path, embeddings)
    retriever = ChromaRetriever(collection, embeddings)

    results = await retriever.search("환불", category="guide", keywords=[], top_k=5)

    assert results
    assert all(result.category == "guide" for result in results)
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/graph/test_chatbot_graph.py::test_service_policy_question_uses_rag_and_returns_sources tests/unit/rag/test_retriever.py::test_category_filter_returns_guide_policy_document -v`

Expected: FAIL because `rag_node` currently sends `category=None` and the policy fixture still stores `category: policy`.

- [ ] **Step 3: Make the smallest production and fixture changes**

Change only the chatbot service-policy search call in `app/chatbot/nodes.py`:

```python
documents = await deps.retriever.search(
    state["message"],
    category="guide",
    keywords=[],
    top_k=3,
)
```

Change `tests/fixtures/rag/sample_policy.md` Front Matter to `category: guide`, and change the hard-coded source document category in `test_service_policy_question_uses_rag_and_returns_sources` to `guide`. Do not edit `app/routine/service.py`; its existing two `category="routine"` calls are the required routine-search boundary.

- [ ] **Step 4: Run focused and affected regression tests**

Run: `pytest tests/graph/test_chatbot_graph.py tests/unit/rag/test_retriever.py -v`

Expected: PASS. The graph test confirms the caller contract; the retriever tests confirm Chroma metadata filtering returns only guide documents while preserving routine behaviour.

- [ ] **Step 5: Commit the service-guide routing change**

```bash
git add -- app/chatbot/nodes.py tests/graph/test_chatbot_graph.py tests/unit/rag/test_retriever.py tests/fixtures/rag/sample_policy.md
git commit -m "feat: filter chatbot guides in rag search"
```

### Task 4: Align Retrieval Evaluation Data and Verify the Full Local Suite

**Files:**
- Modify: `tests/rag_eval/cases.jsonl`
- Verify: `tests/rag_eval/test_retrieval_quality.py`
- Verify: `app/routine/service.py`

**Interfaces:**
- Consumes: the `category` property in each JSONL evaluation case and the production `RetrieverPort.search` contract.
- Produces: RAG quality checks target `guide` for service/policy questions and `routine` for routine questions, with source metadata retained in every retrieved result.

- [ ] **Step 1: Write the evaluation-data expectations before editing the JSONL**

In `tests/rag_eval/test_retrieval_quality.py`, add a pure fixture-free guard that checks the committed evaluation contract without invoking Gemini or Chroma.

```python
def test_service_policy_eval_cases_use_guide_category() -> None:
    cases = _load_cases()
    service_terms = ("환불", "결제", "구독", "예약", "고객센터", "이용")

    matching_cases = [
        case for case in cases
        if any(term in case["query"] for term in service_terms)
    ]

    assert matching_cases
    assert all(case["category"] == "guide" for case in matching_cases)
```

- [ ] **Step 2: Run the guard test to verify it fails**

Run: `pytest tests/rag_eval/test_retrieval_quality.py::test_service_policy_eval_cases_use_guide_category -v`

Expected: FAIL for any legacy service/policy case carrying `"category": "policy"`.

- [ ] **Step 3: Update only service/policy categories in the evaluation corpus**

For every `tests/rag_eval/cases.jsonl` record whose query is a payment, refund, subscription, reservation, customer-centre, or usage-guide question, replace:

```json
"category": "policy"
```

with:

```json
"category": "guide"
```

Leave routine evaluation records as `"category": "routine"`. Do not change their queries, expected source identifiers, or Recall@3 thresholds in this task.

- [ ] **Step 4: Run all non-network regression tests**

Run: `pytest --run-rag-eval tests/unit/rag tests/graph/test_chatbot_graph.py tests/rag_eval/test_retrieval_quality.py::test_service_policy_eval_cases_use_guide_category -v`

Expected: PASS. The module-level `rag_eval` marker requires `--run-rag-eval` even when selecting the fixture-free guard. The selected guard does not instantiate `retriever`, build an embedding index, or call Gemini; this command verifies the unit-level chunker, manifest invalidation, retrieval filter, graph caller, and evaluation-data contract.

- [ ] **Step 5: Run the explicit local reindex and retrieval-quality measurement**

After confirming the configured local Gemini API key is valid without opening `.env`, run the existing ingestion command using the project’s documented entry point:

```bash
uv run python -m app.rag.ingest --source data/documents
pytest --run-rag-eval -m rag_eval tests/rag_eval -v
```

Expected: ingestion reports no `failed_files`; the RAG evaluation reports Recall@3 at or above its existing threshold and every result retains `source`, `title`, and `category`. If the evaluation fails, keep the current collection and record the failing query/result evidence before making any retrieval-parameter change; `top_k` must remain 3 in this plan.

- [ ] **Step 6: Inspect the final change set and commit the evaluation alignment**

Run: `git diff --check`

Expected: no whitespace errors.

```bash
git add -- tests/rag_eval/cases.jsonl tests/rag_eval/test_retrieval_quality.py
git commit -m "test: align rag evaluation with guide category"
```

## Completion Checklist

- [ ] Every Markdown document under `data/documents` parses required Front Matter fields.
- [ ] H2 documents create H2-scoped chunks with `title > H1 > H2` context and no standalone H1 chunk.
- [ ] H2-free documents retain paragraph semantics with the title breadcrumb.
- [ ] Every emitted embedding string is 500 characters or fewer and no overlap is introduced.
- [ ] `_CHUNK_CONFIG` is `markdown-heading-v1`, so the existing manifest triggers a reindex.
- [ ] Chatbot service-policy RAG passes `category="guide"`; routine recommendation continues to pass `category="routine"`.
- [ ] Unit, graph, and non-network evaluation-data tests pass before the paid local reindex.
- [ ] The explicit local reindex reports no failed documents and the opted-in RAG Recall@3 run meets its existing threshold.
