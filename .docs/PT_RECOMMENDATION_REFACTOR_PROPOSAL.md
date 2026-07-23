# 🏋️ pt_recommendation 도메인 리팩터링 제안서 (공용 모듈 정합)

- 작성일: 2026-07-22
- 최종 수정일: 2026-07-22
- 상태: **제안 1(`app/rag/` 소유권 재정의) 합의 완료** / **제안 2(설정 정합+버그 수정) 구현 완료** / **제안 3(DI 조립부 이전) 구현 완료**
- 관련 문서: `.docs/MODULE_OWNERSHIP.md`, `.docs/TRAINER_REPORT_REFACTOR_PROPOSAL.md`, `.docs/DIET_REFACTOR_PROPOSAL.md`
- 영향받는 도메인: `app/chatbot`(RAG 구현 진행 중), `app/pt_recommendation`, `app/core/settings.py`(읽기만)

> `develop` 병합 후 회귀 테스트는 전부 통과(45 passed, 2 skipped)했지만, `MODULE_OWNERSHIP.md`가 정리되는 동안 `app/rag/`를 pt_recommendation이 먼저 구현해둔 상태라 소유권 문서와 실제 코드가 어긋나 있습니다. **챗봇 담당자가 지금 실제로 RAG를 구현 중이라고 확인되어**, 제안 1은 나중에 논의할 사항이 아니라 지금 바로 확인이 필요한 항목으로 격상합니다. 제안 2는 확인 과정에서 실제로 깨져 있던 부분(버그)이라 검토 없이 바로 수정하고 실제 Gemini 호출로 검증까지 마쳤습니다.

---

## 🎯 배경

pt_recommendation은 RAG(운동목표별 트레이닝 가이드·부상 주의사항 검색)가 필요해 `app/rag/vector_store.py`·`ingest.py`·`retriever.py`를 직접 구현했습니다. 그런데 `.docs/MODULE_OWNERSHIP.md` §2 모듈별 소유권 표는 이 폴더를 다음과 같이 규정합니다.

> `app/rag/`, `app/routine/` | 챗봇 기능 | 챗봇 | 챗봇 전용, 타 도메인 미사용

`develop`의 `app/rag/*.py`는 병합 시점엔 1줄짜리 주석 스텁뿐이었지만, **챗봇 담당자가 지금 실제로 자기 RAG 구현을 진행 중**입니다. 즉 "미래에 겹칠 수도 있는 계획"이 아니라 **두 도메인이 지금 동시에 같은 성격의 모듈을 만들고 있는 상황**입니다. trainer_report·diet가 겪었던 "공용 모듈을 여러 도메인이 동시에 건드리다 생긴 정합성 문제"와 같은 유형이며, 이번엔 병합 전에 먼저 확인할 수 있는 기회입니다.

실제 코드를 다시 검토해보니 `app/rag/`의 세 파일은 **PT추천 전용 로직이 사실상 없습니다.**

- `vector_store.py`: ChromaDB 연결·upsert·query만 하는 순수 wrapper
- `ingest.py`: `data/documents/*.md`를 frontmatter의 `category`로 태깅해 적재 — 어느 도메인 문서든 동일하게 처리
- `retriever.py`: `search(query, category)` — `category` 파라미터 하나로 도메인을 구분하는 구조

유일하게 도메인 전용이었던 부분은 컬렉션 이름(`pt_recommendation_documents`)뿐이었고, 이는 이미 `documents`로 중립화했습니다(제안 2와 함께 반영).

---

## 제안 1 (우선순위 높음) — `app/rag/`를 "공용 연결 + 도메인 문서" 구조로 재정의 ✅ 합의 완료

### 현재 — 문서와 실제가 어긋남, 병행 구현 중

- `MODULE_OWNERSHIP.md`: `app/rag/`는 챗봇 전용, 타 도메인 미사용
- 실제: pt_recommendation이 이미 구현·검증(실제 Gemini 임베딩 호출 확인)까지 마쳤고, 챗봇도 지금 별도로 구현을 진행 중
- `app/llm/`이 이미 채택한 "① 연결(공용) / ② Port·계약(도메인)" 구조(§4)가 RAG에도 그대로 들어맞음 — 벡터스토어 연결·임베딩 호출 방식은 도메인 무관 동일, 도메인마다 갈리는 건 `category` 값과 문서 내용뿐

### 제안

```
[공용]  app/rag/vector_store.py, ingest.py, retriever.py
        → "문서를 벡터DB에 넣고 category로 검색하는 방법"은 도메인 무관 동일 (이미 검증됨)

[도메인] data/documents/ 안의 실제 문서와 category 값
        → pt_recommendation: training_guide, injury_guide
        → 챗봇: 챗봇이 필요한 카테고리를 자유롭게 추가(append-only)
```

- `MODULE_OWNERSHIP.md` §2 표의 `app/rag/` 항목을 "챗봇 전용"에서 "공용(연결)"으로 수정했습니다(`app/routine/`은 챗봇 전용 그대로 유지).
- 컬렉션 이름은 이미 `documents`로 중립화했고, `ingest.py`/`retriever.py`에 도메인 분기 코드가 없어 챗봇이 코드 변경 없이 카테고리만 추가하면 바로 사용 가능합니다.
- **챗봇 담당자에게 확인받았습니다(2026-07-22).** pt_recommendation이 먼저 구현·검증한 벡터스토어/ingest/retriever를 챗봇도 그대로 재사용하기로 합의했고, `app/pt_recommendation/service.py`는 원래부터 공용 위치(`app.rag`)를 그대로 참조하고 있어 pt_recommendation 쪽 코드 변경은 없습니다.

