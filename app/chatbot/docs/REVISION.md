# 🩹 Gym-Jjak Chatbot Revision Log

- 작성일: 2026-07-22
- 최종 수정일: 2026-07-22
- 상태: Task 1~14 구현 완료 후 실사용 점검 중 발견한 버그 수정 기록

> `IMPLEMENTATION_PLAN.md`가 "무엇을 만들었는가"를 담은 문서라면, 이 문서는 **다 만든 뒤 실제로
> 써보다가 발견한 버그와 수정 내역**을 담는다. 계획서의 체크박스 완료 여부와는 별개로, 실사용
> 단계에서 드러난 문제를 여기에 남긴다.

---

## 🐛 1. Function Calling 멀티턴 시 `thought_signature` 누락 (치명적)

### 증상

Swagger/curl로 `POST /api/v1/chatbot/messages`에 개인정보 질문(예: "결제 내역 알려줘")을 보내면,
메시지 내용과 무관하게 **항상 503 `LLM_NETWORK_ERROR`** 가 반환됨. `pytest --run-smoke`는 정상
통과해서 더 혼란스러웠음.

### 원인

Gemini 2.5+/3 계열 모델은 Function Calling **멀티턴** 대화에서, 모델이 도구 호출을 요청하면
응답에 `thought_signature`(추론 연속성 서명, base64)를 함께 준다. 도구 실행 결과를 다시 모델에
보내는 **다음 턴**에 이 서명을 그대로 echo하지 않으면 Gemini가 `400 INVALID_ARGUMENT`로 거부한다.

- `app/llm/models.py`의 `ToolCall`이 `name`/`args`/`id`만 담고 서명을 저장하지 않았음
- `app/llm/gemini_adapter.py`의 `generate()`가 응답에서 서명을 추출하지 않고 버렸음
- 재구성 시(`_to_langchain_message`)에도 서명을 다시 실어 보내지 않았음
- 그 결과 도구 실행 후 2턴째 재호출에서 항상 400 발생

### 왜 "네트워크 오류"로 보였나 (버그 2번과 연결)

`gemini_adapter.py`가 429(rate limit)가 아닌 `ChatGoogleGenerativeAIError`를 전부
`LLM_NETWORK_ERROR`로 뭉뚱그려서, 진짜 원인(요청 자체가 잘못됨)이 "일시적 네트워크 문제"로
오인됐다. 실제로는 재시도해도 100% 같은 이유로 계속 실패하는 오류였다.

### 진단 과정 (요약)

1. `pytest --run-smoke`는 성공 → 실제 Gemini 연결/키 자체는 문제 없음 확인
2. uvicorn 재시작 후 첫 요청도 실패 → "오래된 프로세스/세션 문제" 가설 기각
3. `GEMINI_MODEL` 변경 재시도 → 무관함 확인 (다른 모델도 동일 증상)
4. 시스템+유저 메시지 1턴만 보내는 진단 스크립트 → 성공 (1턴은 문제 없음)
5. 그래프 전체 경로(도구 실행 후 2턴째 재호출까지) 진단 스크립트 → **여기서 재현**,
   서버 로그에서 실제 원인 `400 INVALID_ARGUMENT: Function call is missing a
   thought_signature` 확인
6. `langchain_google_genai` 설치 패키지 소스를 직접 읽어 `additional_kwargs`의
   `__gemini_function_call_thought_signatures__` 키로 서명을 왕복시켜야 함을 확인

### 수정 내용

| 파일 | 변경 |
| --- | --- |
| `app/llm/models.py` | `ToolCall`에 `thought_signature: str \| None = None` 필드 추가 |
| `app/llm/gemini_adapter.py` | `generate()`가 응답의 `additional_kwargs["__gemini_function_call_thought_signatures__"]`에서 서명을 추출해 각 `ToolCall`에 담음. `_to_langchain_message()`가 assistant 메시지 재구성 시 이 서명을 다시 `additional_kwargs`로 실어 보냄 |
| `tests/unit/llm/test_gemini_adapter_generate.py` (신규) | 서명 추출/왕복 단위 테스트 4건 |

### 실사용 검증

실제 Gemini API로 `ChatbotService.chat()` 전체 경로(도구 실행 → 2턴째 재호출) 호출 →
정상적으로 결제 내역 답변 생성 확인.

### 남은 리스크

