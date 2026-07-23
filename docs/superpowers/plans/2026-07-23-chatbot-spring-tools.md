# Chatbot Spring Tools Implementation Plan

> Status: **Completed on 2026-07-23**. Verification: focused chatbot suite 72 passed; full non-smoke suite 193 passed, 3 skipped, 3 deselected.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI LangGraph Function Calling이 Spring의 챗봇 내부 읽기 도구 두 개를 호출하고, 그 결과로 최종 SSE 답변을 생성하게 한다.

**Architecture:** 요청별 `ChatbotToolContext`가 Spring이 준 session/request 식별자를 보관한다. `SpringChatbotToolClient`는 HTTP·응답 검증·오류 변환만 담당하고, `ToolRegistry`는 LLM에 공개할 JSON Schema와 도구 실행을 담당한다. `agent_node`는 레지스트리의 schema를 LLMPort에 전달하고 기존 LangGraph tool node가 결과를 ToolMessage로 연결한다.

**Tech Stack:** FastAPI, httpx, respx, Pydantic v2, LangGraph, LangChain Gemini, pytest.

## Global Constraints

- Spring API는 `GET /internal/chatbot/tools/inbody/latest`, `GET /internal/chatbot/tools/workout-history`만 사용한다.
- Spring은 FastAPI 호출 전에 챗봇 구독을 검증하며, FastAPI는 별도의 구독 조회를 하지 않는다.
- 모든 요청은 `X-Internal-Api-Key`, `X-Chatbot-Session-Id`, `X-Request-ID`를 보낸다.
- LLM tool schema와 호출 인자에 `user_id`를 포함하지 않는다.
- 도구 응답의 `data`만 ToolMessage로 전달한다.
- 자동 테스트에서 실제 Spring 또는 Gemini를 호출하지 않는다.
- 새 의존성은 추가하지 않는다.

---

### Task 0: Spring 챗봇 이용 권한을 Spring에서 검증

**Files:**
- Create: `Gym-Jjak/src/main/java/com/ssambbong/gymjjak/chatbot/application/port/out/ChatbotSubscriptionAccessPort.java`
- Create: `Gym-Jjak/src/main/java/com/ssambbong/gymjjak/chatbot/infrastructure/adapter/out/ChatbotSubscriptionAccessAdapter.java`
- Modify: `Gym-Jjak/src/main/java/com/ssambbong/gymjjak/chatbot/application/service/ChatbotConversationService.java`
- Modify: `Gym-Jjak/src/main/java/com/ssambbong/gymjjak/chatbot/exception/ChatbotErrorCode.java`
- Test: `Gym-Jjak/src/test/java/com/ssambbong/gymjjak/chatbot/application/service/ChatbotConversationServiceTest.java`

**Interfaces:**
- Produces: `ChatbotSubscriptionAccessPort.hasActiveAccess(Long userId): boolean`.
- Consumes: payments/subscription 도메인의 `SubscriptionQueryUseCase`만 사용하며, 다른 도메인의 Repository/JPA entity를 직접 참조하지 않는다.
- Produces: 활성 구독이 없으면 `CHATBOT_SUBSCRIPTION_REQUIRED` 오류로 FastAPI 호출 전에 종료한다.

- [ ] **Step 1: 활성 구독이 없으면 `prepare()`가 챗봇 구독 오류를 던진다는 실패 테스트를 작성한다.**

```java
when(subscriptionAccessPort.hasActiveAccess(USER_ID)).thenReturn(false);

assertThatThrownBy(() -> conversationService.prepare(command()))
        .isInstanceOf(ChatbotSessionException.class)
        .extracting(exception -> ((ChatbotSessionException) exception).getErrorCode())
        .isEqualTo(ChatbotErrorCode.SUBSCRIPTION_REQUIRED);
```

- [ ] **Step 2: 해당 테스트가 새 Port와 오류 코드가 없어 실패하는지 확인한다.**

Run: `./gradlew.bat test --tests "com.ssambbong.gymjjak.chatbot.application.service.ChatbotConversationServiceTest"`

Expected: compilation 또는 assertion failure.

- [ ] **Step 3: Port/Adapter를 추가하고 `prepare()`에서 세션 잠금·메시지 저장보다 먼저 권한을 검증한다.**

```java
if (!subscriptionAccessPort.hasActiveAccess(command.userId())) {
    throw new ChatbotSessionException(ChatbotErrorCode.SUBSCRIPTION_REQUIRED);
}
```

- [ ] **Step 4: Spring 챗봇 서비스 테스트를 실행한다.**

Run: `./gradlew.bat test --tests "com.ssambbong.gymjjak.chatbot.application.service.ChatbotConversationServiceTest"`

Expected: 모든 테스트 통과.

---

### Task 1: Spring 도구 HTTP 클라이언트와 오류 계약

**Files:**
- Create: `app/chatbot/spring_tool_client.py`
- Modify: `app/core/exceptions.py`
- Test: `tests/unit/chatbot/test_spring_tool_client.py`

**Interfaces:**
- Produces: `ChatbotToolContext(session_id: str, request_id: str)`.
- Produces: `SpringChatbotToolClient.get_latest_inbody()`와 `get_workout_history(from_date: date, to_date: date)`.
- Produces: `AppError` 기반 `CHATBOT_TOOL_UNAVAILABLE`, `CHATBOT_TOOL_ACCESS_DENIED`, `CHATBOT_TOOL_RESPONSE_INVALID`.

