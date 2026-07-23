# 🏋️ pt_recommendation 도메인 리팩터링 제안서 (공용 모듈 정합)

- 작성일: 2026-07-22
- 최종 수정일: 2026-07-23
- 상태: **제안 1(`app/rag/` 소유권) 최종적으로 도메인 분리로 결론** / **제안 2(설정 정합+버그 수정) 구현 완료** / **제안 3(DI 조립부 이전) 구현 완료**
- 관련 문서: `.docs/MODULE_OWNERSHIP.md`, `.docs/TRAINER_REPORT_REFACTOR_PROPOSAL.md`, `.docs/DIET_REFACTOR_PROPOSAL.md`
- 영향받는 도메인: `app/chatbot`(자체 RAG 구현 완료), `app/pt_recommendation`, `app/core/settings.py`(읽기만)

> `develop` 병합 후 회귀 테스트는 전부 통과(45 passed, 2 skipped)했다. `MODULE_OWNERSHIP.md`가 정리되는 동안 `app/rag/`를 pt_recommendation이 먼저 구현해둔 상태라 소유권 문서와 실제 코드가 어긋나 있었고, 처음에는 챗봇과 공용화하기로 합의했었다. 하지만 이후 챗봇이 이미 `RetrieverPort`/`Ingestor` 기반의 완전히 다른 구조로 자체 RAG를 구현해 `develop`에 들어온 것을 확인해, **공용화 합의를 철회하고 각자 도메인 폴더로 분리하는 쪽으로 최종 결론**을 냈다. 제안 2에는 병합으로 실제 깨진 부분(버그)도 하나 포함되어 있다.

---

## 🎯 배경

pt_recommendation은 RAG(운동목표별 트레이닝 가이드·부상 주의사항 검색)가 필요해 `app/rag/vector_store.py`·`ingest.py`·`retriever.py`를 직접 구현했다. `.docs/MODULE_OWNERSHIP.md` §2 모듈별 소유권 표는 원래 이 폴더를 챗봇 전용으로 규정하고 있었는데, `develop` 병합 시점의 `app/rag/*.py`는 1줄짜리 주석 스텁뿐이라 pt_recommendation의 구현이 텍스트 충돌 없이 그대로 들어갔었다.

이후 챗봇 담당자가 실제로 RAG를 구현 중이라는 걸 확인해 "공용 연결 계층으로 합치자"고 합의했으나, **막상 `git merge develop`을 다시 해보니 챗봇이 이미 완전히 독자적인 구조로 RAG를 다 만들어서 병합해둔 상태**였다.

- `RetrieverPort`(Protocol) + `ChromaRetriever` — 의존성 주입 구조(`collection`, `embeddings` 별도 주입)
- `RetrievedDocument` 모델 — source/title/category/keywords/score를 담는 구조화 반환 타입
- `Ingestor` 클래스 — `id`/`source`/`keywords` 필수 frontmatter, manifest 기반 증분 인덱싱(원자적 파일 쓰기), CLI 인자 지원
- 컬렉션 이름도 `gym_jjak_knowledge_v1`로 별도

pt_recommendation의 `retriever.search(query, category) -> list[str]` 인터페이스와 근본적으로 형태가 달라, 두 구현을 무리하게 통합하는 것보다 **각자 도메인 폴더에서 독립적으로 유지하는 쪽이 리스크와 작업량 모두 작다**고 판단했다.

---

## 제안 1 (우선순위 높음) — `app/rag/`는 챗봇 전용으로 유지, PT추천은 `app/pt_recommendation/rag/` 신설 ✅ 최종 결론

### 경과

1. **1차 결론(2026-07-22)**: `app/rag/`의 `vector_store.py`/`ingest.py`/`retriever.py`는 도메인 전용 로직이 거의 없어 보여, 공용 연결 계층으로 재정의하고 챗봇도 재사용하기로 채팅으로 합의함. `MODULE_OWNERSHIP.md` §2 표를 "공용(연결)"으로 수정.
2. **2차 결론(2026-07-23, 최종)**: 실제로 `git merge develop`을 해보니 챗봇이 그 사이 **완전히 다른 아키텍처(Protocol 기반 DI, 구조화된 반환 타입, manifest 인덱싱)로 RAG를 이미 구현 완료**한 상태였음이 확인됨. 1차 합의는 챗봇이 아직 구현 전이라는 전제였는데 전제 자체가 깨졌으므로, 무리하게 인터페이스를 통합하기보다 **각자 도메인 폴더로 완전히 분리**하기로 최종 변경.

