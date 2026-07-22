# 🔌 Spring 연동 계약 — FastAPI→Spring 조회 API (UserDataClient)

- 작성일: 2026-07-22
- 최종 수정일: 2026-07-22
- 상태: **설계·계약 제안 단계** — FastAPI 측 코드 구현 전, Spring 팀 확정 대기
- 범위: Deferred Integration Plan **item 1**(개인 이용정보 조회 Spring 연동)만 다룬다. 대화 영속화(item 2, Redis/Spring `ConversationProvider`)는 별도 설계로 분리한다.

> 이 문서는 FastAPI AI 서버가 Spring Boot의 개인 데이터 조회 API를 호출하기 위한 계약(엔드포인트·인증·에러·재시도)과 FastAPI 측 `SpringUserDataClient` 설계를 기록한다. Spring 저장소(`Gym-Jjak`)에는 현재 이 인바운드 API가 존재하지 않으므로, 이 문서가 Spring 팀에 전달할 제안 규격이다.

## 🧭 배경 · 시스템 경계

- FastAPI는 **RDS에 직접 접근하지 않는다.** 개인 데이터는 Spring Boot 조회 API를 통해서만 가져온다(`.docs/ARCHITECTURE.md` "🔒 시스템 경계").
- 조회 경계는 `app/common/user_data_client.py`의 `UserDataClient` Protocol(8개 read-only 메서드)로 이미 확정되어 있다. 이 문서의 엔드포인트는 그 메서드와 1:1로 대응한다.
- 신뢰 경계: **내부망 + 공유 API Key.** `user_id`/`subject_user_id`는 항상 서버 컨텍스트(FastAPI가 경로 파라미터로 고정)에서만 결정되며, LLM(Function Calling)이 생성하거나 바꿀 수 없다(`app/chatbot/tools.py`의 `_ALLOWED_ARGS` 필터·`ToolExecutionContext` 설계와 동일 원칙).
- 모든 엔드포인트는 **읽기 전용 GET**이다. 생성·수정·삭제는 이 계약에 없다.

## 🔐 인증 계약

- FastAPI→Spring 모든 요청에 헤더를 부착한다:

  ```text
  X-Internal-Api-Key: {INTERNAL_API_KEY}
  ```

- 인바운드(Spring→FastAPI, `app/common/auth.py::verify_internal_api_key`)와 **동일한 공유 시크릿**을 양방향에 사용한다. 키 값은 양쪽 모두 환경변수/Secrets로 주입하고 저장소에 커밋하지 않는다.
- Spring은 키 불일치 시 401을 반환한다(FastAPI 인바운드와 동일 규칙). FastAPI는 이를 `SPRING_CLIENT_ERROR`로 처리한다(아래 에러 절).
- 트레이스 전파(권장): FastAPI가 수신한 `request_id`를 `X-Request-ID` 헤더로 전파한다. Spring `TraceIdFilter`가 현재 `X-Trace-Id`/`traceId`를 사용하고 수신 헤더를 재사용하지 않는 것과 정합이 필요하다 — Spring 팀 확인 항목.

## 📡 엔드포인트 계약 (8개, 메서드 1:1)

- 공통 프리픽스(제안): `/internal/api/v1` — 최종 명칭은 Spring 팀이 확정한다.
- 응답 JSON 필드는 **snake_case**로 직렬화한다(Spring 연동 계약). 필드명은 `app/common/models.py`의 Pydantic 모델과 정확히 일치해야 한다.
- 금액·신체 수치는 숫자(FastAPI에서 `Decimal`로 역직렬화), 날짜는 ISO 8601 문자열(`date`/`datetime`)로 표현한다.

