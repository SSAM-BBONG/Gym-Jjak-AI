from app.rag.models import RetrievedDocument


def test_retrieved_document_defaults_keywords_to_empty_list() -> None:
    doc = RetrievedDocument(
        document_id="routine-beginner-fullbody-001",
        content="초보자 전신 루틴 설명",
        score=0.83,
        source="data/documents/routine/beginner-fullbody.md",
        title="초보자 전신 루틴",
        category="routine",
    )

    assert doc.keywords == []
