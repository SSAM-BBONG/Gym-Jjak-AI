"""질문 + 카테고리 필터로 관련 문서 조각을 코사인 유사도 순으로 반환한다.
PT추천 전용(app/pt_recommendation) — 공용 app/rag/는 챗봇 도메인 소유라 별도로 둔다."""

from google import genai
from google.genai import types

from app.core.settings import settings
from app.pt_recommendation.rag.vector_store import get_vector_store

SIMILARITY_THRESHOLD = 0.35


def _embed_query(text: str) -> list[float]:
    client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
    result = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=[text],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY", output_dimensionality=settings.embedding_dimensions
        ),
    )
    return result.embeddings[0].values


def search(query: str, category: str, top_k: int = 3) -> list[str]:
    """query와 관련된 category 소속 문서 조각을 유사도 순으로 최대 top_k개 반환한다.
    유사도가 SIMILARITY_THRESHOLD 미만이면 억지 매칭으로 보고 제외한다."""

    store = get_vector_store()
    query_embedding = _embed_query(query)
    result = store.query(query_embedding, n_results=top_k, where={"category": category})

    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]

    return [
        document
        for document, distance in zip(documents, distances)
        if (1 - distance) >= SIMILARITY_THRESHOLD
    ]