| # | UserDataClient 메서드 | HTTP · 경로(제안) | 200 응답 | 데이터 부재 시 |
| --- | --- | --- | --- | --- |
| 1 | `get_subscription_status(user_id)` | GET `/internal/api/v1/users/{user_id}/subscription` | `SubscriptionStatus` | 항상 200 — 구독이 없으면 `is_active=false` |
| 2 | `get_payment_history(user_id)` | GET `/internal/api/v1/users/{user_id}/payments` | `PaymentHistory[]` | `[]` |
| 3 | `get_pt_usage(user_id)` | GET `/internal/api/v1/users/{user_id}/pt-usage` | `PtUsageSummary` | 항상 200 — 계약이 없으면 `0/0/0` |
| 4 | `get_pt_history(user_id)` | GET `/internal/api/v1/users/{user_id}/pt-history` | `PtHistory[]` | `[]` |
| 5 | `get_onboarding(user_id)` | GET `/internal/api/v1/users/{user_id}/onboarding` | `OnboardingProfile` | **204 No Content** → FastAPI가 `None`으로 매핑 |
| 6 | `get_recent_workouts(user_id, weeks=4)` | GET `/internal/api/v1/users/{user_id}/workouts?weeks=4` | `WorkoutDiary[]` | `[]` |
| 7 | `get_recent_inbody(user_id, months=6, limit=6)` | GET `/internal/api/v1/users/{user_id}/inbody?months=6&limit=6` | `InBodyRecord[]` | `[]` |
| 8 | `assert_trainer_can_access(trainer_id, subject_user_id)` | GET `/internal/api/v1/trainers/{trainer_id}/subjects/{subject_user_id}/access` | `TrainerSubjectAccess` | 해당 없음 — 아래 "핵심 결정" 참고 |

- 쿼리 파라미터 명명(`weeks`, `months`, `limit`)은 단일 단어라 snake/camel 논쟁이 없다. 향후 복합어 파라미터가 생기면 명명 규칙을 Spring 팀과 다시 합의한다.
- `404 Not Found`는 "리소스 없음"의 정상 표현으로 사용하지 않는다(부재는 위 표의 `[]`/204/기본값으로 표현). 404가 오면 "알 수 없는 사용자" 등 계약 위반 상황으로 보고 `SPRING_CLIENT_ERROR`로 처리한다.

### 핵심 결정: 트레이너 접근 판정(#8)은 403이 아니라 200 + `is_allowed`

- Spring은 트레이너가 해당 회원의 담당이 **아니어도** 403이 아니라 `200 + {"is_allowed": false}`를 반환한다.
- FastAPI 측 `assert_trainer_can_access()`가 `is_allowed=false`일 때 `SubjectAccessDeniedError`(403, `TRAINER_SUBJECT_ACCESS_DENIED`)를 던진다 — 현행 Port docstring·`InMemoryUserDataClient` 동작과 동일.
- 이유: Spring의 403을 "PT 관계 거부"로 쓰면 "API Key 오류·권한 설정 오류 등 진짜 클라이언트 오류(`SPRING_CLIENT_ERROR`)"와 의미가 겹쳐 장애 진단이 어려워진다. 업무 판정은 200 응답 본문으로, 통신·인증 오류는 HTTP status로 분리한다.

### 응답 JSON 예시

`GET /internal/api/v1/users/10/subscription`

```json
{
  "is_active": true,
  "plan_name": "AI PRO",
  "expires_at": "2026-12-31T23:59:59+09:00"
}
```

`GET /internal/api/v1/users/10/payments`

```json
[
  {
    "paid_at": "2026-07-01T10:30:00+09:00",
    "amount": 99000,
    "item_name": "PT 10회권"
  }
]
```

`GET /internal/api/v1/users/10/pt-usage`

```json
{
  "total_sessions": 10,
  "used_sessions": 4,
  "remaining_sessions": 6
}
```

`GET /internal/api/v1/users/10/pt-history`

```json
[
  {
    "trainer_name": "김트레이너",
    "started_at": "2026-05-01",
    "ended_at": null
  }
]
```

`GET /internal/api/v1/users/10/onboarding` (등록된 경우)

```json
{
  "goal": "체지방 감량",
  "preferred_exercises": ["스쿼트", "러닝"],
  "experience_level": "초급"
}
```

`GET /internal/api/v1/users/10/workouts?weeks=4`

```json
[
  {
    "diary_date": "2026-07-20",
    "part": "하체",
    "exercise": "스쿼트",
    "sets": [
      { "set_number": 1, "weight": 60.0, "reps": 10 },
      { "set_number": 2, "weight": 65.0, "reps": 8 }
    ]
  }
]
```

