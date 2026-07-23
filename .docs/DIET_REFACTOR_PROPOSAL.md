# 🍽️ diet 도메인 리팩터링 제안서 (공용 모듈 분리)

- 작성일: 2026-07-22
- 최종 수정일: 2026-07-22
- 상태: 제안 (diet 담당자 검토 요청)
- 관련 문서: `.docs/MODULE_OWNERSHIP.md`

> 챗봇 도메인이 합류하면서 `app/llm`·`app/core/dependencies` 같은 공용 모듈을 여러 도메인이 공유하게 되었습니다. 지금 당장은 챗봇 쪽에서 diet 코드를 건드리지 않고 공용 모듈에 **추가만** 하는 방식으로 우회하지만, 중복과 의존성 역방향을 정리하려면 diet 쪽 협조가 필요합니다. 아래는 **강제가 아니라 제안**이며, 우선순위와 타이밍은 diet 담당자가 정하시면 됩니다.

---

## 🎯 배경

`.docs/MODULE_OWNERSHIP.md`에서 팀이 합의하려는 원칙은 다음과 같습니다.

> 공용에는 "LLM에 닿는 방법"(연결)만 두고, "기능별 계약"(프롬프트·스키마·정책)은 각 도메인이 소유한다.

이 원칙에 맞춰 보면, 현재 diet 관련 코드 2곳이 공용 위치에 계약을 두고 있어 정리 대상입니다. 아래 제안은 **기능 동작을 바꾸지 않는 순수 이동/분리**이며, 외부 API 계약(`/api/v1/meals/analyze` 요청·응답)에는 영향이 없습니다.

---

## 제안 1 — LLM 계약을 `app/llm`에서 `app/diet`로 이전

### 현재

`app/llm/gemini_adapter.py`에 **연결 생성과 diet 전용 계약이 한 파일에 섞여** 있습니다.

```python
class GeminiAdapter:
    def _get_model(self) -> ChatGoogleGenerativeAI:      # ① 연결 (공용이어야 함)
        ...
    async def generate(self, messages, tools=None):       # 계약
        ...
    async def generate_structured_image(self, *, prompt, image_bytes, mime_type, output_schema):  # ② diet 전용 계약
        ...
```

`generate_structured_image`는 diet의 이미지 분석 전용 계약인데, 공용 위치(`app/llm`)에 있어 다른 도메인이 오해하거나 의존할 여지가 있습니다.

### 제안

- **공용으로 남길 것** (`app/llm/`): `_get_model()`에 해당하는 **연결 팩토리**만. 계약 없는 순수 LangChain chat model을 반환하는 함수(예: `create_chat_model()`)로 노출. 인증키·모델명·타임아웃·`max_retries=0`만 담당.
- **`app/diet/`로 옮길 것**: `generate_structured_image`와 그 Port(`app/llm/port.py`의 diet용 시그니처). diet의 Adapter가 공용 `create_chat_model()`을 주입받아 `.with_structured_output()`을 호출하도록.

```
[공용]  app/llm/create_chat_model()          # 연결만
[diet]  app/diet/.../port.py  (interface)    # 구조화 이미지 분석 계약
        app/diet/.../adapter.py (implements) # create_chat_model() 주입받아 구현
```

### 효과

- diet·챗봇·PT·리포트가 같은 연결 팩토리 1개를 공유하되, 각자 계약은 자기 도메인에 둠 → 도메인 간 결합 제거.
- Spring의 `AiServiceConfig`(공용 빈) + `AiMealAnalysisAdapter`(도메인 계약) 구조와 정확히 대칭.

---

## 제안 2 — diet DI 조립을 `app/core/dependencies.py`에서 `app/diet/dependencies.py`로 이전

### 현재

`app/core/dependencies.py`가 diet를 직접 import합니다. (공용 core가 도메인을 아는 **의존성 역방향**)

```python
# app/core/dependencies.py
from app.diet.analyzer import MealImageAnalyzer   # core → diet 역방향
from app.diet.service import DietService

@lru_cache
def get_diet_service() -> DietService:
    return DietService(MealImageAnalyzer(get_llm_client()))
```

이대로 챗봇·PT·리포트 조립까지 추가되면 이 파일이 4개 도메인을 모두 import하는 God 모듈이 되어, 모든 팀이 같은 파일을 수정하며 충돌합니다. (챗봇은 이를 피하려고 `app/chatbot/dependencies.py`를 별도 신설합니다.)

### 제안

- diet 서비스 조립부(`get_diet_service`, diet용 `get_llm_client`)를 **`app/diet/dependencies.py`로 이전**.
- `app/core/dependencies.py`에는 공용 자원(예: `create_chat_model()` 캐시)만 남김.
- `app/diet/router.py`의 `from app.core.dependencies import get_diet_service`를 `from app.diet.dependencies import get_diet_service`로 변경.

### 효과

- `app/core`가 어떤 도메인도 import하지 않는 단방향 의존성 확립.
- 각 도메인이 자기 조립 파일을 소유해 파일 단위 충돌이 사라짐.

---

## 제안 3 — (선택) `internal_api_key` 타입 정리

### 현재

`app/diet/router.py`가 설정값을 문자열로 직접 비교합니다.

```python
if not api_key or not secrets.compare_digest(api_key, settings.internal_api_key):
```

이 때문에 챗봇 쪽에서 `settings.internal_api_key`를 보안상 `SecretStr`로 승격하려 해도, diet가 `str`을 기대하고 있어 지금은 `str`로 유지하고 있습니다(`app/core/settings.py` 주석 참조).

### 제안

diet가 위 비교를 `secrets.compare_digest(api_key, settings.internal_api_key.get_secret_value())` 형태로 바꿔주면, 공용 설정에서 `internal_api_key`를 `SecretStr`로 승격할 수 있습니다. 로그·응답에 원문이 노출될 위험이 줄어듭니다. (제안 1·2보다 우선순위 낮음)

---

## 🧭 우선순위와 타이밍

| 제안 | 우선순위 | 성격 | 외부 계약 영향 |
| --- | --- | --- | --- |
| 1. LLM 계약 분리 | 높음 | 순수 이동 | 없음 |
| 2. DI 조립 분리 | 높음 | 순수 이동 | 없음 |
| 3. SecretStr 정리 | 낮음(선택) | 소규모 변경 | 없음 |

- 세 제안 모두 **기능 동작과 외부 API 계약을 바꾸지 않는** 내부 구조 정리입니다.
- 챗봇 구현은 이 리팩터링을 **기다리지 않고** 진행 가능합니다(공용 모듈에 추가만 하는 방식). 다만 위 정리가 되면 중복과 충돌 위험이 사라집니다.
- 타이밍은 diet가 Spring `ai.service` 공용 빈 이관 작업을 하는 시점에 함께 진행하면 자연스럽습니다.

---

## 📝 변경 이력

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-07-22 | 공용 모듈 분리를 위한 diet 리팩터링 제안 초안 작성 |
