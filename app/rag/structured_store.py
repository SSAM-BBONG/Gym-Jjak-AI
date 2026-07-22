"""고객센터 연락처, 환불 정책 버전처럼 정확성이 필요한 서비스 사실을 임베딩 검색 없이
{category, key}로 정확 조회한다. 설명형 정책 문서와 루틴 지식은 Chroma 검색(retriever.py)을
쓰고, 답변 조립 우선순위는 정형 사실 -> RAG 문서 -> Gemini 일반 지식 순으로 고정한다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StructuredKnowledgeStore:
    """service_facts.json 형태의 정형 지식을 {category, key}로 정확 조회하는 저장소."""

    def __init__(self, data: dict[str, Any]) -> None:
        """facts 리스트를 (category, key) -> value 딕셔너리로 미리 변환해둔다."""
        self._values: dict[tuple[str, str], str] = {
            (fact["category"], fact["key"]): fact["value"] for fact in data.get("facts", [])
        }

    @classmethod
    def from_file(cls, path: Path) -> "StructuredKnowledgeStore":
        """service_facts.json 파일을 읽어 저장소를 만든다."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data)

    def get(self, category: str, key: str) -> str | None:
        """정확히 일치하는 항목이 없으면 None을 반환한다(임베딩 검색 안 함)."""
        return self._values.get((category, key))