### 적용한 변경

```
[챗봇 전용, 그대로 유지] app/rag/
    - RetrieverPort, ChromaRetriever, Ingestor 등 챗봇의 독자 구현

[PT추천 신설] app/pt_recommendation/rag/
    - vector_store.py, retriever.py, ingest.py (기존 pt_recommendation 구현 그대로 이전)
    - COLLECTION_NAME = "pt_recommendation_documents" (챗봇의 gym_jjak_knowledge_v1과 별개 컬렉션,
      같은 persist 디렉터리를 공유해도 컬렉션이 다르므로 충돌 없음)
```

- `app/pt_recommendation/service.py`의 `from app.rag import retriever` → `from app.pt_recommendation.rag import retriever`로 변경.
- RAG 문서도 함께 분리: `data/documents/training-by-goal.md`·`injury-precautions.md` → `data/documents/pt_recommendation/`로 이동. 챗봇의 `Ingestor`가 같은 `data/documents/`를 스캔하더라도(기본 `--source data/documents`), pt_recommendation 문서는 `id`/`source`/`keywords` 필수 필드가 없어 챗봇 쪽 파싱이 실패 목록에 잡힐 수 있어 물리적으로 하위 폴더를 분리했다.
- `MODULE_OWNERSHIP.md` §2 표의 `app/rag/`를 다시 "챗봇 전용"으로 되돌리고, PT추천은 `app/pt_recommendation/rag/`를 별도 소유한다고 명시.

### 효과

- 두 도메인의 RAG 구현이 서로의 존재를 몰라도 되는 완전한 독립 상태가 되어, 머지 충돌·인터페이스 재작업 리스크가 사라짐.
- `MODULE_OWNERSHIP.md` §3.4(도메인 코드 무수정) 원칙을 그대로 지킴 — 서로 소유 폴더만 건드림.
- 나중에 실제로 통합할 필요가 생기면(예: 컬렉션·인덱싱 방식을 정말 공유해야 하는 시점), 그때 챗봇의 `RetrieverPort` 계약에 맞춰 재검토하면 된다.

---

## 제안 2 (우선순위 높음, 버그 포함) — 하드코딩된 값을 공용 `settings`로 이전 ✅ 구현 완료

### 현재였던 것 — 설정이 이미 있는데 안 씀

`app/pt_recommendation/rag/vector_store.py`·`ingest.py`·`retriever.py`(당시 `app/rag/`)가 임베딩 모델명·차원·Chroma 경로·컬렉션 이름을 전부 하드코딩하고 있었다. `app/core/settings.py`(병합 후)엔 이미 `gemini_embedding_model`·`embedding_dimensions`·`chroma_mode`·`chroma_persist_directory`·`chroma_host`·`chroma_port`·`chroma_timeout_seconds`가 있었는데도 쓰지 않았다.

### 🐛 발견한 버그 — `genai.Client(api_key=...)`에 `SecretStr` 그대로 전달

`develop` 병합으로 `settings.gemini_api_key`가 `str`에서 `SecretStr`로 바뀌었다(diet 제안서 제안 3 반영). `app/llm/gemini_adapter.py`는 LangChain을 거치므로 `SecretStr`를 그대로 받아도 문제없지만, RAG 쪽은 **LangChain 없이 `google-genai` SDK(`genai.Client`)를 직접 호출**해서 `SecretStr` 객체가 그대로 들어가면 실제 임베딩 호출이 깨지는 상태였다. 자동화 테스트에는 안 걸린다(RAG 테스트 자체가 없고, 실 Gemini 호출은 `--run-smoke` 스킵 대상).

### 적용한 수정

```python
# ingest.py / retriever.py
client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
result = client.models.embed_content(
    model=settings.gemini_embedding_model,
    ...,
    config=types.EmbedContentConfig(..., output_dimensionality=settings.embedding_dimensions),
)

# vector_store.py
class VectorStore:
    def __init__(self) -> None:
        if settings.chroma_mode == "http":
            self._client = chromadb.HttpClient(
                host=settings.chroma_host, port=settings.chroma_port,
                settings=chromadb.Settings(
                    chroma_query_request_timeout_seconds=settings.chroma_timeout_seconds),
            )
        else:
            self._client = chromadb.PersistentClient(path=str(settings.chroma_persist_directory))
        self._collection = self._client.get_or_create_collection(
            name="pt_recommendation_documents", metadata={"hnsw:space": "cosine"},
        )
```

