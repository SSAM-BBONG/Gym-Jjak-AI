# 🤖 챗봇 Spring Function Calling 도구 계약

- 최종 수정일: 2026-07-23
- 상태: 구현 완료 — FastAPI `SpringChatbotToolClient`와 Spring 내부 도구 API가 연동된다.

## 🧭 책임과 호출 흐름

```text
Spring WebSocket 요청
  → Spring이 사용자 인증 및 활성 구독 검증
  → FastAPI SSE 요청 (session_id, request_id, actor)
  → LangGraph agent_node가 Gemini에 도구 스키마 전달
  → tool_node가 Spring 내부 조회 API 호출
  → 도구 data를 ToolMessage로 Gemini에 전달
  → 최종 답변을 SSE done 이벤트로 Spring에 반환
```

## 🧠 Gemini 다중 도구 호출 규칙

Gemini 2.5+/3 계열은 Function Calling 후속 요청에서 각 `functionCall`의 `thought_signature`를 그대로 되돌려 받아야 한다. `GeminiAdapter.stream()`은 스트리밍 청크마다 도착한 서명 맵을 도구 호출 ID 기준으로 누적 병합하고, `ToolCall`과 후속 `AIMessage`에 함께 보존한다.

이 규칙은 한 번의 모델 응답에서 InBody와 운동 이력처럼 여러 도구를 동시에 호출해도 적용된다. 마지막 청크의 서명 맵으로 앞선 값을 덮어쓰면 Gemini가 후속 호출을 `400 INVALID_ARGUMENT`으로 거절한다.

- FastAPI는 구독을 다시 조회하지 않는다. Spring이 FastAPI 호출 전에 검증하고, 실패하면 FastAPI를 호출하지 않는다.
- LLM 도구 인자에는 `user_id`가 없다. Spring이 `X-Chatbot-Session-Id`, `X-Request-ID`로 활성 스트림과 소유 사용자를 검증한다.
- FastAPI는 RDS에 직접 접근하지 않으며, 등록된 도구는 모두 읽기 전용 GET이다.

## 🔐 공통 요청 헤더

모든 FastAPI→Spring 도구 요청은 다음 헤더를 포함한다.

```text
X-Internal-Api-Key: {INTERNAL_API_KEY}
X-Chatbot-Session-Id: {session_id}
X-Request-ID: {request_id}
```

`httpx.AsyncClient`는 챗봇 요청 단위로 생성하고 SSE 스트림 종료 후 닫는다. 따라서 서로 다른 사용자의 session/request 컨텍스트가 섞이지 않는다.

## 🛠️ 등록 도구

| Function name | Spring API | 인자 | `data` 응답 |
| --- | --- | --- | --- |
| `get_latest_inbody` | `GET /internal/chatbot/tools/inbody/latest` | 없음 | `null` 또는 `measuredDate`, `weight`, `bodyFatPercentage`, `skeletalMuscleMass` |
| `get_workout_history` | `GET /internal/chatbot/tools/workout-history` | `from`, `to` (ISO 날짜, 1~31일) | `from`, `to`, `diaries[]` |

도구 결과에서는 Spring 응답 envelope의 `data`만 LLM에 전달한다. 인증 헤더, HTTP 상태, 사용자 식별 정보는 모델에 노출하지 않는다.

## ⚠️ 오류 매핑

| Spring 호출 결과 | FastAPI 오류 코드 | 재시도 |
| --- | --- | --- |
| 연결 실패·timeout·5xx | `CHATBOT_TOOL_UNAVAILABLE` (503) | 없음 |
| 401·403 | `CHATBOT_TOOL_ACCESS_DENIED` | 없음 |
| 200이 아닌 나머지 상태·잘못된 JSON/DTO | `CHATBOT_TOOL_RESPONSE_INVALID` | 없음 |

응답 DTO 검증은 `app/chatbot/spring_tool_client.py`에서 수행한다. InBody의 `data: null`만 정상적인 데이터 부재로 허용하며, 운동 이력은 유효한 기간과 diary 구조가 필요하다.

## 🧪 검증 범위

- `tests/unit/chatbot/test_spring_tool_client.py`: 헤더, 상태 코드, DTO, 오류 변환
- `tests/unit/chatbot/test_tools.py`: 도구 스키마와 인자 검증
- `tests/unit/llm/test_gemini_adapter_stream.py`: 다중 도구 호출 스트림의 `thought_signature` 누적 보존
- `tests/graph/test_chatbot_graph.py`: LangGraph 도구 실행과 구독 재조회 금지
- `tests/unit/chatbot/test_service.py`: 요청 단위 HTTP 클라이언트와 SSE 통합
