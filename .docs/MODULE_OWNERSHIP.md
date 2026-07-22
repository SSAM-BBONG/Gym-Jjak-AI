# 🧩 FastAPI 모듈 소유권 규칙

- 작성일: 2026-07-22
- 최종 수정일: 2026-07-22
- 상태: 팀 제안 (합의 전)
- 대상: Gym-Jjak-fastapi AI 서버의 공용 모듈(`app/core`, `app/llm`, `app/common`)을 여러 도메인이 공유하는 상황

> 이 문서는 diet·chatbot·pt_recommendation·trainer_report 4개 도메인이 같은 FastAPI 저장소에서 공용 모듈을 공유할 때 발생하는 충돌을 예방하기 위한 소유권 규칙이다. Spring(Gym-Jjak)의 `global` 공용 빈 + 도메인별 어댑터 구조와 대칭이 되도록 설계했다.

---

## 🎯 1. 배경과 원칙

초기 챗봇 설계는 diet 도메인이 없던 시점에 작성되어, 공용 모듈(`app/llm`, `app/core/dependencies` 등)을 챗봇이 자유롭게 재정의할 수 있다고 가정했다. 이후 diet 도메인이 합류해 같은 공용 모듈을 사용하면서, 한쪽의 재작성이 다른 쪽을 파손하는 충돌이 생겼다.

판단 기준은 한 줄로 요약한다.

> **모든 도메인이 동일하게 쓰는 것만 공용에 둔다. 계약(시그니처·프롬프트·정책)이 도메인마다 갈리면 각 도메인이 소유한다.**

Spring 팀원이 진행 중인 리팩터링(`AiServiceConfig` 공용 빈 + 도메인별 `AiXxxClientAdapter`)과 같은 원칙이다.

- **공용이 갖는 것** = "AI 서버(또는 LLM)에 닿는 방법" — 주소·인증키·타임아웃·연결 생성. 4개 도메인이 전부 동일.
- **도메인이 갖는 것** = "그 기능만의 계약" — 엔드포인트/프롬프트, 요청·응답 스키마, 에러 정책, 도구 정의.

---

## 📋 2. 모듈별 소유권 표

| 모듈 | 분류 | 변경 권한 | 비고 |
| --- | --- | --- | --- |
| `app/core/settings.py` | 공용 | 추가는 누구나(append-only), 기존 필드 변경은 합의 | 필드 추가 자유, 삭제·타입 변경 금지 |
| `app/core/exceptions.py` (`AppError`) | 공용 | 기반 클래스는 합의 | 도메인 전용 예외는 각 도메인이 하위 클래스로 소유 |
| `app/core/logging.py` / 요청 미들웨어 | 공용 | 합의 | `X-Request-ID` 전파·처리시간 계측 |
| `app/core/dependencies.py` | 공용(축소) | 공용 자원만 | 도메인 서비스 조립은 각 도메인으로 이전 (§5) |
| `app/llm/` | 공용(연결) + diet 과도기 | §4 참조 | 연결 팩토리는 공용, 계약은 도메인 |
| `main.py` (`create_app`) | 공용 | 합의 | 라우터 등록·전역 예외 핸들러 |
| `app/common/` | 공용 경계 | 소유자 표기 | `user_data_client` 등 조회 Port. 챗봇이 신설·소유 |
| `app/rag/`, `app/routine/` | 챗봇 기능 | 챗봇 | 챗봇 전용, 타 도메인 미사용 |
| `app/diet/` | diet | diet | diet 도메인 전용 |
| `app/chatbot/` | chatbot | chatbot | 챗봇 도메인 전용 |

---

## 🔒 3. 공용 모듈 변경 규칙

공용 모듈(§2에서 "공용")을 수정할 때 지킨다.

1. **append-only 우선**: 필드·함수·예외 클래스 추가는 자유. 기존 시그니처·필드·기본값의 **변경/삭제는 금지**하고, 필요하면 채팅으로 합의한다.
2. **파괴적 변경은 사전 공유**: 공용 심볼의 이름·타입·반환값을 바꿔야 하면 영향받는 도메인 담당자에게 먼저 알린다.
3. **의존성 단방향**: `app/core`는 어떤 도메인(`app/diet`, `app/chatbot` 등)도 import하지 않는다. 도메인이 core를 import한다. (현재 위반 사항은 §5의 과도기 예외 참조)
4. **도메인 코드 무수정**: 자기 담당이 아닌 도메인 폴더는 수정하지 않는다. 공용 모듈을 통해서만 상호작용한다.

---

## 🤖 4. LLM 계층 소유권

LLM 계층은 세 층으로 분리한다. Java의 `@Bean` + `interface` + `implements` 구조와 동일하다.

