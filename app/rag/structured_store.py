"""고객센터 연락처, 환불 정책 버전처럼 정확성이 필요한 서비스 사실을 임베딩 검색 없이
{category, key}로 정확 조회한다. 설명형 정책 문서와 루틴 지식은 Chroma 검색(retriever.py)을
쓰고, 답변 조립 우선순위는 정형 사실 -> RAG 문서 -> Gemini 일반 지식 순으로 고정한다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StructuredKnowledgeStore:
    def __init__(self, data: dict[str, Any]) -> None:
        self._values: dict[tuple[str, str], str] = {
            (fact["category"], fact["key"]): fact["value"] for fact in data.get("facts", [])
        }

    @classmethod
    def from_file(cls, path: Path) -> "StructuredKnowledgeStore":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data)

    def get(self, category: str, key: str) -> str | None:
        return self._values.get((category, key))
