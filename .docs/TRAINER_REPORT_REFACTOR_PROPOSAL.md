# 📊 trainer_report 도메인 리팩터링 제안서 (공용 모듈 정합)

- 작성일: 2026-07-22
- 최종 수정일: 2026-07-22
- 상태: 제안 (trainer_report 담당자 검토 요청)
- 관련 문서: `.docs/MODULE_OWNERSHIP.md`, `app/chatbot/docs/IMPLEMENTATION_PLAN.md`

> trainer_report 도메인 구현 잘 봤습니다. LangChain 격리, 결정론 계산(`comparison.py`)과 LLM narration 분리, 공용 `FakeLLMPort`, `max_retries=0` 오류 변환 등 **계획서 방향과 맞는 부분이 많습니다.** 아래는 여러 도메인이 공용 모듈을 함께 쓰면서 생긴 정합성 이슈에 대한 **수정 제안**이며, 강제가 아니라 협의용입니다. 기능 동작을 바꾸지 않는 내부 정리가 대부분입니다.

---

## 🎯 배경

챗봇 도메인이 합류하면서 `app/llm`, `app/core/exceptions.py`, `main.py` 같은 공용 모듈을 여러 도메인이 공유하게 되었고, 소유권 규칙을 `.docs/MODULE_OWNERSHIP.md`로 정리했습니다. trainer_report가 수정한 공용 모듈 몇 곳이 이 규칙과 어긋나 정리를 제안합니다.

---

## 제안 1 (우선순위 높음) — LLMError 응답의 request_id를 미들웨어와 일치시키기

### 현재 — 추적이 끊깁니다

`app/core/exceptions.py`의 LLMError 핸들러가 **새 request_id를 생성**합니다.

```python
@app.exception_handler(LLMError)
async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
    request_id = str(uuid.uuid4())        # ← 새로 만든다
    ...
    content={..., "request_id": request_id, ...}
```

반면 `main.py`의 미들웨어는 요청마다 `X-Request-ID`를 받아 `set_request_id()`로 보관하고 응답 헤더에 실어줍니다. 그리고 `AppError`·검증 오류·500 핸들러는 모두 `get_request_id()`로 **같은 ID**를 씁니다.

결과적으로 **LLM 오류가 났을 때만** 응답 본문 `request_id`가 응답 헤더 `X-Request-ID`, 그리고 Spring이 보낸 원래 추적 ID와 **달라집니다.** Spring↔FastAPI 로그 추적이 이 지점에서 끊깁니다.

### 제안

LLMError 핸들러도 공용 `get_request_id()`를 쓰도록 바꿉니다.

```python
from app.core.logging import get_request_id

@app.exception_handler(LLMError)
async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
    request_id = get_request_id()         # ← 미들웨어가 보관한 값 재사용
    ...
```

### 효과

모든 오류 응답의 `request_id`가 응답 헤더 및 Spring 추적 ID와 일치합니다. (테스트도 `body["request_id"] == response.headers["X-Request-ID"]`까지 검증하도록 강화 권장 — 현재 `test_router.py`는 `"request_id" in body`만 확인합니다.)

---

## 제안 2 (우선순위 높음) — 예외 체계를 AppError 하나로 통일

### 현재 — 두 개의 평행한 예외 계층

| 계층 | 위치 | 보유 필드 | 처리 |
| --- | --- | --- | --- |
| `AppError` | `app/core/exceptions.py` | status_code, code, message, retryable | `main.py` 핸들러 |
| `LLMError` | `app/llm/errors.py` | code | `core/exceptions.py`의 별도 핸들러(상태·메시지·retryable 하드코딩) |

같은 역할(HTTP 오류 응답)을 두 체계가 각자 처리하고 있어, 상태코드 매핑·retryable 판단이 두 곳에 흩어져 있습니다. 예를 들어 LLMError 핸들러는 `LLM_INVALID_RESPONSE`(502, 서버 파싱 실패)에도 `retryable=True`를 반환하는데, 이는 재시도로 해결되지 않는 오류라 계약상 어색합니다.

### 제안 (두 방식 중 택1)

- **A. `LLMError`가 `AppError`를 상속** — `LLMNetworkError(AppError)`로 두고 클래스 속성으로 `status_code=503, code="LLM_NETWORK_ERROR", retryable=True`를 선언. 그러면 `main.py`의 기존 `AppError` 핸들러가 그대로 처리하고, `register_exception_handlers`의 별도 핸들러와 `_LLM_ERROR_STATUS` 매핑을 삭제할 수 있습니다. (챗봇 계획서 Task 3이 택한 방식과 동일)
- **B. `LLMError` 유지, 핸들러만 공용 계약에 맞춤** — 최소 변경. 핸들러에서 `get_request_id()`를 쓰고, retryable을 오류 종류별로 구분.