### 효과

- 소유권 문서와 실제 코드가 일치합니다.
- 챗봇이 이미 검증된 연결 계층을 재사용해 RAG 구현 시간을 아낍니다.
- 두 도메인이 각자 다른 청킹·컬렉션 구조로 병행 완성해 나중에 다시 합치는 낭비를 막습니다.

---

## 제안 2 (우선순위 높음, 버그 포함) — 하드코딩된 값을 공용 `settings`로 이전 ✅ 구현 완료

### 현재였던 것 — 설정이 이미 있는데 안 씀

`app/rag/vector_store.py`·`ingest.py`·`retriever.py`가 임베딩 모델명·차원·Chroma 경로·컬렉션 이름을 전부 하드코딩하고 있었습니다. `app/core/settings.py`(병합 후)엔 이미 `gemini_embedding_model`·`embedding_dimensions`·`chroma_mode`·`chroma_persist_directory`·`chroma_host`·`chroma_port`·`chroma_timeout_seconds`가 있었는데도 쓰지 않았습니다.

### 🐛 발견한 버그 — `genai.Client(api_key=...)`에 `SecretStr` 그대로 전달

`develop` 병합으로 `settings.gemini_api_key`가 `str`에서 `SecretStr`로 바뀌었습니다(diet 제안서 제안 3 반영). `app/llm/gemini_adapter.py`는 LangChain을 거치므로 `SecretStr`를 그대로 받아도 문제없지만, `app/rag/ingest.py`·`retriever.py`는 **LangChain 없이 `google-genai` SDK(`genai.Client`)를 직접 호출**해서 `SecretStr` 객체가 그대로 들어가면 실제 임베딩 호출이 깨지는 상태였습니다. 자동화 테스트에는 안 걸립니다(RAG 테스트 자체가 없고, 실 Gemini 호출은 `--run-smoke` 스킵 대상).

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
            name="documents", metadata={"hnsw:space": "cosine"},
        )
```

### 검증 결과

```bash
python -m pytest -q
# 45 passed, 2 skipped (회귀 없음)

python -m app.rag.ingest
# ingested: injury-precautions.md (8 chunks)
# ingested: training-by-goal.md (7 chunks)

# retriever.search(query="근비대를 위한 운동", category="training_guide")
# → 3건 정상 검색 (실제 Gemini 임베딩 호출 확인)
```

컬렉션 이름 변경(`pt_recommendation_documents` → `documents`)에 따라 로컬의 구 인덱스(`data/indexes/`, gitignore 대상)도 삭제 후 재적재해 정합성을 확인했습니다.

---

## 제안 3 (우선순위 낮음) — DI 조립부를 `app/pt_recommendation/dependencies.py`로 이전 ✅ 구현 완료

`app/pt_recommendation/router.py`가 trainer_report처럼 `get_pt_recommendation_service`를 라우터 파일에 인라인으로 두고 있던 것을, `MODULE_OWNERSHIP.md` §5(도메인 서비스 조립은 `app/<domain>/dependencies.py`에서) 목표 구조대로 분리했습니다.

```python
# app/pt_recommendation/dependencies.py (신규)
def get_pt_recommendation_service(
    llm: LLMPort = Depends(get_llm_client),
) -> PtRecommendationService:
    return PtRecommendationService(llm=llm)
```

`router.py`는 이제 이 함수를 import만 하고, 라우팅·인증 검증(`verify_internal_api_key`)만 담당합니다. 테스트는 더 안쪽의 공용 `get_llm_client`를 오버라이드하는 방식이라(`app.dependency_overrides[get_llm_client]`) 이번 이동으로 깨지지 않았고, 회귀 없이 45 passed 그대로 유지됩니다.

trainer_report는 아직 같은 상태(자체 `dependencies.py` 없음)로 남아있으며, `.docs/TRAINER_REPORT_REFACTOR_PROPOSAL.md` 제안 5가 별도로 다룹니다.

---

## 🧭 우선순위 요약

| 제안 | 우선순위 | 성격 | 상태 | 외부 계약 영향 |
| --- | --- | --- | --- | --- |
| 1. `app/rag/` 소유권을 공용으로 재정의 | 높음 | 문서·구조 정리 | ✅ 합의 완료 | 없음 |
| 2. 설정값 이전 + `SecretStr` 버그 수정 | 높음 | 버그 수정 + 하드코딩 제거 | ✅ 완료(검증됨) | 없음(내부 동작만 정상화) |
| 3. DI 조립부 이전 | 낮음 | 구조 정리 | ✅ 완료(검증됨) | 없음 |

- 제안 1·2·3 모두 완료되었습니다.

---

## 📝 변경 이력

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-07-22 | develop 병합 후 pt_recommendation-챗봇 간 `app/rag/` 소유권 정합성 제안 초안 작성 |
| 2026-07-22 | 챗봇 RAG가 병행 구현 중임을 확인 — 제안 1을 긴급 논의 항목으로 격상. 제안 2(설정 이전 + `SecretStr` 버그 수정) 구현·검증 완료 |
| 2026-07-22 | 챗봇 담당자와 협의 완료 — 제안 1(`app/rag/` 공용화) 합의. `MODULE_OWNERSHIP.md` §2 표 수정 반영 |
| 2026-07-22 | 제안 3(DI 조립부를 `app/pt_recommendation/dependencies.py`로 이전) 구현·검증 완료 |
