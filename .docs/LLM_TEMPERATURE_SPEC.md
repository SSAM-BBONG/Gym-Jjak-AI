# 🌡️ 도메인별 Gemini Temperature 설정 명세서

- 작성일: 2026-07-24
- 상태: 구현 기준
- 적용 범위: FastAPI AI 서버의 Gemini 텍스트·스트리밍·구조화 출력

## 🎯 목적

식단 분석, 챗봇, 운동 루틴, PT 추천, 트레이너 리포트는 서로 다른 생성 특성을 요구한다.
구조화된 분석과 추천은 결과의 일관성이 중요하고, 챗봇은 자연스러운 표현의 다양성이
필요하다. 따라서 모든 도메인이 하나의 고정 `temperature`를 공유하지 않고, 공통
`GeminiAdapter`에 도메인별 설정을 주입한다.

이 명세의 목표는 다음과 같다.

- 도메인별 생성 다양성과 일관성을 독립적으로 조절한다.
- 한 도메인의 설정 변경이 다른 도메인의 실행 중인 모델에 영향을 주지 않게 한다.
- 코드 수정 없이 환경변수로 운영 설정을 변경할 수 있게 한다.
- 설정값의 타입, 허용 범위, 기본값 및 적용 경로를 하나의 계약으로 정의한다.

## 📌 적용 대상과 기본값

| 도메인 | 설정 필드 | 환경변수 | 기본값 | 주요 출력 특성 |
| --- | --- | --- | ---: | --- |
| 식단 분석 | `diet_llm_temperature` | `DIET_LLM_TEMPERATURE` | `0.1` | 이미지 기반 구조화 영양 분석 |
| 챗봇 | `chatbot_llm_temperature` | `CHATBOT_LLM_TEMPERATURE` | `0.7` | 자연어 대화 및 도구 호출 |
| 운동 루틴 | `routine_llm_temperature` | `ROUTINE_LLM_TEMPERATURE` | `0.2` | 구조화된 운동 루틴 생성 |
| PT 추천 | `pt_recommendation_llm_temperature` | `PT_RECOMMENDATION_LLM_TEMPERATURE` | `0.2` | 후보 비교 및 추천 생성 |
| 트레이너 리포트 | `trainer_report_llm_temperature` | `TRAINER_REPORT_LLM_TEMPERATURE` | `0.1` | 시장 데이터 기반 분석 리포트 |

기본값은 `app/core/settings.py`의 `Settings`를 단일 기준으로 한다.
`.env.example`은 이 기본값과 동일하게 유지한다.

## ⚙️ 설정 계약

### 타입과 허용 범위

모든 temperature 설정은 다음 제약을 따른다.

```text
타입: float
최솟값: 0
최댓값: 2
경계값 0과 2: 허용
```

Pydantic `Field(default=..., ge=0, le=2)`로 검증한다. 숫자로 변환할 수 없거나 허용
범위를 벗어난 값이 입력되면 `Settings` 생성이 실패하며, 잘못된 값으로 Gemini를
호출해서는 안 된다.

### 설정 우선순위

실효 설정값은 다음 순서로 결정한다.

```text
실행 환경의 환경변수
        ↓ 없을 경우
.env 파일
        ↓ 없을 경우
Settings에 선언된 기본값
```

`.env.example`은 배포 시 자동으로 읽는 설정 파일이 아니라 설정 항목과 기본값을 안내하는
예시 문서다.

### 운영 변경 원칙

- API 요청 본문이나 쿼리로 temperature를 입력받지 않는다.
- 배포 환경에서 값을 바꾸려면 해당 도메인의 환경변수만 변경한다.
- 환경변수를 변경한 뒤에는 프로세스를 재시작해야 한다.
- 운영 중인 어댑터 인스턴스의 `_temperature`를 직접 변경하지 않는다.
- temperature 값은 비밀정보가 아니지만 외부 API 응답에는 포함하지 않는다.

## 🧱 구성 및 의존성 주입

### 전체 구조

```text
Settings
   ├─ diet_llm_temperature ─────────────┐
   ├─ chatbot_llm_temperature ──────────┤
   ├─ routine_llm_temperature ──────────┤
   ├─ pt_recommendation_llm_temperature ┤
   └─ trainer_report_llm_temperature ───┤
                                        ↓
                         도메인별 LLM DI 함수
                                        ↓
                  GeminiAdapter(temperature=<설정값>)
                                        ↓
                         ChatGoogleGenerativeAI
```

`GeminiAdapter`는 temperature 정책을 결정하지 않는다. 생성자가 전달받은 값을 보관하고,
내부 모델을 최초 생성할 때 `ChatGoogleGenerativeAI.temperature`로 전달한다.

```python
GeminiAdapter(temperature=<도메인 설정값>)
```

### 도메인별 생성 함수

| 도메인 | DI 함수 | 위치 |
| --- | --- | --- |
| 식단 분석 | `get_diet_llm_client()` | `app/diet/dependencies.py` |
| 챗봇 | `get_chatbot_llm_client()` | `app/chatbot/dependencies.py` |
| 운동 루틴 | `get_routine_llm_client()` | `app/chatbot/dependencies.py` |
| PT 추천 | `get_pt_recommendation_llm_client()` | `app/pt_recommendation/dependencies.py` |
| 트레이너 리포트 | `get_trainer_report_llm_client()` | `app/trainer_report/dependencies.py` |

각 함수는 `@lru_cache`로 어댑터를 프로세스당 한 번 생성한다. 서로 다른 DI 함수가 반환하는
어댑터는 별도 인스턴스여야 하며, 한 인스턴스를 여러 도메인이 공유해서는 안 된다.

동일한 DI 함수를 반복 호출하는 경우에는 캐시된 동일 인스턴스를 반환한다.

