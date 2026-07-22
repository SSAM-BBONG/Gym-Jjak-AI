"""수동 증분 인덱싱. UTF-8 Markdown 문서를 front matter 규약대로 읽어 청크로 쪼갠 뒤
Chroma에 삽입한다. 변경되지 않은 문서는 재임베딩하지 않는다.

문서 front matter 필수 필드:

---
id: routine-beginner-fullbody-001
title: 초보자 전신 루틴
category: routine
source: data/documents/routine/beginner-fullbody.md
keywords: [루틴 추천, 초보자, 전신, 주 3회]
---

CLI: python -m app.rag.ingest --source data/documents --collection gym_jjak_knowledge_v1
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

import yaml
from chromadb.api.models.Collection import Collection
from pydantic import BaseModel

from app.core.settings import get_settings
from app.rag.models import EmbeddingPort
from app.rag.vector_store import COLLECTION_NAME, create_chroma_client, get_or_create_collection

_REQUIRED_FRONTMATTER_FIELDS = ("id", "title", "category", "source", "keywords")
_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_CHUNK_CONFIG = "paragraph-v1"


class ParsedDocument(BaseModel):
    id: str
    title: str
    category: str
    source: str
    keywords: list[str]
    body: str


class IngestResult(BaseModel):
    processed_files: int = 0
    added_chunks: int = 0
    updated_chunks: int = 0
    skipped_chunks: int = 0
    failed_files: list[str] = []


def _parse_document(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_PATTERN.match(text)
    if not match:
        raise ValueError(f"{path}: front matter를 찾을 수 없습니다.")

    frontmatter = yaml.safe_load(match.group(1)) or {}
    missing = [field for field in _REQUIRED_FRONTMATTER_FIELDS if field not in frontmatter]
    if missing:
        raise ValueError(f"{path}: 필수 front matter 필드 누락 {missing}")

    return ParsedDocument(
        id=str(frontmatter["id"]),
        title=str(frontmatter["title"]),
        category=str(frontmatter["category"]),
        source=str(frontmatter["source"]),
        keywords=[str(k) for k in frontmatter["keywords"]],
        body=match.group(2).strip(),
    )


def _chunk_text(body: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body)]
    return [p for p in paragraphs if p]


def _compute_document_hash(
    file_bytes: bytes,
    embedding_model: str,
    embedding_dimensions: int,
    chunk_config: str,
) -> str:
    hasher = hashlib.sha256()
    hasher.update(file_bytes)
    hasher.update(embedding_model.encode("utf-8"))
    hasher.update(str(embedding_dimensions).encode("utf-8"))
    hasher.update(chunk_config.encode("utf-8"))
    return hasher.hexdigest()


class Ingestor:
    def __init__(
        self,
        *,
        collection: Collection,
        embeddings: EmbeddingPort,
        manifest_path: Path,
        embedding_model: str,
        embedding_dimensions: int,
        chunk_config: str = _CHUNK_CONFIG,
    ) -> None:
        self._collection = collection
        self._embeddings = embeddings
        self._manifest_path = manifest_path
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._chunk_config = chunk_config

    def _load_manifest(self) -> dict:
        if not self._manifest_path.exists():
            return {}
        return json.loads(self._manifest_path.read_text(encoding="utf-8"))

    def _save_manifest(self, manifest: dict) -> None:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._manifest_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self._manifest_path)

    async def ingest(self, sources: list[Path]) -> IngestResult:
        manifest = self._load_manifest()
        result = IngestResult()

        pending_ids: list[str] = []
        pending_texts: list[str] = []
        pending_metadatas: list[dict] = []

        for source in sources:
            result.processed_files += 1
            try:
                parsed = _parse_document(source)
            except (ValueError, yaml.YAMLError) as e:
                result.failed_files.append(str(source))
                continue

            file_hash = _compute_document_hash(
                source.read_bytes(),
                self._embedding_model,
                self._embedding_dimensions,
                self._chunk_config,
            )
            previous = manifest.get(parsed.id)
            if previous and previous["hash"] == file_hash:
                result.skipped_chunks += len(previous["chunk_ids"])
                continue

            if previous:
                self._collection.delete(ids=previous["chunk_ids"])

            chunks = _chunk_text(parsed.body)
            chunk_ids = [f"{parsed.id}::{i}" for i in range(len(chunks))]
            pending_ids.extend(chunk_ids)
            pending_texts.extend(chunks)
            pending_metadatas.extend(
                {
                    "document_id": parsed.id,
                    "source": parsed.source,
                    "title": parsed.title,
                    "category": parsed.category,
                    "keywords": ",".join(parsed.keywords),
                }
                for _ in chunks
            )
            manifest[parsed.id] = {"hash": file_hash, "chunk_ids": chunk_ids}

            if previous:
                result.updated_chunks += len(chunk_ids)
            else:
                result.added_chunks += len(chunk_ids)

        if pending_texts:
            vectors = await self._embeddings.embed_documents(pending_texts)
            self._collection.add(
                ids=pending_ids,
                embeddings=vectors,
                documents=pending_texts,
                metadatas=pending_metadatas,
            )

        self._save_manifest(manifest)
        return result


async def _run_cli(source_dir: Path, collection_name: str) -> None:
    from app.rag.embeddings import GeminiEmbeddings

    settings = get_settings()
    client = create_chroma_client(settings)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    ingestor = Ingestor(
        collection=collection,
        embeddings=GeminiEmbeddings(),
        manifest_path=settings.chroma_persist_directory / "manifest.json",
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
    )
    sources = sorted(source_dir.rglob("*.md"))
    result = await ingestor.ingest(sources)
    print(
        f"처리 파일: {result.processed_files}, "
        f"추가 chunk: {result.added_chunks}, "
        f"갱신 chunk: {result.updated_chunks}, "
        f"건너뜀 chunk: {result.skipped_chunks}"
    )
    if result.failed_files:
        print(f"실패 파일: {result.failed_files}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 문서 증분 인덱싱")
    parser.add_argument("--source", type=Path, default=Path("data/documents"))
    parser.add_argument("--collection", type=str, default=COLLECTION_NAME)
    args = parser.parse_args()
    asyncio.run(_run_cli(args.source, args.collection))


if __name__ == "__main__":
    main()
