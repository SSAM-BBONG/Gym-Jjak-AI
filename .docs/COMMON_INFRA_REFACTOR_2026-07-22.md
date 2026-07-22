# 🛠️ 공용 인프라 정리: 오류 핸들러·미들웨어 통합 (2026-07-22)

- 작성일: 2026-07-22
- 상태: 구현 완료, 커밋 전
- 관련 문서: `.docs/MODULE_OWNERSHIP.md`, `.docs/TRAINER_REPORT_REFACTOR_PROPOSAL.md`(제안 1)
- 영향받는 도메인: 없음 (diet·trainer_report 폴더 무수정, 회귀 테스트 통과)

> `main.py`와 `app/core/exceptions.py`에 흩어져 있던 예외 핸들러·미들웨어를 `MODULE_OWNERSHIP.md` §3 원칙(공용 인프라는 한 곳에)에 맞춰 정리했다. 정리 과정에서 **request_id 관련 버그 2건**을 TDD로 잡았다.

---

## 🎯 왜 했나

병합 이후 오류 처리 로직이 두 곳에 나뉘어 있었다.

- `main.py`: `AppError`, `RequestValidationError`, 예상 못한 `Exception` 핸들러
- `app/core/exceptions.py`: `LLMError` 핸들러(`register_exception_handlers`)

같은 역할(공통 오류 응답 `{code, message, request_id, retryable}`)을 두 곳이 각자 처리하면서, **request_id 처리 방식이 갈라졌다.**

---

## 🐛 TDD로 발견한 버그 2건

새 통합 테스트(`tests/integration/core/test_error_contract.py`)를 먼저 작성해 4가지 오류 경로(AppError·검증 오류·LLMError·예상 못한 500)가 모두 "본문 `request_id` == 응답 헤더 `X-Request-ID`"를 만족하는지 검증했다. 구현 전 실행 결과 **2개 실패**.

### 버그 1 — LLMError 응답이 새 request_id를 생성 (예상했던 버그)

```python
# 기존 app/core/exceptions.py
@app.exception_handler(LLMError)
async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
    request_id = str(uuid.uuid4())   # ← 미들웨어가 보관한 값을 안 쓰고 새로 생성
```

Spring이 보낸 `X-Request-ID`를 미들웨어가 보관해 다른 오류들은 그 값을 쓰는데, LLMError만 새 UUID를 만들어 응답 헤더·Spring 원본 추적 ID와 어긋났다.

### 버그 2 — 예상 못한 500 오류에는 X-Request-ID 헤더 자체가 없음 (테스트 작성 중 새로 발견)

`main.py`의 커스텀 미들웨어(`request_context`)는 `call_next()`가 반환한 뒤 응답 헤더에 `X-Request-ID`를 붙인다. 그런데 FastAPI의 `@app.exception_handler(Exception)`은 Starlette 내부에서 `ServerErrorMiddleware`로 처리되며, 이 미들웨어는 **커스텀 미들웨어 바깥(스택 최외곽)** 에 위치한다. 즉 처리되지 않은 예외가 발생하면 커스텀 미들웨어의 "응답 받은 뒤 헤더 붙이기" 코드가 실행될 기회 자체가 없다.

- AppError·검증 오류: `ExceptionMiddleware`(커스텀 미들웨어 **안쪽**)가 처리 → 헤더 정상 부착
- 예상 못한 `Exception`: `ServerErrorMiddleware`(커스텀 미들웨어 **바깥쪽**)가 처리 → 헤더 부착 코드를 건너뜀

병합 이전부터 있던 버그로, 지금까지는 500 응답에 요청 추적 ID가 안 실렸다.

---

## ✅ 수정 방식

미들웨어 순서에 의존하지 않도록, **모든 오류 응답을 만드는 공용 빌더가 헤더를 직접 설정**하게 했다.

```python
# app/core/error_handlers.py
def _error_response(status_code: int, code: str, message: str, retryable: bool) -> JSONResponse:
    request_id = get_request_id()
    return JSONResponse(
        status_code=status_code,
        headers={REQUEST_ID_HEADER: request_id},   # ← 미들웨어를 거치지 않아도 항상 채움
        content={"code": code, "message": message, "request_id": request_id, "retryable": retryable},
    )
```

이제 어떤 예외 경로(커스텀 미들웨어 안쪽이든 바깥쪽이든)를 타도 헤더 누락이 구조적으로 불가능하다.

---

## 📁 파일 변경 내역

| 파일 | 변경 | 내용 |
| --- | --- | --- |
| `app/core/error_handlers.py` | **신규** | `AppError`·검증 오류·`LLMError`·예상 못한 예외 핸들러를 한 곳에 통합. `_error_response()` 공용 빌더로 request_id·헤더 일관성 보장 |
| `app/core/middleware.py` | **신규** | `request_context_middleware` 분리 (request_id 보존/생성 + 처리시간 로그) |
| `app/core/exceptions.py` | 축소 | `AppError`, `internal_auth_failed`만 남김. 핸들러·`_LLM_ERROR_STATUS`·`uuid` import 제거(→ `error_handlers.py`로 이동) |
| `main.py` | 슬림화 | `create_app()` 팩토리로 전환. 미들웨어·핸들러 인라인 코드 제거하고 조립만 담당. 라우터 등록 순서·엔드포인트(`/health`, `/`, diet, trainer-report)는 동일하게 유지 |
| `tests/integration/core/test_error_contract.py` | **신규** | 4가지 오류 경로의 request_id/헤더 일관성 통합 테스트 |

**`app/diet/`, `app/trainer_report/`, `app/llm/` 등 도메인 폴더는 한 곳도 수정하지 않았다.** `app/llm/errors.py`의 `LLMError`는 import만 하고 정의는 그대로 trainer_report 소유로 둔다.

---

## 🧪 검증

```bash
python -m pytest tests/integration/core/test_error_contract.py -q
# 4 passed (구현 전: 2 failed)

python -m pytest -q
# 30 passed, 1 skipped  (diet·trainer_report 회귀 없음)
```

---

## 🔜 남은 것 (별도 협의)

- `TRAINER_REPORT_REFACTOR_PROPOSAL.md` 제안 2(`LLMError`를 `AppError` 상속으로 통일)는 이번 정리에 포함하지 않았다. 지금 구조(핸들러 4종을 한 곳에서 처리)로도 request_id 버그는 해결되므로, 상속 통합은 trainer_report 담당자와 별도 협의.
- `MODULE_OWNERSHIP.md` §5(도메인 DI를 `app/<domain>/dependencies.py`로 분리)는 이번 범위 밖. `app/core/dependencies.py`는 아직 diet를 import하는 상태 그대로.

---

## 📝 변경 이력

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-07-22 | 오류 핸들러·미들웨어 통합, request_id 버그 2건 수정 |
