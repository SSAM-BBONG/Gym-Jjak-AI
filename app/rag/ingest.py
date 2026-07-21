"""data/documents/의 마크다운 원본을 청크로 나누고 임베딩해서 벡터DB에 적재하는
배치 스크립트. 서버 실행과 완전히 분리되어 있으며 수동으로 실행한다:
    python -m app.rag.ingest

문서 해시를 저장해두고, 변경된 파일만 다시 적재한다(증분 적재)."""

import hashlib
import json
import re
from pathlib import Path

import yaml
from google import genai
from google.genai import types

from app.core.settings import settings
from app.rag.vector_store import get_vector_store

DOCUMENTS_DIR = Path("data/documents")
STATE_FILE = Path("data/indexes/.ingest_state.json")
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768

_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _parse_document(text: str) -> tuple[dict, str]:
    match = _FRONTMATTER_PATTERN.match(text)
    if not match:
        raise ValueError("frontmatter(---로 감싼 메타데이터)를 찾을 수 없습니다.")
    frontmatter = yaml.safe_load(match.group(1)) or {}
    return frontmatter, match.group(2)


def _split_sections(body: str) -> list[tuple[str, str]]:
    """`## ` 헤딩 단위로 청크를 나눈다. 첫 헤딩 이전 텍스트는 'intro' 섹션으로 묶는다."""
    sections: list[tuple[str, str]] = []
    current_title = "intro"
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return [(title, text) for title, text in sections if text]


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    client = genai.Client(api_key=settings.gemini_api_key)
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIM),
    )
    return [embedding.values for embedding in result.embeddings]


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ingest_all() -> None:
    state = _load_state()
    store = get_vector_store()

    for path in sorted(DOCUMENTS_DIR.glob("*.md")):
        raw_text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if state.get(path.name) == digest:
            print(f"skip (unchanged): {path.name}")
            continue

        frontmatter, body = _parse_document(raw_text)
        category = frontmatter.get("category", "uncategorized")
        title = frontmatter.get("title", path.stem)
        sections = _split_sections(body)
        if not sections:
            print(f"skip (no sections): {path.name}")
            continue

        texts = [text for _, text in sections]
        embeddings = _embed(texts, task_type="RETRIEVAL_DOCUMENT")
        ids = [f"{path.stem}-{i}" for i in range(len(sections))]
        metadatas = [
            {"source": path.name, "title": title, "category": category, "section": section_title}
            for section_title, _ in sections
        ]

        store.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        state[path.name] = digest
        print(f"ingested: {path.name} ({len(sections)} chunks)")

    _save_state(state)


if __name__ == "__main__":
    ingest_all()
