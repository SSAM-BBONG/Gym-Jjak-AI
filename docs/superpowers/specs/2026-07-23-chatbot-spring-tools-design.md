# 🔌 챗봇 Spring 내부 도구 연동 설계

- 작성일: 2026-07-23
- 상태: 구현 완료
- 범위: FastAPI의 LangGraph Function Calling이 Spring 챗봇 내부 읽기 API를 호출하도록 전환한다.

## 목표

기존의 `FakeUserDataClient` 기반 개인 데이터 도구 7개를 운영 경로에서 제거한다. 대신 현재 Spring에 구현된 다음 두 읽기 전용 도구만 LLM에 공개한다.

- `get_latest_inbody()`
- `get_workout_history(from, to)`

도구 결과는 최종 답변을 만드는 근거일 뿐, Spring 응답 원문이나 내부 인증 헤더를 프론트엔드에 직접 노출하지 않는다.

## 선택한 접근

`app/chatbot` 안에 요청별 `ChatbotToolClient`를 둔다. 클라이언트는 `httpx.AsyncClient`로 Spring의 `/internal/chatbot/tools` API를 호출하고, 도구 레지스트리는 그 클라이언트만 호출한다.

대안으로 기존 `UserDataClient`의 7개 메서드를 Spring 구현체로 바꾸는 방법도 있으나, 현재 Spring이 제공하지 않는 결제·구독·PT API까지 계약에 남겨 잘못된 도구 노출을 유발한다. 전역 가변 컨텍스트에 세션 정보를 저장하는 방법은 동시 요청 사이에 신원이 섞일 수 있어 사용하지 않는다.

## 구성과 데이터 흐름

1. Spring은 인증된 회원 역할과 활성 챗봇 구독을 먼저 검증한다. 구독이 없으면 FastAPI를 호출하지 않는다.
2. Spring은 FastAPI 요청 본문의 `session_id`와 `X-Request-ID`를 전달한다.
3. `ChatbotService`는 매 대화 요청마다 `ChatbotToolContext(session_id, request_id)`와 `ChatbotToolClient`를 만들어 `ToolRegistry`에 주입한다.
4. Gemini는 `get_latest_inbody()` 또는 `get_workout_history(from, to)`만 Function Call로 요청할 수 있다. `user_id`는 JSON Schema와 함수 인자 모두에 없다.
5. `ToolRegistry`는 `X-Internal-Api-Key`, `X-Chatbot-Session-Id`, `X-Request-ID` 헤더를 붙여 Spring을 호출한다.
6. Spring이 세션 소유자와 활성 요청의 만료 여부를 검증한 뒤 데이터를 반환한다.
7. FastAPI는 필요한 데이터만 `ToolMessage`로 모델에 전달한다. Gemini 2.5+/3 계열의 다중 도구 호출에서는 각 `functionCall`의 `thought_signature`를 스트리밍 청크 전체에서 호출 ID별로 누적 보존해 후속 모델 요청에 다시 전달한다.
8. 모델의 최종 답변만 기존 SSE `done` 이벤트로 Spring에 반환한다.

## HTTP 계약과 검증

| 도구 | Spring 요청 | 허용 인자 | 응답 변환 |
| --- | --- | --- | --- |
| `get_latest_inbody` | `GET /internal/chatbot/tools/inbody/latest` | 없음 | `data`가 `null`이면 `null`, 아니면 측정일·체중·체지방률·골격근량 |
| `get_workout_history` | `GET /internal/chatbot/tools/workout-history` | `from`, `to` (`date`) | 기간과 운동일지의 날짜·운동명·부위·세트 수 |

- 운동일지 기간은 Spring 규칙대로 1~31일이어야 한다. FastAPI도 호출 전 날짜 형식과 `from <= to`를 검증해 불필요한 내부 요청을 막는다.
- 도구는 어떤 경우에도 `user_id`, `actor.user_id`, API key, 세션 소유자 정보를 모델에 전달하지 않는다.
- FastAPI는 Spring의 응답 `data` 부분만 ToolMessage 내용으로 직렬화한다.

## 오류 처리

- 연결 실패, 타임아웃, Spring 5xx는 `CHATBOT_TOOL_UNAVAILABLE`로 변환한다. 이 오류는 재시도하지 않는다. Spring의 활성 스트림 유효 시간이 짧으므로 자동 재시도보다 현재 요청을 종료하는 편이 안전하다.
- Spring 400은 LLM에 `TOOL_INPUT_INVALID` 결과로 전달한다. 모델은 올바른 기간으로 한 번 더 요청할 수 있다.
- Spring 401/403은 서버 인증 또는 세션·요청 검증 실패이므로 `CHATBOT_TOOL_ACCESS_DENIED`로 변환하고 SSE `error`로 종료한다.
- 응답 JSON이 계약과 다르면 `CHATBOT_TOOL_RESPONSE_INVALID`로 변환한다.

## 테스트 범위

- HTTP 클라이언트: 헤더 3종, 두 API의 정상·빈 데이터 매핑, 상태별 예외 변환을 `respx`로 검증한다.
- 도구 레지스트리: 등록된 도구가 정확히 2개인지, `user_id`가 도구 스키마·호출 인자에 없는지, 기간 검증을 확인한다.
- 그래프/서비스: 두 도구의 결과가 `ToolMessage`를 거쳐 최종 SSE `done` 답변으로 이어지는지 검증한다.
- Gemini 어댑터: 다중 도구 호출의 서명이 서로 다른 스트리밍 청크에 나뉘어도 모든 `ToolCall`에 보존되는지 검증한다.
- 자동 테스트는 실제 Spring·Gemini를 호출하지 않는다.

## 범위 밖

- 결제, 구독, PT, 온보딩 도구의 Spring API 추가
- 대화 저장소 또는 `ConversationProvider`의 Spring/Redis 전환
- Spring API key의 배포·로테이션 설정
