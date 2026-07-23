# 챗봇 응답 스트리밍(SSE) 설계

- 날짜: 2026-07-22
- 대상: `app/chatbot` 도메인 `POST /api/v1/chatbot/messages`
- 작성 배경: 프론트엔드가 챗봇 답변을 스트리밍으로 받을 수 있도록, AI 서버(FastAPI) → Spring 구간을 SSE로 전환한다. Spring → 프론트 구간 구현은 이 스펙 범위 밖이며 Spring 팀에 별도 전달한다.

## 범위

- **포함**: AI 서버가 Spring에 SSE로 응답. `personal`(agent_node 최종 답변), `service_policy`(rag_node)는 실제 LLM 토큰 단위 스트리밍. `routine`, `reject`는 완성된 답변을 단일 delta로 전송.
- **제외**: Spring ↔ 프론트 스트리밍 연동(별도 문서/작업), 기존 non-streaming 엔드포인트의 병행 유지(사용하지 않을 것으로 판단해 교체).
- 기존 `POST /api/v1/chatbot/messages`를 스트리밍 방식으로 **교체**한다(신규 별도 경로를 만들지 않음).

## 전체 아키텍처

```
Router: POST /api/v1/chatbot/messages → StreamingResponse(text/event-stream)
  ↓
Service.chat(request) -> AsyncIterator[str]  (SSE 포맷 문자열 yield)
  - asyncio.Queue 생성 → config["configurable"]["stream_queue"] = queue
  - asyncio.create_task(graph.ainvoke(initial_state, config))  ← 그래프 구조는 기존과 동일
  - while: queue에서 델타를 꺼내 SSE로 yield, task 완료되면 종료
  - task 완료 후 최종 state 확인:
      error_code 있음 → event: error
      없음          → event: done (answer 전체, category, routine, sources, limited)
```

`graph.py`/`nodes.py`의 라우팅 로직과 도구 호출 반복 구조는 그대로 유지한다. 그래프를 access_guard/intent_router 단계와 분리하지 않고 **단일 `graph.ainvoke()`** 호출로 실행한다(에러 처리 단순화 결정에 따름 — 아래 참고).

## 컴포넌트별 변경

- **`app/llm/port.py`**: `LLMPort`에 `stream()` 메서드 추가.
  - `async def stream(self, messages: list[LLMMessage], tools=None) -> AsyncIterator[LLMStreamChunk]`
  - `LLMStreamChunk`: 텍스트 델타(`delta: str`) 또는 스트림 종료 시 최종 `LLMResponse`(전체 text + tool_calls + thought_signature) 중 하나를 담는 간단한 유니온 타입.
- **`app/llm/gemini_adapter.py`**: `stream()`을 `langchain_google_genai`의 `astream()`으로 구현. 청크마다 텍스트 조각을 yield, 마지막에 누적된 tool_calls/thought_signature를 포함한 최종 응답을 yield.
- **`app/chatbot/nodes.py`**:
  - `agent_node`, `rag_node`: `deps.llm.generate(...)` 호출을 `deps.llm.stream(...)`으로 교체. 델타가 나올 때마다 `config["configurable"]["stream_queue"].put(delta)`.
  - tool_calls를 결정하는 중간 호출도 동일하게 `stream()`을 쓰지만, 이런 턴은 일반적으로 텍스트 콘텐츠가 비어 있으므로 델타가 실질적으로 전송되지 않는다(Gemini function calling 특성에 대한 가정 — 실제 검증 필요).
  - `routine_node`, `reject_node`: 변경 없음. 완성된 answer는 서비스 레이어가 `done` 이벤트에 한 번에 담아 보낸다.
- **`app/chatbot/service.py`**: `chat()`을 async generator로 변경, SSE 문자열을 yield.
- **`app/chatbot/router.py`**: `StreamingResponse(service.chat(request), media_type="text/event-stream")`로 교체.
- **`app/chatbot/schemas.py`**: 기존 `ChatResponse`를 `done` 이벤트 payload로 재사용. `error` 이벤트용 스키마(code/message/request_id/retryable)를 추가.

## SSE 이벤트 포맷

