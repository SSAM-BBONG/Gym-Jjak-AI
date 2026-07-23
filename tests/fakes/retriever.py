from pydantic import BaseModel

from app.rag.models import RetrievedDocument


class SearchQuery(BaseModel):
    """FakeRetriever.search() 호출 인자 기록 1건."""

    query: str
    category: str | None
    keywords: list[str]
    top_k: int


class FakeRetriever:
    """RetrieverPort의 가짜 구현체. 미리 정해둔 문서 목록을 반환하고,
    검색 호출 인자를 기록해 카테고리/키워드 사용 여부를 검증할 수 있게 한다."""

    def __init__(self, documents: list[RetrievedDocument] | None = None) -> None:
        self.documents = documents if documents is not None else []
        self.queries: list[SearchQuery] = []

    async def search(
        self,
        query: str,
        *,
        category: str | None = None,
        keywords: list[str] | None = None,
        top_k: int = 3,
    ) -> list[RetrievedDocument]:
        """호출 인자를 기록하고 미리 설정된 문서 목록을 그대로 반환한다."""
        self.queries.append(
            SearchQuery(query=query, category=category, keywords=keywords or [], top_k=top_k)
        )
        return self.documents