`GET /internal/api/v1/users/10/inbody?months=6&limit=6`

```json
[
  {
    "measured_at": "2026-07-15",
    "weight": 72.4,
    "body_fat_percentage": 18.2,
    "skeletal_muscle_mass": 33.1
  }
]
```

`GET /internal/api/v1/trainers/20/subjects/10/access`

```json
{
  "trainer_id": 20,
  "subject_user_id": 10,
  "is_allowed": true
}
```

## 🚨 에러 · 재시도 · 타임아웃

`.docs/ERROR_HANDLING.md`에 이미 정의된 오류 코드(`SPRING_CLIENT_ERROR`, `SPRING_UNAVAILABLE`)와 재시도·Timeout 정책을 그대로 구현 계약으로 삼는다.

| Spring 호출 결과 | 자동 재시도 | FastAPI 매핑 |
| --- | --- | --- |
| 연결 실패 / read timeout | **1회** | 재실패 시 `SPRING_UNAVAILABLE` (503, `retryable=true`) |
| 5xx (500/502/503/504) | **1회** | 재실패 시 `SPRING_UNAVAILABLE` (503, `retryable=true`) |
| 4xx (400/401/404 등) | 0회 | `SPRING_CLIENT_ERROR` (해당 status 유지, `retryable=false`) |
| 200이지만 본문 Pydantic 검증 실패 | 0회 | `SPRING_UNAVAILABLE`로 단순화 — 계약 위반은 upstream 장애로 취급 |

- 모든 엔드포인트가 idempotent GET이므로 5xx 1회 재시도는 안전하다. 재시도는 조회 전용 요청에만 적용한다는 기존 원칙과도 일치한다(이 계약에는 조회만 존재).
- Timeout: `httpx.Timeout(connect=spring_connect_timeout_seconds, read=spring_read_timeout_seconds)` — 초기값 연결 2초 / 응답 5초, 환경설정으로 조정.
- 챗봇 SSE 경로: 위 오류는 모두 `AppError` 하위 예외로 구현되므로 `ChatbotService`의 `_error_payload`를 그대로 통과해 SSE `error` 이벤트(`{code, message, request_id, retryable}`)로 전달된다. 추가 배선이 필요 없다.
- 트레이너 루틴 분석(non-streaming)·기타 REST 경로: 전역 예외 핸들러(`app/core/error_handlers.py`)가 동일 오류 코드를 공통 JSON 응답으로 변환한다.
- 개인화 데이터 **일부** 실패 시의 `LIMITED`/`PERSONAL_DATA_PARTIAL` 처리(루틴 서비스의 `_missing_data` 등)는 기존 도메인 로직을 그대로 사용하며 이 계약의 범위가 아니다 — 이 문서는 "호출 1건의 실패를 어떤 예외로 바꾸는가"까지만 규정한다.

## 🏗️ FastAPI 측 `SpringUserDataClient` 설계 (구현은 다음 세션)

- 위치: `app/common/spring_user_data_client.py` — `UserDataClient` Protocol 8개 메서드 구현.
- HTTP 클라이언트: 단일 `httpx.AsyncClient` 인스턴스를 생성 시 보유(연결 풀 재사용). `base_url=settings.spring_base_url`, 기본 헤더 `X-Internal-Api-Key`, 위 Timeout 설정. `app/chatbot/dependencies.py::get_user_data_client()`가 `@lru_cache` 싱글턴이므로 클라이언트도 프로세스당 1개가 되고, 앱 종료(lifespan shutdown) 시 `aclose()`를 호출한다.
- 공통 헬퍼 `_get(path, params)` 하나가 다음을 캡슐화한다: 요청 전송 → 연결 오류/timeout/5xx면 정확히 1회 재전송 → 상태코드→예외 매핑(위 표) → JSON 반환. `tenacity` 의존 대신 명시적 1회 재시도로 단순하게 유지한다(정책이 "최대 1회" 고정이라 라이브러리가 과함).
- 각 메서드는 `_get` 호출 후 Pydantic 검증만 담당한다: 단일 객체는 `Model.model_validate(data)`, 리스트는 `TypeAdapter(list[Model]).validate_python(data)`. `get_onboarding`은 204 응답을 `None`으로 매핑.
- `assert_trainer_can_access`는 `TrainerSubjectAccess` 파싱 후 `is_allowed=false`면 `SubjectAccessDeniedError`를 던진다.
- 기존 httpx 사용 패턴 참고: `app/diet/analyzer.py`(Timeout 구성·예외 매핑), `app/llm/gemini_adapter.py`(httpx 예외→도메인 예외 변환).