```
event: delta
data: {"text": "안녕"}

event: done
data: {"request_id": "...", "session_id": "...", "answer": "...", "category": "...", "routine": null, "sources": [], "limited": false}

event: error
data: {"code": "CHATBOT_SUBSCRIPTION_REQUIRED", "message": "...", "request_id": "...", "retryable": false}
```

## 에러 & 타임아웃 처리

- **단순화 결정**: access_guard 실패를 포함한 모든 에러를 항상 SSE `event: error`로 통일한다. HTTP status 코드 분기(4xx)는 포기한다. 스트림은 항상 200 OK로 시작한다.
  - 기존 `_ERROR_CODE_TO_EXCEPTION` 매핑(ROLE_NOT_ALLOWED, CHATBOT_SUBSCRIPTION_REQUIRED, LLM_CALL_LIMIT_EXCEEDED)은 그대로 두되, 예외를 raise하는 대신 인스턴스를 생성해 `code`/`message`/`retryable` 속성만 꺼내 error 이벤트로 변환한다.
  - Spring 쪽은 HTTP status 대신 이벤트 body의 `code` 필드로 에러 종류를 분기해야 한다(Spring 팀 전달 필요 사항).
- **타임아웃**: 기존 `asyncio.wait_for(graph.ainvoke(...), timeout=...)` 구조를 유지하되, 백그라운드 task에 타임아웃을 걸고 큐 소비 루프에서 타임아웃이 발생하면 `ChatRequestTimeoutError`에 해당하는 error 이벤트를 보내고 스트림을 종료한다.
- **클라이언트 연결 끊김**: `request.is_disconnected()`를 체크해 Spring이 연결을 끊으면 백그라운드 task를 `cancel()`한다(불필요한 LLM 호출 방지 — 현재 non-streaming 구조엔 없는 신규 로직).
- **미매핑 예외(버그 등)**: try/except로 감싸 `INTERNAL_ERROR` 성격의 일반 error 이벤트로 변환 후 스트림을 정상 종료한다(무한 대기/커넥션 hang 방지).
- **persist_node**: 변경 없음. 그래프가 끝까지 실행되므로 기존 로직 그대로 최종 답변 저장 여부를 처리한다.

## 테스트 전략

- `LLMPort.stream()` / `GeminiAdapter.stream()`: 텍스트 델타 여러 개 + tool_calls 없는 최종 응답 케이스, 텍스트 없음 + tool_calls 있는 케이스 각각 모킹해 단위 테스트.
- `agent_node`/`rag_node`: `deps.llm`을 stub으로 교체해 `stream()` 호출 여부, 큐에 델타가 순서대로 쌓이는지, tool_calls 있으면 기존처럼 `pending_tool_calls`를 반환하는지 검증(기존 `generate()` 테스트를 `stream()` 버전으로 갱신).
- `ChatbotService.chat()`: 그래프를 스텁으로 교체해 SSE 문자열 시퀀스(`delta`→`delta`→`done`, 혹은 `error`)가 올바른 포맷으로 나오는지 검증. httpx `AsyncClient`로 라우터까지 통합 테스트해 `text/event-stream` 응답을 파싱, 이벤트 타입/순서 확인.
- 타임아웃/연결 끊김: 느린 stub LLM으로 타임아웃 유도 → `error` 이벤트로 끝나는지, `request.is_disconnected()` 시 백그라운드 task가 취소되는지 검증.
- 기존 회귀 테스트: `generate()` → `stream()` 시그니처 변경에 따라 관련 테스트만 업데이트하고, 나머지는 그대로 통과하는지 확인.

## 확인이 필요한 사항 (저장소 밖 상태)

- Spring 팀이 SSE(`text/event-stream`) 응답을 소비할 준비가 되어 있는지, 그리고 에러를 HTTP status 대신 이벤트 body의 `code` 필드로 분기하는 방식에 동의하는지 확인 필요.
- Gemini function calling 중간 턴에서 텍스트 콘텐츠가 실제로 비어 있는지(델타 유출 없음 가정)는 실제 스트리밍 응답으로 검증 필요.