- [ ] **Step 1: 실패하는 클라이언트 테스트를 작성한다.**

```python
async def test_get_latest_inbody_sends_server_context_headers(respx_mock) -> None:
    client = SpringChatbotToolClient(
        context=ChatbotToolContext(session_id="session-1", request_id="request-1"),
        http_client=httpx.AsyncClient(base_url="http://spring.test"),
    )
    route = respx_mock.get("http://spring.test/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(200, json={"data": None})
    )

    assert await client.get_latest_inbody() is None
    assert route.calls[0].request.headers["X-Chatbot-Session-Id"] == "session-1"
```

- [ ] **Step 2: 테스트가 모듈 없음으로 실패하는지 확인한다.**

Run: `python -m pytest tests/unit/chatbot/test_spring_tool_client.py -q`

Expected: `ModuleNotFoundError: app.chatbot.spring_tool_client`.

- [ ] **Step 3: 최소 구현으로 정상 응답·빈 data·오류 변환을 구현한다.**

```python
class SpringChatbotToolClient:
    async def get_latest_inbody(self) -> dict | None:
        return await self._get_data("/internal/chatbot/tools/inbody/latest")

    async def get_workout_history(self, from_date: date, to_date: date) -> dict:
        return await self._get_data(
            "/internal/chatbot/tools/workout-history",
            params={"from": from_date.isoformat(), "to": to_date.isoformat()},
        )
```

- [ ] **Step 4: 클라이언트 테스트를 실행한다.**

Run: `python -m pytest tests/unit/chatbot/test_spring_tool_client.py -q`

Expected: 모든 테스트 통과.

### Task 2: 도구 레지스트리 축소와 LangGraph 도구 schema 등록

**Files:**
- Modify: `app/chatbot/tools.py`
- Modify: `app/chatbot/service.py`
- Modify: `app/chatbot/nodes.py`
- Test: `tests/unit/chatbot/test_tools.py`
- Test: `tests/graph/test_chatbot_graph.py`

**Interfaces:**
- Consumes: Task 1의 `SpringChatbotToolClient`와 요청별 `ChatbotToolContext`.
- Produces: `ToolRegistry.tool_definitions() -> list[dict]`, `ToolRegistry.execute(name, args) -> ToolResult`.
- Produces: Gemini에 전달되는 정확히 두 도구 schema.

- [ ] **Step 1: 기존 7개 도구가 더 이상 노출되지 않고 두 도구만 동작한다는 실패 테스트를 작성한다.**

```python
def test_only_spring_backed_tools_are_registered() -> None:
    assert TOOL_NAMES == ("get_latest_inbody", "get_workout_history")
    schemas = registry.tool_definitions()
    assert all("user_id" not in schema["function"]["parameters"]["properties"] for schema in schemas)
```

- [ ] **Step 2: 테스트가 기존 7개 도구 목록 때문에 실패하는지 확인한다.**

Run: `python -m pytest tests/unit/chatbot/test_tools.py -q`

Expected: `TOOL_NAMES` assertion failure.

- [ ] **Step 3: 레지스트리를 두 실제 도구와 기간 검증으로 교체한다.**

```python
async def execute(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
    if tool_name == "get_latest_inbody":
        return ToolResult(tool_name=tool_name, data=await self._client.get_latest_inbody())
    if tool_name == "get_workout_history":
        from_date, to_date = self._parse_period(args)
        return ToolResult(tool_name=tool_name, data=await self._client.get_workout_history(from_date, to_date))
```

- [ ] **Step 4: service가 `get_request_id()`와 request session_id로 도구 컨텍스트를 만들고, agent_node가 `registry.tool_definitions()`를 `deps.llm.stream(..., tools=...)`로 넘기게 한다.**

- [ ] **Step 5: 단위·그래프 테스트를 실행한다.**

Run: `python -m pytest tests/unit/chatbot/test_tools.py tests/graph/test_chatbot_graph.py -q`

Expected: 모든 테스트 통과.

### Task 3: 회귀 테스트, 문서 최신화, 커밋 검토

**Files:**
- Modify: `app/chatbot/docs/IMPLEMENTATION_PLAN.md`
- Modify: `.docs/SPRING_INTEGRATION.md`
- Test: `tests/unit/chatbot/test_service.py`, `tests/integration/chatbot/test_chat_api.py`

- [ ] **Step 1: 변경된 실제 계약(2개 도구, 3개 헤더, user_id 금지)을 문서에 반영한다.**
- [ ] **Step 2: 챗봇 단위·그래프·통합 테스트를 실행한다.**

Run: `python -m pytest tests/unit/chatbot tests/graph tests/integration/chatbot -q`

Expected: 모든 테스트 통과.

- [ ] **Step 3: 전체 자동 테스트와 정적 점검을 실행한다.**

Run: `python -m pytest -m "not smoke" -q`

Expected: 실패 0건.

Run: `python -m compileall app tests`

Expected: syntax error 없음.

Run: `git diff --check`

Expected: 출력 없음.

- [ ] **Step 4: 변경 파일과 diff를 채팅에 먼저 공유하고 승인 후 기능 단위 커밋을 만든다.**

```bash
git add app/chatbot app/core/exceptions.py tests/unit/chatbot tests/graph docs/superpowers .docs
git commit -m "feat: Spring 챗봇 내부 도구 연동 구현"
```