- `__gemini_function_call_thought_signatures__`는 `langchain-google-genai`의 **비공개(밑줄 2개)
  내부 키**를 그대로 미러링한 것이다. 이 라이브러리가 버전업하며 키 이름을 바꾸면 우리 코드도
  같이 갱신해야 한다(`app/llm/gemini_adapter.py`의 `_THOUGHT_SIGNATURE_KEY` 주석 참고).
- 근본적으로는 `langchain-google-genai`가 `gemini-3`이 아닌 모델명(`gemini-flash-latest` 등)에는
  자체 호환 패치(더미 서명 자동 삽입)를 적용하지 않는 버전 갭이 원인이었다. 라이브러리가 이 문제를
  정식으로 고치면 우리 쪽 우회 코드는 단순화할 수 있다.

---

## 🐛 2. LLM 오류 분류가 429 외에는 전부 "네트워크 오류"로 뭉개짐

### 증상

버그 1을 진단하며 발견. 400(잘못된 요청), 404(모델 없음) 등 **재시도해도 똑같이 실패하는 오류**가
전부 `LLM_NETWORK_ERROR`(재시도 가능)로 응답되고 있었다.

### 원인

```python
except ChatGoogleGenerativeAIError as e:
    if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
        raise LLMRateLimitedError(error_text) from e
    raise LLMNetworkError(error_text) from e   # 429가 아니면 전부 네트워크 오류
```

추가로 `app/core/error_handlers.py`의 `handle_llm_error`가 `retryable`을 **모든 LLMError에 대해
무조건 `True`로 하드코딩**하고 있어, 재시도해도 소용없는 오류인데도 사용자에게 "다시 시도하라"고
안내하고 있었다.

### 수정 내용

| 파일 | 변경 |
| --- | --- |
| `app/llm/gemini_adapter.py` | `_raise_for_gemini_error()` 헬퍼 신설. `INVALID_ARGUMENT` 포함 시 `LLMInvalidResponseError`(502, 비재시도)로 분류, 그 외는 기존대로 `LLMNetworkError` |
| `app/core/error_handlers.py` | `_LLM_ERROR_RETRYABLE` 매핑 추가 — `LLM_NETWORK_ERROR`/`LLM_RATE_LIMITED`만 `retryable=True`, `LLM_INVALID_RESPONSE`는 `False`. 오류 메시지도 재시도 가능 여부에 따라 다르게 안내 |
| `tests/integration/core/test_error_contract.py` | `LLM_INVALID_RESPONSE`가 502 + `retryable=False`로 나가는지 검증하는 테스트 추가 |

---

## 🐛 3. `tests/rag_eval` fixture가 실제 `.env`를 못 읽음

### 증상

`GEMINI_API_KEY`를 `.env`에 넣고 `pytest --run-rag-eval`을 돌려도 3개 테스트가 전부 스킵됨.

### 원인

`tests/rag_eval/test_retrieval_quality.py`의 `retriever` fixture가 `Settings(_env_file=None, ...)`로
설정을 새로 만들면서, Chroma 임시 경로만 바꾸려던 의도와 달리 `.env` 전체를 안 읽게 만들어버림 →
`GEMINI_API_KEY`가 항상 빈 값 → 스킵 조건 항상 참.

### 수정 내용

`Settings(_env_file=None, ...)` 대신 `get_settings()`(실제 `.env`를 읽은 설정)를
`model_copy(update={...})`로 Chroma 경로만 덮어써서 사용하도록 변경.

### 실사용 검증

실제 키로 재실행 → `test_recall_at_3_meets_threshold` 등 3건 모두 통과 확인.

---

## 🛠️ 4. (버그는 아님) 로컬 개발용 `LocalDevUserDataClient` 추가

Swagger 등으로 챗봇 응답을 직접 확인하려면, 기존 `InMemoryUserDataClient`(항상 구독 비활성
반환)로는 항상 403만 떠서 아무 답변도 볼 수 없었다. `app_env=local`일 때만 활성화되는 샘플
데이터 제공자(`app/common/dev_user_data.py`)를 추가해 로컬에서 실제 대화 흐름을 눈으로 확인할
수 있게 했다. Spring 연동이 끝나면 이 파일과 `app/chatbot/dependencies.py`의 분기 코드를
통째로 삭제할 예정.

---

## 📝 변경 이력

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-07-22 | thought_signature 누락 버그, LLM 오류 분류 버그, rag_eval fixture 버그 수정. 로컬 개발용 UserDataClient 추가 |