### 구현 시 코드 변경 목록 (이번 세션 아님)

| 파일 | 변경 |
| --- | --- |
| `app/common/spring_user_data_client.py` | 신규 — 위 설계대로 구현 |
| `app/core/exceptions.py` | `SpringClientError`(4xx, `SPRING_CLIENT_ERROR`), `SpringUnavailableError`(503, `SPRING_UNAVAILABLE`, `retryable=True`) — `AppError` 하위 클래스 추가 |
| `app/chatbot/dependencies.py` | `get_user_data_client()`: `app_env == "production"`이면 `SpringUserDataClient` 반환. `local`=LocalDev, `test`=InMemory/Fake 유지 |
| `main.py` | lifespan shutdown에서 클라이언트 `aclose()` 정리 |
| `.env.example` | `SPRING_CONNECT_TIMEOUT_SECONDS`, `SPRING_READ_TIMEOUT_SECONDS` 항목 추가, `INTERNAL_API_KEY`가 인바운드 검증·아웃바운드 부착 양쪽에 쓰임을 주석으로 명시 |

설정(`spring_base_url`, `spring_connect_timeout_seconds`, `spring_read_timeout_seconds`, `internal_api_key`)은 `app/core/settings.py`에 이미 존재하므로 신규 필드는 없다.

## 🧪 테스트 전략 개요 (구현 세션에서 작성)

- `respx`로 Spring 응답을 모킹해 메서드별로 검증한다: 정상 응답 파싱 / 4xx→`SpringClientError` / 연결·timeout→정확히 1회 재시도 후 `SpringUnavailableError` / 200 본문 검증 실패→`SpringUnavailableError`.
- 재시도 횟수는 respx 호출 카운트로 "정확히 2회(원호출+재시도 1회)"를 단언한다.
- `assert_trainer_can_access`: `is_allowed=false` 응답 → `SubjectAccessDeniedError`(403) 검증.
- 모든 요청에 `X-Internal-Api-Key` 헤더가 부착되는지 검증한다.
- 기존 `FakeUserDataClient`/`InMemoryUserDataClient`는 테스트·기본값 용도로 그대로 유지한다. 실제 Spring 호출은 자동 테스트에서 0회다.

## ❓ Spring 팀 확인 필요 사항

1. 엔드포인트 프리픽스·경로 최종 확정(`/internal/api/v1/...` 제안).
2. **응답 snake_case 직렬화 방식**: 전역 Jackson SNAKE_CASE는 기존 클라이언트 API를 깨뜨리므로 금지 — AI 서버용 인바운드 컨트롤러(DTO)에만 snake_case를 적용할 방법(패키지 단위 `@JsonNaming`, 전용 `ObjectMapper` 등) 확정. (아웃바운드 `aiServiceRestClient`의 snake_case 건과는 방향이 반대인 별개 이슈.)
3. onboarding 미등록 표현: 204 No Content 제안 확정 여부.
4. #8 트레이너 접근 판정: 200 + `is_allowed` 방식 확정 여부.
5. `X-Request-ID` 트레이스 전파 채택 여부(`TraceIdFilter`의 `X-Trace-Id`와 정합).
6. 공유 `INTERNAL_API_KEY` 값의 발급·보관 방식(GitHub Secrets/환경변수) 및 로테이션 절차.
7. `weeks`/`months`/`limit` 기본값·상한(예: `limit` 최대 12)을 Spring 측에서도 검증할지.

## 📝 문서 변경 이력

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-07-22 | FastAPI→Spring 조회 API 계약 초안 작성 — 8개 엔드포인트, 인증(X-Internal-Api-Key), 에러·재시도·타임아웃 매핑, SpringUserDataClient 설계, Spring 팀 확인 사항 |