| 층 | 위치 | Java 대응 | 소유자 | 담당 |
| --- | --- | --- | --- | --- |
| ① 연결 팩토리 (구체) | `app/llm/` | `@Bean aiServiceRestClient` | 공용 | 인증키·모델명·타임아웃·`max_retries=0`로 LangChain chat model 생성 |
| ② Port (interface) | 각 도메인 | `interface ChatbotPort` | 도메인 | 그 도메인의 LLM 계약 정의 |
| ③ Adapter (implements) | 각 도메인 | `class AiChatbotAdapter implements ChatbotPort` | 도메인 | 공용 chat model을 주입받아 자기 계약 구현 |

### 목표 구조

```
[공용]  app/llm/            → create_chat_model() : 계약 없는 순수 LangChain chat model 반환
                              (Spring의 aiServiceRestClient @Bean과 동일 역할)

[diet]  Port     : 구조화 이미지 분석 계약 (generate_structured_image)
        Adapter  : create_chat_model() 주입 → .with_structured_output() 호출

[챗봇]  Port     : 대화 + tool 계약 (generate(LLMRequest) -> LLMResponse)
        Adapter  : 같은 create_chat_model() 주입 → tool binding 호출
```

각 도메인은 자기 Port만 알면 되고, 공용 팩토리 하나를 여럿이 주입받아도 도메인 간 결합이 생기지 않는다.

### 현재 상태와 과도기 처리

현재 `app/llm/gemini_adapter.py`는 ① 연결(`_get_model`)과 diet 계약(`generate`, `generate_structured_image`)이 **한 파일에 섞여** 있다. diet 무수정 제약 때문에 다음과 같이 처리한다.

- **지금**: 챗봇은 `app/llm/`을 재작성하지 않는다. 공용 연결 팩토리를 `app/llm/`에 **추가만(append)** 하고, 챗봇 Port·Adapter는 `app/chatbot/` 안에 신설한다. diet 파일은 건드리지 않는다.
- **미래 정리 항목**: diet 계약(`generate_structured_image`)을 `app/diet/`로 이전하고, 공용 `app/llm/`은 연결 팩토리만 남긴다. → `.docs/DIET_REFACTOR_PROPOSAL.md` 참조.

> ⚠️ 이 결정으로 초기 챗봇 계획서 Task 2("`app/llm/port.py` 재작성")는 **"챗봇 전용 LLM 계약 신설, 공용 `app/llm` 미변경"**으로 수정된다.

---

## 🔧 5. DI 조립부(`dependencies.py`) 규칙

- **공용** `app/core/dependencies.py`(또는 `app/llm/`): 계약 없는 공용 자원만 조립한다. 예: `create_chat_model()` 캐시 제공.
- **도메인** `app/<domain>/dependencies.py`: 공용 팩토리를 주입받아 자기 서비스를 조립한다. 챗봇은 `app/chatbot/dependencies.py`를 신설·소유한다.
- **규칙**: `app/core/dependencies.py`는 도메인을 import하지 않는다(§3.3). 도메인 조립은 도메인 파일에서 한다.

### 과도기 예외

현재 `app/core/dependencies.py`는 `get_diet_service`/`get_llm_client`에서 `app/diet`를 import한다(의존성 방향 위반). diet 무수정 제약으로 지금은 그대로 두고, **미래 정리 항목**으로 diet가 `app/diet/dependencies.py`로 이전한다. 챗봇은 이 파일을 확장하지 않고 `app/chatbot/dependencies.py`를 신설하므로 물리적으로 충돌하지 않는다.

> ⚠️ 이 결정으로 초기 챗봇 계획서 Task 12("`core/dependencies.py`에 챗봇 조립 추가")는 **"`app/chatbot/dependencies.py` 신설"**로 수정된다.

---

## 🪞 6. Spring 대칭성 메모

| 관점 | Spring (Gym-Jjak) | FastAPI (Gym-Jjak-fastapi) |
| --- | --- | --- |
| 공용 = 연결 방법 | `global/.../AiServiceConfig` (`aiServiceRestClient` 빈) | `app/llm/create_chat_model()` |
| 도메인 = 계약 | `diet/adapter/out/ai/AiMealAnalysisAdapter` | `app/diet` Port·Adapter |
| 신규 도메인 | `chat/adapter/out/ai/AiChatbotAdapter` | `app/chatbot` Port·Adapter |
| 공용 설정 위치 | `application.yml`의 `ai.service.*` | `app/core/settings.py` 공용 필드 |
| 팀 규칙 문서 | (해당 팀 컨벤션) | 본 문서 `.docs/MODULE_OWNERSHIP.md` |

Spring 어댑터와 FastAPI 라우터/어댑터가 1:1로 대응되어, 양쪽 저장소를 오갈 때 구조가 대칭이 된다.

---

## 📝 변경 이력

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-07-22 | diet 합류 이후 공용 모듈 소유권 규칙 초안 작성 |