계획서(Task 3)와의 일관성을 위해 **A를 권장**합니다.

### 효과

상태코드·retryable·request_id 처리가 한 곳(`AppError` + `main.py` 핸들러)으로 모입니다. 챗봇·diet·trainer_report가 동일한 오류 응답 계약(`{code, message, request_id, retryable}`)을 공유합니다.

---

## 제안 3 (우선순위 중간) — LLM Port를 §4 구조로 수렴

### 현재

공용 `app/llm/port.py`의 `LLMPort`가 `generate`(trainer_report·챗봇용)와 `generate_structured_image`(diet용)를 **모두** 갖고 있습니다. 이는 `MODULE_OWNERSHIP.md` §4에서 택하지 않은 "안 A(공용 통합 Port)"에 해당합니다. 도메인이 늘수록 이 인터페이스에 계약이 계속 누적됩니다.

### 제안

`MODULE_OWNERSHIP.md` §4의 목표 구조(안 B)로 수렴합니다.

- 공용 `app/llm/`은 **연결 팩토리**(계약 없는 chat model 생성)만 노출.
- `generate(messages, tools)`는 범용적이므로 공용 "대화형 호출" 계약으로 남길 수 있으나, 이상적으로는 각 도메인이 자기 Port를 소유하고 공용 팩토리를 주입받는 형태.
- `generate_structured_image`는 diet 전용이므로 `app/diet`로 이전(→ `.docs/DIET_REFACTOR_PROPOSAL.md` 제안 1).

trainer_report 입장에서 당장 깨지는 것은 없으며, diet의 이전이 이루어지면 공용 Port가 자연히 가벼워집니다. trainer_report는 그 시점에 자기 Port를 `app/trainer_report`에 두는 것을 검토하면 됩니다.

---

## 제안 4 (우선순위 중간) — 테스트 의존성을 requirements-dev.txt로 이동

### 현재

`requirements.txt`(런타임)에 `pytest`, `pytest-asyncio`, `pytest-cov`, `Pygments` 등 테스트 전용 패키지가 들어가 있습니다. Task 1에서 런타임/개발 의존성을 분리하려고 `requirements-dev.txt`를 만들었는데, 두 파일에 테스트 의존성이 이원화되어 있습니다.

### 제안

테스트 전용 패키지는 `requirements-dev.txt`에만 두고 `requirements.txt`에서 제거합니다. 운영 이미지에 테스트 도구가 실려 배포되지 않도록 하는 목적입니다. (`respx`, `coverage`, `pytest*`, `Pygments`, `iniconfig`, `pluggy` 등)

---

## 제안 5 (우선순위 낮음) — 도메인 DI를 도메인 파일로

### 현재

`app/trainer_report/router.py`가 `app.core.dependencies.get_llm_client`에 의존합니다. `MODULE_OWNERSHIP.md` §5는 "도메인 서비스 조립은 `app/<domain>/dependencies.py`에서, `app/core`는 도메인을 몰라야 한다"를 규칙으로 합니다.

### 제안

- 공용은 "연결"만 제공(예: `create_chat_model()` 또는 공용 `get_chat_model()`).
- trainer_report는 `app/trainer_report/dependencies.py`를 두고 그 공용 팩토리를 주입받아 `TrainerReportService`를 조립.

낮은 우선순위이며, 제안 1·2가 정리된 뒤 진행해도 됩니다.

---

## 🧭 우선순위 요약

| 제안 | 우선순위 | 성격 | 외부 계약 영향 |
| --- | --- | --- | --- |
| 1. LLMError request_id 일치 | 높음 | 버그 수정 | 추적 정상화 (응답 형태 동일) |
| 2. 예외 체계 통일(AppError) | 높음 | 구조 정리 | 없음(오류 계약 동일) |
| 3. LLM Port §4 수렴 | 중간 | 구조 정리 | 없음 |
| 4. 테스트 의존성 분리 | 중간 | 위생 | 없음 |
| 5. 도메인 DI 이전 | 낮음 | 구조 정리 | 없음 |

- 제안 1은 **강사님이 강조한 Spring↔FastAPI 추적**과 직결되므로 먼저 처리하길 권합니다.
- 나머지는 기능·외부 계약을 바꾸지 않는 내부 정리입니다.
- 챗봇 구현은 이 정리를 기다리지 않고 진행 가능하나, 제안 1·2가 되면 공용 오류 계약이 일관됩니다.

---

## 📝 변경 이력

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-07-22 | trainer_report 병합 후 공용 모듈 정합성 제안 초안 작성 |