### 검증 결과

```bash
python -m pytest -q
# 45 passed, 2 skipped (회귀 없음)

python -m app.pt_recommendation.rag.ingest
# ingested: injury-precautions.md (8 chunks)
# ingested: training-by-goal.md (7 chunks)

# retriever.search(query="근비대를 위한 운동", category="training_guide")
# → 3건 정상 검색 (실제 Gemini 임베딩 호출 확인)
```

---

## 제안 3 (우선순위 낮음) — DI 조립부를 `app/pt_recommendation/dependencies.py`로 이전 ✅ 구현 완료

`app/pt_recommendation/router.py`가 trainer_report처럼 `get_pt_recommendation_service`를 라우터 파일에 인라인으로 두고 있던 것을, `MODULE_OWNERSHIP.md` §5(도메인 서비스 조립은 `app/<domain>/dependencies.py`에서) 목표 구조대로 분리했다.

```python
# app/pt_recommendation/dependencies.py (신규)
def get_pt_recommendation_service(
    llm: LLMPort = Depends(get_llm_client),
) -> PtRecommendationService:
    return PtRecommendationService(llm=llm)
```

`router.py`는 이제 이 함수를 import만 하고, 라우팅·인증 검증(`verify_internal_api_key`)만 담당한다. 테스트는 더 안쪽의 공용 `get_llm_client`를 오버라이드하는 방식이라(`app.dependency_overrides[get_llm_client]`) 이번 이동으로 깨지지 않았고, 회귀 없이 45 passed 그대로 유지된다.

trainer_report는 아직 같은 상태(자체 `dependencies.py` 없음)로 남아있으며, `.docs/TRAINER_REPORT_REFACTOR_PROPOSAL.md` 제안 5가 별도로 다룬다.

---

## 🧭 우선순위 요약

| 제안 | 우선순위 | 성격 | 상태 | 외부 계약 영향 |
| --- | --- | --- | --- | --- |
| 1. `app/rag/` 소유권 정리 (최종: 도메인 분리) | 높음 | 문서·구조 정리 | ✅ 완료 | 없음 |
| 2. 설정값 이전 + `SecretStr` 버그 수정 | 높음 | 버그 수정 + 하드코딩 제거 | ✅ 완료(검증됨) | 없음(내부 동작만 정상화) |
| 3. DI 조립부 이전 | 낮음 | 구조 정리 | ✅ 완료(검증됨) | 없음 |

- 제안 1·2·3 모두 완료되었다.
- 제안 1은 중간에 방향이 한 번 바뀌었다(공용화 합의 → 챗봇의 독자 구현 확인 후 도메인 분리로 최종 변경) — `.docs/MODULE_OWNERSHIP.md` 변경 이력에 두 시점 모두 기록되어 있다.

---

## 📝 변경 이력

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-07-22 | develop 병합 후 pt_recommendation-챗봇 간 `app/rag/` 소유권 정합성 제안 초안 작성 |
| 2026-07-22 | 챗봇 RAG가 병행 구현 중임을 확인 — 제안 1을 긴급 논의 항목으로 격상. 제안 2(설정 이전 + `SecretStr` 버그 수정) 구현·검증 완료 |
| 2026-07-22 | 챗봇 담당자와 협의 완료 — 제안 1(`app/rag/` 공용화) 합의. `MODULE_OWNERSHIP.md` §2 표 수정 반영 |
| 2026-07-22 | 제안 3(DI 조립부를 `app/pt_recommendation/dependencies.py`로 이전) 구현·검증 완료 |
| 2026-07-23 | `git merge develop` 시도 중 챗봇의 독자적 RAG 구현(Protocol 기반, 완전히 다른 구조)을 확인 — 제안 1의 공용화 합의를 철회하고 `app/pt_recommendation/rag/` 신설로 최종 변경. RAG 문서도 `data/documents/pt_recommendation/`으로 이동 |