### 공통 팩토리 호환성

`app/core/dependencies.py`의 `get_llm_client()`는 공통·스모크 테스트 호환을 위해 유지하며,
`GeminiAdapter`의 기본값 `0.1`을 사용한다. 실제 도메인 서비스 조립에는 위 표의 도메인별
DI 함수를 사용한다. 신규 도메인은 공통 팩토리를 직접 사용하지 않고 전용 DI 함수를
정의해야 한다.

## 🔄 호출별 적용 범위

어댑터 생성 시 주입된 temperature는 해당 인스턴스가 수행하는 모든 Gemini 호출에
동일하게 적용된다.

| `LLMPort` 메서드 | 용도 | 적용 여부 |
| --- | --- | --- |
| `generate()` | 일반 텍스트 생성 및 Function Calling | 적용 |
| `stream()` | 스트리밍 텍스트 생성 및 Function Calling | 적용 |
| `generate_structured()` | 텍스트 기반 JSON Schema 출력 | 적용 |
| `generate_structured_image()` | 이미지 기반 JSON Schema 출력 | 적용 |

호출 메서드마다 temperature를 다시 전달하거나 덮어쓰지 않는다. 서로 다른 temperature가
필요하면 별도의 어댑터 인스턴스를 생성한다.

## 🔒 동시성 및 캐시 규칙

- 도메인별 어댑터는 생성 이후 불변 설정으로 취급한다.
- 요청 처리 중 temperature를 변경하는 setter를 제공하지 않는다.
- 동일 도메인의 동시 요청은 캐시된 동일 어댑터와 모델을 재사용할 수 있다.
- 다른 도메인의 동시 요청은 서로 다른 어댑터 인스턴스를 사용한다.
- `get_settings()` 및 도메인별 DI 함수의 캐시를 테스트에서 초기화할 때는 테스트 종료 후
  원래 상태가 복원되도록 한다.

이 규칙은 요청마다 공유 모델의 temperature를 변경할 때 발생할 수 있는 설정 경합을
방지한다.

## 🚨 오류 처리

| 상황 | 처리 기준 |
| --- | --- |
| 환경변수가 숫자가 아님 | `Settings` 검증 실패 |
| temperature가 0 미만 | `Settings` 검증 실패 |
| temperature가 2 초과 | `Settings` 검증 실패 |
| 환경변수가 없음 | 도메인별 기본값 사용 |
| Gemini API Key가 없음 | 어댑터가 모델을 생성하는 시점에 실패 |
| Gemini 호출 실패 | 기존 공통 LLM 오류 계약에 따라 변환 |

temperature 검증 오류를 임의의 기본값으로 조용히 대체하지 않는다.

## ✅ 테스트 명세

### 설정 테스트

- 환경변수가 없으면 표에 정의된 도메인별 기본값을 사용한다.
- 환경변수가 있으면 해당 값을 기본값보다 우선한다.
- `0`과 `2`를 정상적으로 허용한다.
- 음수, `2` 초과 및 숫자가 아닌 값을 거부한다.

### 어댑터 테스트

- 생성자로 전달된 temperature를 어댑터가 보관한다.
- 내부 `ChatGoogleGenerativeAI` 생성 시 동일한 값을 전달한다.
- temperature를 생략하면 호환 기본값 `0.1`을 사용한다.

### DI 테스트

- 각 도메인 DI 함수가 해당 도메인의 설정값으로 어댑터를 생성한다.
- 서로 다른 도메인의 어댑터는 동일 객체가 아니다.
- 동일 DI 함수를 반복 호출하면 캐시된 동일 객체를 반환한다.
- FastAPI `dependency_overrides`가 지정된 도메인에만 적용된다.

### 회귀 테스트

- 식단 구조화 이미지 응답 스키마가 유지된다.
- 챗봇 일반 응답과 스트리밍 응답이 유지된다.
- 운동 루틴 구조화 응답 스키마가 유지된다.
- PT 추천 및 트레이너 리포트 API 계약이 유지된다.
- 공통 LLM 오류 응답의 상태 코드와 오류 코드가 유지된다.

## 📊 변경 영향

| 구분 | 영향 |
| --- | --- |
| 외부 API 요청·응답 | 변경 없음 |
| DB 스키마 | 변경 없음 |
| 프롬프트 | 변경 없음 |
| LLM 모델명 | 변경 없음 |
| 배포 설정 | 도메인별 환경변수 선택적 추가 |
| 테스트 override 대상 | 공통 DI에서 도메인별 DI 함수로 변경 |

환경변수를 별도로 설정하지 않은 환경에서도 `Settings` 기본값으로 동작한다.

## 🧭 신규 도메인 추가 규칙

새로운 LLM 도메인을 추가할 때 다음 순서를 따른다.

1. `Settings`에 `<domain>_llm_temperature` 필드를 추가한다.
2. `.env.example`에 대응하는 `<DOMAIN>_LLM_TEMPERATURE`를 추가한다.
3. 해당 도메인의 `dependencies.py`에 전용 LLM DI 함수를 추가한다.
4. `GeminiAdapter(temperature=<도메인 설정값>)`으로 생성한다.
5. 이 문서의 적용 대상 표와 DI 함수 표를 갱신한다.
6. 설정 범위, 어댑터 전달 및 도메인 격리 테스트를 추가한다.

공통 `GeminiAdapter`에 신규 도메인의 기본값이나 분기문을 추가하지 않는다.

## 📚 관련 파일

- `app/core/settings.py`
- `app/llm/gemini_adapter.py`
- `app/llm/port.py`
- `app/diet/dependencies.py`
- `app/chatbot/dependencies.py`
- `app/pt_recommendation/dependencies.py`
- `app/trainer_report/dependencies.py`
- `.env.example`
