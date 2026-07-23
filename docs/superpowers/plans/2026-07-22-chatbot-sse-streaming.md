# 챗봇 SSE 스트리밍 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /api/v1/chatbot/messages`가 완성된 JSON 대신 SSE(`text/event-stream`)로 답변을 흘려보내도록 바꿔서, Spring이 프론트까지 스트리밍을 이어갈 수 있게 한다.

**Architecture:** LangGraph 그래프 구조(`graph.py`/`nodes.py`의 라우팅·도구 호출 반복)는 그대로 유지한다. `agent_node`/`rag_node`가 LLM을 호출하는 지점만 `LLMPort.generate()`에서 새로 추가하는 `LLMPort.stream()`으로 바꿔 텍스트 델타를 `asyncio.Queue`에 흘려보내고, `ChatbotService.chat()`은 그래프 실행을 백그라운드 task로 돌리면서 큐를 소비해 SSE 문자열을 yield하는 async generator로 바뀐다. 에러는 access_guard 실패든 타임아웃이든 전부 `event: error`로 통일한다(HTTP status 분기 없음, 스트림은 항상 200으로 시작).

**Tech Stack:** FastAPI `StreamingResponse`, `asyncio.Queue`/`asyncio.create_task`, `langchain_google_genai`의 `ChatGoogleGenerativeAI.astream()`, 기존 LangGraph/Pydantic 스택.

## Global Constraints

- 모든 설명/커밋 메시지/주석은 한국어로 작성한다 (CLAUDE.md).
- 계층 구조(Router → Service → Domain → Port/Adapter)를 유지한다. `router.py`는 LangGraph/LangChain/Gemini를 직접 import하지 않는다.
- 기존 네이밍 컨벤션(snake_case 함수/모듈, PascalCase 클래스)을 따른다.
- 에러 응답 계약은 `{code, message, request_id, retryable}` 형태를 SSE `error` 이벤트 payload에서도 그대로 유지한다(`app/core/exceptions.py`의 `AppError` 필드와 동일).
- 스펙 문서: `docs/superpowers/specs/2026-07-22-chatbot-streaming-design.md`.
- 기존 `POST /api/v1/chatbot/messages` 엔드포인트를 스트리밍 방식으로 **교체**한다(신규 경로 추가 아님).
- 각 태스크 끝에 관련 테스트를 실행해 통과를 확인하고 커밋한다.

---

## Task 1: `LLMStreamChunk` 모델 + `LLMPort.stream()` 프로토콜 선언

**Files:**
- Modify: `app/llm/models.py`
- Modify: `app/llm/port.py`

**Interfaces:**
- Produces: `LLMStreamChunk(delta: str | None = None, response: LLMResponse | None = None)` — 텍스트 조각이면 `delta`만, 스트림의 마지막 청크는 `response`만 채워서 온다. 이후 모든 태스크가 이 타입을 소비한다.
- Produces: `LLMPort.stream(self, messages: list[LLMMessage], tools: list[Callable] | None = None) -> AsyncIterator[LLMStreamChunk]` — Protocol 멤버 선언(구현은 Task 2/3).

- [ ] **Step 1: `app/llm/models.py`에 `LLMStreamChunk` 추가**

`app/llm/models.py` 끝(현재 36줄 `LLMResponse` 클래스 뒤)에 추가:

```python
class LLMStreamChunk(BaseModel):
    """LLM 스트리밍 응답 조각. delta가 있으면 텍스트 토큰 조각이고, response가 있으면
    스트림의 마지막 청크로 전체 텍스트+tool_calls가 담긴 최종 응답이다.
    한 청크에 delta와 response가 동시에 채워지는 일은 없다."""

    delta: str | None = None
    response: LLMResponse | None = None
```

- [ ] **Step 2: `app/llm/port.py`에 `stream()` Protocol 멤버 추가**

`app/llm/port.py` 상단 import를 다음으로 교체:

```python
from typing import AsyncIterator, Callable, Protocol, TypeVar

from pydantic import BaseModel

from app.llm.models import LLMMessage, LLMResponse, LLMStreamChunk
```

`class LLMPort(Protocol):` 안, `generate()` 메서드 바로 뒤(`generate_structured_image` 앞)에 추가:

```python
    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[Callable] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """대화 메시지 목록으로 1회 호출하되, 텍스트를 토큰 단위로 흘려보낸다.
        마지막에 tool_calls까지 포함한 전체 응답을 담은 청크를 낸다."""
        ...
```

- [ ] **Step 3: import 확인**

Run: `python -c "from app.llm.port import LLMPort; from app.llm.models import LLMStreamChunk; print('ok')"`
Expected: `ok` 출력 (import 오류 없음)

- [ ] **Step 4: 커밋**

```bash
git add app/llm/models.py app/llm/port.py
git commit -m "feat: LLMPort에 스트리밍 인터페이스(stream/LLMStreamChunk) 추가"
```

---

## Task 2: `GeminiAdapter.stream()` 구현 + 단위 테스트

**Files:**
- Modify: `app/llm/gemini_adapter.py`
- Test: `tests/unit/llm/test_gemini_adapter_stream.py` (신규)

**Interfaces:**
- Consumes: `LLMStreamChunk`, `LLMPort.stream()` 시그니처 (Task 1)
- Consumes: 기존 `_to_langchain_message`, `_raise_for_gemini_error`, `_extract_text`, `_THOUGHT_SIGNATURE_KEY` (모두 `app/llm/gemini_adapter.py`에 이미 존재)
- Produces: `GeminiAdapter.stream(messages, tools=None) -> AsyncIterator[LLMStreamChunk]` — 이후 Task 4(agent_node/rag_node)가 실제 운영 경로에서 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/llm/test_gemini_adapter_stream.py` 생성:

```python
"""GeminiAdapter.stream()의 델타 순서와 최종 응답 조립을 검증한다.
generate()와 동일하게 오류 분류(429/INVALID_ARGUMENT/기타)와 thought_signature
추출도 스트리밍 경로에서 그대로 동작해야 한다."""

import pytest
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from app.llm.errors import LLMInvalidResponseError, LLMNetworkError
from app.llm.gemini_adapter import GeminiAdapter, _THOUGHT_SIGNATURE_KEY
from app.llm.models import LLMMessage


class _FakeChunk:
    def __init__(self, *, content="", tool_calls=None, additional_kwargs=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.additional_kwargs = additional_kwargs or {}


def _adapter_with_astream(chunks: list[_FakeChunk] | None = None, side_effect=None) -> GeminiAdapter:
    adapter = GeminiAdapter()

    async def _fake_astream(_messages):
        if side_effect is not None:
            raise side_effect
        for chunk in chunks or []:
            yield chunk

    fake_model = type("FakeBaseModel", (), {"astream": _fake_astream})()
    adapter._model = fake_model
    return adapter


async def test_stream_yields_text_deltas_in_order_then_final_response() -> None:
    adapter = _adapter_with_astream([_FakeChunk(content="안녕"), _FakeChunk(content="하세요")])

    chunks = [c async for c in adapter.stream([LLMMessage(role="user", content="안녕")])]

    assert [c.delta for c in chunks if c.delta] == ["안녕", "하세요"]
    assert chunks[-1].response.text == "안녕하세요"
    assert chunks[-1].response.tool_calls == []


async def test_stream_carries_tool_calls_and_thought_signature_in_final_response() -> None:
    adapter = _adapter_with_astream([
        _FakeChunk(
            tool_calls=[{"name": "get_payment_history", "args": {}, "id": "call-1"}],
            additional_kwargs={_THOUGHT_SIGNATURE_KEY: {"call-1": "c2ln"}},
        ),
    ])

    chunks = [c async for c in adapter.stream([LLMMessage(role="user", content="결제 내역")])]

    final = chunks[-1].response
    assert final.text is None
    assert final.tool_calls[0].name == "get_payment_history"
    assert final.tool_calls[0].thought_signature == "c2ln"


async def test_stream_raises_invalid_response_when_no_text_or_tool_calls() -> None:
    adapter = _adapter_with_astream([_FakeChunk(content="")])

    with pytest.raises(LLMInvalidResponseError):
        async for _ in adapter.stream([LLMMessage(role="user", content="hi")]):
            pass


async def test_stream_classifies_invalid_argument_as_invalid_response_not_network() -> None:
    error = ChatGoogleGenerativeAIError(
        "Error calling model (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. missing thought_signature"
    )
    adapter = _adapter_with_astream(side_effect=error)

    with pytest.raises(LLMInvalidResponseError):
        async for _ in adapter.stream([LLMMessage(role="user", content="hi")]):
            pass


async def test_stream_classifies_other_errors_as_network() -> None:
    error = ChatGoogleGenerativeAIError("Error calling model: 503 Service Unavailable")
    adapter = _adapter_with_astream(side_effect=error)

    with pytest.raises(LLMNetworkError):
        async for _ in adapter.stream([LLMMessage(role="user", content="hi")]):
            pass
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/unit/llm/test_gemini_adapter_stream.py -v`
Expected: FAIL — `AttributeError: 'GeminiAdapter' object has no attribute 'stream'`

- [ ] **Step 3: `GeminiAdapter.stream()` 구현**

`app/llm/gemini_adapter.py` 상단 import에 `AsyncIterator` 추가:

```python
from typing import AsyncIterator, Callable
```

`generate()` 메서드(현재 101~134줄) 바로 뒤, `generate_structured_image()` 앞에 추가:

```python
    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[Callable] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """generate()와 같은 호출을 토큰 단위로 흘려보낸다. tool_calls는 일반적으로
        마지막 청크에만 전체가 채워져 오므로, 각 청크의 tool_calls를 그때그때 최신값으로
        덮어써서 최종 청크의 값을 쓴다(langchain-google-genai 스트리밍 응답 구조 기준)."""
        base_model = self._get_model()
        model = base_model.bind_tools(tools) if tools else base_model
        langchain_messages = [_to_langchain_message(m) for m in messages]

        text_parts: list[str] = []
        tool_calls_raw: list[dict] = []
        additional_kwargs: dict = {}
        try:
            async for chunk in model.astream(langchain_messages):
                piece = _extract_text(chunk.content)
                if piece:
                    text_parts.append(piece)
                    yield LLMStreamChunk(delta=piece)
                if chunk.tool_calls:
                    tool_calls_raw = chunk.tool_calls
                if chunk.additional_kwargs:
                    additional_kwargs.update(chunk.additional_kwargs)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise LLMNetworkError(str(e)) from e
        except ChatGoogleGenerativeAIError as e:
            _raise_for_gemini_error(e)

        signature_map = additional_kwargs.get(_THOUGHT_SIGNATURE_KEY, {})
        tool_calls = [
            ToolCall(
                name=tc["name"],
                args=tc["args"],
                id=tc["id"],
                thought_signature=signature_map.get(tc["id"]),
            )
            for tc in tool_calls_raw
        ]
        text = "".join(text_parts) or None

        if text is None and not tool_calls:
            raise LLMInvalidResponseError("Gemini 스트리밍 응답에 text와 tool_calls가 모두 없습니다.")

        yield LLMStreamChunk(response=LLMResponse(text=text, tool_calls=tool_calls))
```

`app/llm/gemini_adapter.py` 상단의 `from app.llm.models import LLMMessage, LLMResponse, ToolCall` 줄을 다음으로 교체:

```python
from app.llm.models import LLMMessage, LLMResponse, LLMStreamChunk, ToolCall
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/unit/llm/test_gemini_adapter_stream.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 기존 `generate()` 테스트 회귀 확인**

Run: `pytest tests/unit/llm -v`
Expected: PASS (기존 `test_gemini_adapter_generate.py`, `test_gemini_adapter_structured.py`, `test_gemini_adapter_tool_calls.py` 포함 전부)

- [ ] **Step 6: 커밋**

```bash
git add app/llm/gemini_adapter.py tests/unit/llm/test_gemini_adapter_stream.py
git commit -m "feat: GeminiAdapter.stream()으로 실제 토큰 스트리밍 구현"
```

---

## Task 3: `FakeLLMPort.stream()` 추가 (테스트 인프라)

**Files:**
- Modify: `tests/fakes/llm.py`
- Test: `tests/unit/llm/test_fake_llm_stream.py` (신규)

**Interfaces:**
- Consumes: `LLMStreamChunk` (Task 1)
- Produces: `FakeLLMPort.stream(messages, tools=None) -> AsyncIterator[LLMStreamChunk]` — Task 4의 그래프 노드 테스트, Task 5의 서비스 테스트가 전부 이 Fake를 통해 스트리밍 경로를 검증한다. 기존 `response`/`responses_queue`/`received_messages`/`received_tools` 필드를 `generate()`와 동일하게 공유한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/llm/test_fake_llm_stream.py` 생성:

```python
"""FakeLLMPort.stream()이 generate()와 같은 response/responses_queue를 공유하며
텍스트가 있으면 델타 1개 + 최종 응답, 텍스트가 없으면(tool_calls만) 최종 응답만
내는지 검증한다. 이 Fake는 이후 그래프 노드/서비스 테스트가 전부 사용한다."""

import pytest

from app.llm.models import LLMResponse, ToolCall
from tests.fakes.llm import FakeLLMPort


async def test_stream_yields_delta_then_final_response_when_text_present() -> None:
    fake = FakeLLMPort(response=LLMResponse(text="안녕하세요"))

    chunks = [c async for c in fake.stream([])]

    assert chunks[0].delta == "안녕하세요"
    assert chunks[1].response.text == "안녕하세요"


async def test_stream_yields_only_final_response_when_text_absent() -> None:
    fake = FakeLLMPort(response=LLMResponse(text="", tool_calls=[
        ToolCall(name="get_pt_usage", args={}, id="call-1")
    ]))

    chunks = [c async for c in fake.stream([])]

    assert len(chunks) == 1
    assert chunks[0].response.tool_calls[0].name == "get_pt_usage"


async def test_stream_consumes_responses_queue_in_order() -> None:
    fake = FakeLLMPort(responses=[LLMResponse(text="첫번째"), LLMResponse(text="두번째")])

    first = [c async for c in fake.stream([])]
    second = [c async for c in fake.stream([])]

    assert first[-1].response.text == "첫번째"
    assert second[-1].response.text == "두번째"


async def test_stream_raises_exception_from_responses_queue() -> None:
    fake = FakeLLMPort(responses=[RuntimeError("boom")])

    with pytest.raises(RuntimeError, match="boom"):
        async for _ in fake.stream([]):
            pass
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/unit/llm/test_fake_llm_stream.py -v`
Expected: FAIL — `AttributeError: 'FakeLLMPort' object has no attribute 'stream'`

- [ ] **Step 3: `FakeLLMPort.stream()` 구현**

`tests/fakes/llm.py` 상단 import를 다음으로 교체:

```python
from typing import Any, AsyncIterator, Callable

from app.llm.models import LLMMessage, LLMResponse, LLMStreamChunk
```

`generate()` 메서드(현재 31~44줄) 바로 뒤에 추가:

```python
    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[Callable] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """generate()와 동일한 response/responses_queue를 재사용한다. 텍스트가 있으면
        델타 1개로 흘려보낸 뒤 최종 응답을 담은 청크를 낸다."""
        self.received_messages.append(messages)
        self.received_tools.append(tools)
        if self.responses_queue:
            next_item = self.responses_queue.pop(0)
            if isinstance(next_item, Exception):
                raise next_item
            response = next_item
        else:
            response = self.response
        if response.text:
            yield LLMStreamChunk(delta=response.text)
        yield LLMStreamChunk(response=response)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/unit/llm/test_fake_llm_stream.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add tests/fakes/llm.py tests/unit/llm/test_fake_llm_stream.py
git commit -m "test: FakeLLMPort에 stream() 추가"
```

---

## Task 4: `agent_node`/`rag_node`를 스트리밍 호출로 전환 + 그래프 conftest에 큐 주입

**Files:**
- Modify: `app/chatbot/nodes.py`
- Modify: `tests/graph/conftest.py`

**Interfaces:**
- Consumes: `deps.llm.stream()` (Task 2/3), `config["configurable"]["stream_queue"]: asyncio.Queue[str]`
- Produces: `config["configurable"]["stream_queue"]`를 그래프 실행 중 노드가 델타를 넣는 통로로 확정 — Task 5의 `ChatbotService.chat()`이 이 큐를 만들어 config에 주입하고 소비한다.
- 이 태스크는 새 테스트 파일을 만들지 않는다. 대신 기존 그래프 테스트(`tests/graph/test_chatbot_graph.py`, `tests/graph/test_chatbot_limits.py`, `tests/integration/chatbot/test_privacy_regression.py`, `tests/integration/chatbot/test_safety_regression.py`)가 전부 `builder.config()`를 통해 `stream_queue`를 필요로 하므로, conftest 수정과 함께 그대로 회귀 테스트 역할을 한다.

- [ ] **Step 1: `tests/graph/conftest.py`에 `stream_queue`를 config에 추가**

`tests/graph/conftest.py` 상단에 `import asyncio` 추가(파일 최상단, `from datetime import date` 앞):

```python
import asyncio
from datetime import date
```

`_Builder.config()` 메서드(현재 90~103줄)를 다음으로 교체:

```python
    def config(self, *, actor: ActorContext | None = None, call_limit: int | None = None) -> dict:
        deps = ChatbotDeps(
            llm=self.llm,
            retriever=self.retriever,
            user_data=self.user_data,
            routine_service=self.routine_service,
            conversation_provider=self.conversation,
        )
        registry = ToolRegistry(
            user_data=self.user_data,
            context=ToolExecutionContext(actor=actor or member_actor()),
            call_limit=call_limit,
        )
        return {
            "configurable": {
                "deps": deps,
                "tool_registry": registry,
                "stream_queue": asyncio.Queue(),
            }
        }
```

- [ ] **Step 2: 현재 실패 확인(아직 노드가 큐를 요구하지 않으므로 실패하지 않음 — 통과 상태를 기준선으로 기록)**

Run: `pytest tests/graph tests/integration/chatbot/test_privacy_regression.py tests/integration/chatbot/test_safety_regression.py -v`
Expected: PASS (conftest만 바꿨고 노드는 아직 큐를 안 쓰므로 기존과 동일하게 전부 통과 — 이 스텝은 Step 4 이후 회귀를 비교할 기준선을 남기기 위한 것)

- [ ] **Step 3: `agent_node`/`rag_node`를 `stream()` 기반으로 수정**

`app/chatbot/nodes.py` 상단의 `import json` 줄 앞에 `import asyncio`를 추가(알파벳 순서상 asyncio가 먼저 온다):

```python
import asyncio
import json
```

`_tool_registry()` 함수(현재 55~56줄) 바로 뒤에 헬퍼 추가:

```python
def _stream_queue(config: RunnableConfig) -> asyncio.Queue:
    return config["configurable"]["stream_queue"]
```

`agent_node()`(현재 115~143줄)의 LLM 호출 부분을 다음으로 교체:

```python
async def agent_node(state: ChatState, config: RunnableConfig) -> dict:
    """개인 데이터 질문 처리. 한 번 실행이 LLM 호출 1회다. 도구 호출을 요청하면
    pending_tool_calls를 채워 반환하고, 그래프가 tool_node로 보냈다가 다시 이리로 되돌린다
    (이 재호출은 재시도가 아니라 정상적인 Function Calling 후속 턴이다).
    LLM 응답은 stream_queue로 델타를 흘려보내며 생성한다 — 도구 호출을 요청하는 중간 턴은
    보통 텍스트가 비어 있어 실질적으로 델타가 나가지 않는다."""
    call_count = state.get("llm_call_count", 0)
    if call_count >= get_settings().llm_call_limit:
        return {"error_code": "LLM_CALL_LIMIT_EXCEEDED", "pending_tool_calls": []}

    deps = _deps(config)
    queue = _stream_queue(config)
    llm_messages = state.get("llm_messages") or _build_initial_agent_messages(state)

    response = None
    async for chunk in deps.llm.stream(llm_messages):
        if chunk.delta:
            await queue.put(chunk.delta)
        if chunk.response is not None:
            response = chunk.response

    assistant_message = LLMMessage(
        role="assistant", content=response.text or "", tool_calls=response.tool_calls
    )
    updated_messages = [*llm_messages, assistant_message]

    if response.tool_calls:
        return {
            "llm_messages": updated_messages,
            "pending_tool_calls": response.tool_calls,
            "llm_call_count": call_count + 1,
        }
    return {
        "llm_messages": updated_messages,
        "pending_tool_calls": [],
        "answer": response.text or _FALLBACK_ANSWER,
        "llm_call_count": call_count + 1,
    }
```

`rag_node()`(현재 174~188줄)를 다음으로 교체:

```python
async def rag_node(state: ChatState, config: RunnableConfig) -> dict:
    """서비스/정책 질문. RAG 검색 결과를 근거로 LLM이 1회 호출로 답변을 만든다.
    답변 텍스트는 stream_queue로 델타를 흘려보내며 생성한다."""
    deps = _deps(config)
    queue = _stream_queue(config)
    documents = await deps.retriever.search(state["message"], category=None, keywords=[], top_k=3)
    prompt = build_rag_prompt(message=state["message"], documents=documents)

    response = None
    async for chunk in deps.llm.stream([LLMMessage(role="user", content=prompt)]):
        if chunk.delta:
            await queue.put(chunk.delta)
        if chunk.response is not None:
            response = chunk.response

    sources = [
        SourceReference(source=d.source, title=d.title, category=d.category) for d in documents
    ]
    return {
        "answer": response.text or _FALLBACK_ANSWER,
        "sources": sources,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
    }
```

- [ ] **Step 4: 회귀 테스트 통과 확인**

Run: `pytest tests/graph tests/integration/chatbot/test_privacy_regression.py tests/integration/chatbot/test_safety_regression.py -v`
Expected: PASS — `generate()`를 쓰던 것과 동일한 시나리오가 `stream()` 경로로도 그대로 통과해야 한다(응답 텍스트/tool_calls/에러 코드 결과는 동일).

- [ ] **Step 5: 커밋**

```bash
git add app/chatbot/nodes.py tests/graph/conftest.py
git commit -m "feat: agent_node/rag_node가 LLM 응답을 stream_queue로 흘려보내도록 전환"
```

---

## Task 5: `ChatbotService.chat()`을 SSE async generator로 전환

**Files:**
- Modify: `app/chatbot/service.py`
- Modify: `tests/unit/chatbot/test_service.py`

**Interfaces:**
- Consumes: `config["configurable"]["stream_queue"]` (Task 4), `app.chatbot.exceptions._ERROR_CODE_TO_EXCEPTION`(기존), `app.core.exceptions.AppError`, `app.llm.errors.LLMError`
- Produces: `ChatbotService.chat(request: ChatRequest) -> AsyncIterator[str]` — 각 문자열은 `event: <type>\ndata: <json>\n\n` 형식의 SSE 블록 하나. `<type>`은 `delta`(`{"text": str}`) / `done`(`ChatResponse.model_dump(mode="json")`) / `error`(`{"code", "message", "request_id", "retryable"}`) 중 하나. Task 6의 `router.py`가 그대로 `StreamingResponse(service.chat(request), ...)`에 넘긴다.

- [ ] **Step 1: 실패하는 테스트로 기존 `test_service.py` 전체 교체**

`tests/unit/chatbot/test_service.py`를 다음 내용으로 전체 교체(기존 파일은 `chat()`이 `ChatResponse`를 반환하거나 예외를 raise한다고 가정하므로, 새 SSE 계약에 맞춰 전면 재작성한다):

```python
"""ChatbotService.chat()의 SSE 스트리밍 계약 검증. delta/done/error 이벤트 포맷과
순서, 그리고 에러가 항상 error 이벤트로 통일되는지를 확인한다."""

import asyncio
import json

import pytest

from app.chatbot.graph import build_chatbot_graph
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.schemas import ChatRequest
from app.chatbot.service import ChatbotService
from app.common.models import ActorContext, PaymentHistory, Role
from app.llm.models import LLMResponse, ToolCall

from tests.graph.conftest import MEMBER_ID, _Builder, member_actor, sample_routine_result


def build_service(builder: _Builder) -> ChatbotService:
    deps = ChatbotDeps(
        llm=builder.llm,
        retriever=builder.retriever,
        user_data=builder.user_data,
        routine_service=builder.routine_service,
        conversation_provider=builder.conversation,
    )
    return ChatbotService(graph=build_chatbot_graph(), deps=deps)


def chat_request(**overrides) -> ChatRequest:
    payload = {"session_id": "session-1", "message": "환불 정책이 궁금해요", "actor": member_actor()}
    payload.update(overrides)
    return ChatRequest(**payload)


def _parse_sse(raw_events: list[str]) -> list[tuple[str, dict]]:
    parsed = []
    for raw in raw_events:
        lines = raw.strip("\n").split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        parsed.append((event, data))
    return parsed


async def _run(service: ChatbotService, request: ChatRequest) -> list[tuple[str, dict]]:
    raw_events = [event async for event in service.chat(request)]
    return _parse_sse(raw_events)


async def test_chat_returns_done_event_with_request_id_and_category() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    events = await _run(service, chat_request())

    done_events = [data for event, data in events if event == "done"]
    assert len(done_events) == 1
    done = done_events[0]
    assert done["answer"] == "환불은 7일 이내 가능합니다."
    assert done["category"] == "SERVICE_POLICY"
    assert done["request_id"]
    assert done["session_id"] == "session-1"


async def test_chat_streams_deltas_before_done_event() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    events = await _run(service, chat_request())

    assert events[-1][0] == "done"
    delta_texts = [data["text"] for event, data in events if event == "delta"]
    assert "".join(delta_texts) == "환불은 7일 이내 가능합니다."


async def test_chat_persists_via_conversation_provider() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    await _run(service, chat_request())

    assert len(builder.conversation.appended_messages) == 2  # user + assistant


async def test_chat_returns_routine_result_and_limited_flag() -> None:
    builder = _Builder()
    builder.llm.structured_response = sample_routine_result()
    service = build_service(builder)

    events = await _run(service, chat_request(message="루틴 추천해줘"))

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "ROUTINE"
    assert done["routine"] is not None
    assert done["limited"] is True
    assert set(done["routine"]["missing_data"]) == {"workout_diaries", "inbody"}


async def test_chat_emits_error_event_for_inactive_subscription() -> None:
    builder = _Builder()
    builder.user_data._subscriptions[MEMBER_ID].is_active = False
    service = build_service(builder)

    events = await _run(service, chat_request())

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "CHATBOT_SUBSCRIPTION_REQUIRED"
    assert data["retryable"] is False
    assert data["request_id"]


async def test_chat_emits_error_event_for_trainer_actor() -> None:
    builder = _Builder()
    service = build_service(builder)

    events = await _run(
        service, chat_request(actor=ActorContext(user_id=20, role=Role.TRAINER))
    )

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "ROLE_NOT_ALLOWED"


async def test_chat_uses_actor_fixed_id_for_function_calling() -> None:
    builder = _Builder()
    builder.user_data._payment_histories[MEMBER_ID] = [
        PaymentHistory(paid_at="2026-07-01T00:00:00", amount="10000", item_name="테스트")
    ]
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_payment_history", args={}, id="call-1")]),
        LLMResponse(text="결제 내역을 안내드립니다."),
    ]
    service = build_service(builder)

    events = await _run(service, chat_request(message="결제 내역 알려줘"))

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "PERSONAL"
    assert builder.user_data.calls[-1] == ("get_payment_history", MEMBER_ID)


async def test_chat_emits_timeout_error_event_when_graph_exceeds_budget(monkeypatch) -> None:
    builder = _Builder()
    service = build_service(builder)

    async def _hang(coro, *args, **kwargs):
        coro.close()  # 실제로 await하지 않아 생기는 ResourceWarning 방지
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", _hang)

    events = await _run(service, chat_request())

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "CHATBOT_REQUEST_TIMEOUT"


async def test_chat_emits_llm_call_limit_exceeded_error_event() -> None:
    builder = _Builder()
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_pt_usage", args={"n": i}, id=f"call-{i}")])
        for i in range(10)
    ]
    service = build_service(builder)

    events = await _run(service, chat_request(message="결제 내역 알려줘"))

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "LLM_CALL_LIMIT_EXCEEDED"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/unit/chatbot/test_service.py -v`
Expected: FAIL — `chat()`이 아직 async generator가 아니라 `TypeError: object ChatResponse can't be used in 'async for'` 류 오류 다수 발생

- [ ] **Step 3: `ChatbotService.chat()` 재작성**

`app/chatbot/service.py` 전체를 다음으로 교체:

```python
"""챗봇 대화 1턴을 실행하는 Use Case. 라우터는 이 서비스만 알고, LangGraph/LangChain/
Gemini는 몰라도 된다 — 그런 구현 세부사항은 전부 이 파일 아래(graph/nodes)에 있다.

chat()은 SSE 문자열을 흘려보내는 async generator다. 그래프 실행은 백그라운드 task로
돌리고, agent_node/rag_node가 stream_queue에 넣는 텍스트 델타를 즉시 delta 이벤트로
내보낸다. 에러는 access_guard 실패든 LLM 호출 한도 초과든 타임아웃이든 전부
error 이벤트로 통일한다 — 스트림은 이미 200으로 시작했으므로 HTTP status를
나중에 바꿀 수 없기 때문이다."""

import asyncio
import json
from typing import AsyncIterator

from app.chatbot.exceptions import ChatRequestTimeoutError, LLMCallLimitExceededError
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.schemas import ChatRequest, ChatResponse
from app.chatbot.state import ChatState
from app.chatbot.tools import ToolExecutionContext, ToolRegistry
from app.core.exceptions import AppError
from app.core.logging import get_request_id
from app.core.settings import get_settings
from app.llm.errors import LLMError
from app.routine.exceptions import ActorRoleNotAllowedError, SubscriptionRequiredError

_ERROR_CODE_TO_EXCEPTION = {
    "ROLE_NOT_ALLOWED": ActorRoleNotAllowedError,
    "CHATBOT_SUBSCRIPTION_REQUIRED": SubscriptionRequiredError,
    "LLM_CALL_LIMIT_EXCEEDED": LLMCallLimitExceededError,
}

_CATEGORY_BY_ROUTE = {
    "routine": "ROUTINE",
    "personal": "PERSONAL",
    "service_policy": "SERVICE_POLICY",
    "reject": "REJECT",
}

# error_handlers.py의 LLM 오류 재시도 가능 여부 매핑과 동일하게 유지한다.
_LLM_ERROR_RETRYABLE = {
    "LLM_NETWORK_ERROR": True,
    "LLM_RATE_LIMITED": True,
    "LLM_INVALID_RESPONSE": False,
}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error_payload(exc: Exception, request_id: str) -> dict:
    if isinstance(exc, AppError):
        return {"code": exc.code, "message": exc.message, "request_id": request_id, "retryable": exc.retryable}
    if isinstance(exc, LLMError):
        retryable = _LLM_ERROR_RETRYABLE.get(exc.code, False)
        message = (
            "AI 서버 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            if retryable
            else "요청을 처리하지 못했습니다. 다른 방식으로 다시 시도해 주세요."
        )
        return {"code": exc.code, "message": message, "request_id": request_id, "retryable": retryable}
    return {
        "code": "INTERNAL_ERROR",
        "message": "서버 내부 오류가 발생했습니다.",
        "request_id": request_id,
        "retryable": False,
    }


class _StreamDone:
    """그래프 실행이 끝났음을 큐로 알리는 신호. result가 있으면 정상 종료,
    error가 있으면 예외/타임아웃으로 종료된 것이다."""

    __slots__ = ("result", "error")

    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error


class ChatbotService:
    def __init__(self, *, graph, deps: ChatbotDeps) -> None:
        self._graph = graph
        self._deps = deps

    async def _run_graph_and_signal(self, initial_state: ChatState, config: dict, queue: asyncio.Queue) -> None:
        try:
            result = await asyncio.wait_for(
                self._graph.ainvoke(initial_state, config=config),
                timeout=get_settings().request_timeout_seconds,
            )
            await queue.put(_StreamDone(result=result))
        except asyncio.TimeoutError:
            await queue.put(_StreamDone(error=ChatRequestTimeoutError()))
        except Exception as e:  # 스트림을 안전하게 끝내기 위해 모든 예외를 error 이벤트로 변환한다.
            await queue.put(_StreamDone(error=e))

    async def chat(self, request: ChatRequest) -> AsyncIterator[str]:
        """요청 1건을 그래프로 실행하고 SSE 이벤트를 흘려보낸다."""
        request_id = get_request_id()

        summary = await self._deps.conversation_provider.load_summary(
            request.session_id, request.actor.user_id
        )
        recent_messages = await self._deps.conversation_provider.load_recent_messages(
            request.session_id, request.actor.user_id
        )
        contexts = await self._deps.conversation_provider.load_context(
            request.session_id, request.actor.user_id
        )

        initial_state = ChatState(
            request_id=request_id,
            session_id=request.session_id,
            actor=request.actor,
            message=request.message,
            intent_hint=request.intent_hint,
            summary=summary,
            recent_messages=recent_messages,
            contexts=contexts,
            llm_call_count=0,
            tool_call_count=0,
        )

        tool_registry = ToolRegistry(
            user_data=self._deps.user_data,
            context=ToolExecutionContext(actor=request.actor),
        )
        queue: asyncio.Queue = asyncio.Queue()
        config = {
            "configurable": {
                "deps": self._deps,
                "tool_registry": tool_registry,
                "stream_queue": queue,
            }
        }

        task = asyncio.create_task(self._run_graph_and_signal(initial_state, config, queue))
        done_signal: _StreamDone | None = None
        try:
            while done_signal is None:
                item = await queue.get()
                if isinstance(item, _StreamDone):
                    done_signal = item
                else:
                    yield _sse_event("delta", {"text": item})
        finally:
            if not task.done():
                task.cancel()

        if done_signal.error is not None:
            yield _sse_event("error", _error_payload(done_signal.error, request_id))
            return

        result = done_signal.result
        error_code = result.get("error_code")
        if error_code:
            exception_cls = _ERROR_CODE_TO_EXCEPTION.get(error_code)
            exc = exception_cls() if exception_cls else RuntimeError(f"매핑되지 않은 챗봇 오류 코드: {error_code}")
            yield _sse_event("error", _error_payload(exc, request_id))
            return

        route = result.get("route") or "personal"
        routine_result = result.get("routine_result")
        response = ChatResponse(
            request_id=request_id,
            session_id=request.session_id,
            answer=result.get("answer") or "",
            category=_CATEGORY_BY_ROUTE.get(route, route.upper()),
            routine=routine_result,
            sources=result.get("sources") or [],
            limited=bool(routine_result and routine_result.status == "LIMITED"),
        )
        yield _sse_event("done", response.model_dump(mode="json"))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/unit/chatbot/test_service.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: 커밋**

```bash
git add app/chatbot/service.py tests/unit/chatbot/test_service.py
git commit -m "feat: ChatbotService.chat()을 SSE 이벤트 스트림으로 전환"
```

---

## Task 6: 라우터를 `StreamingResponse`로 전환 + 통합 테스트 갱신

**Files:**
- Modify: `app/chatbot/router.py`
- Modify: `tests/integration/chatbot/test_chat_api.py`

**Interfaces:**
- Consumes: `ChatbotService.chat(request) -> AsyncIterator[str]` (Task 5)
- Produces: `POST /api/v1/chatbot/messages`가 `200 text/event-stream`으로 응답. 이 태스크가 이 계획의 마지막 배선 지점이다.

- [ ] **Step 1: 실패하는 테스트로 `test_chat_api.py` 전체 교체**

`tests/integration/chatbot/test_chat_api.py`를 다음 내용으로 전체 교체:

```python
"""회원 챗봇 API 계약 테스트. SSE(text/event-stream) 응답 헤더, done/error 이벤트
포맷, 인증/검증 오류(스트림 진입 전 실패)를 검증한다."""

import json

from httpx import ASGITransport, AsyncClient

from app.chatbot.dependencies import get_chatbot_service
from app.chatbot.schemas import ChatResponse
from main import app

_HEADERS = {"X-Internal-Api-Key": "local-development-only"}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


class FakeChatbotService:
    """라우터 배선(SSE 헤더, 이벤트 포맷)만 검증하면 되므로 delta 없이
    done 또는 error 이벤트 하나만 낸다."""

    def __init__(self, *, done: ChatResponse | None = None, error: dict | None = None) -> None:
        self.done = done
        self.error = error
        self.received_requests: list = []

    async def chat(self, request):
        self.received_requests.append(request)
        if self.error is not None:
            yield _sse_event("error", self.error)
            return
        yield _sse_event("done", self.done.model_dump(mode="json"))


def _payload(**overrides) -> dict:
    payload = {
        "session_id": "019f0000-0000-7000-8000-000000000001",
        "message": "환불 정책이 궁금해요",
        "intent_hint": None,
        "actor": {"user_id": 10, "role": "USER"},
    }
    payload.update(overrides)
    return payload


async def test_chat_message_streams_done_event_with_common_response_contract() -> None:
    fake = FakeChatbotService(
        done=ChatResponse(
            request_id="req-1", session_id="019f0000-0000-7000-8000-000000000001",
            answer="환불은 7일 이내 가능합니다.", category="SERVICE_POLICY",
            routine=None, sources=[], limited=False,
        )
    )
    app.dependency_overrides[get_chatbot_service] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chatbot/messages", headers=_HEADERS, json=_payload()
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert events == [
        (
            "done",
            {
                "request_id": "req-1",
                "session_id": "019f0000-0000-7000-8000-000000000001",
                "answer": "환불은 7일 이내 가능합니다.",
                "category": "SERVICE_POLICY",
                "routine": None,
                "sources": [],
                "limited": False,
            },
        )
    ]
    assert len(fake.received_requests) == 1


async def test_chat_message_requires_internal_api_key() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/chatbot/messages", json=_payload())

    assert response.status_code == 401
    assert response.json()["code"] == "INTERNAL_AUTH_FAILED"


async def test_chat_message_rejects_blank_message() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chatbot/messages", headers=_HEADERS, json=_payload(message="")
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"


async def test_chat_message_streams_error_event_for_service_error_code() -> None:
    fake = FakeChatbotService(
        error={
            "code": "CHATBOT_SUBSCRIPTION_REQUIRED",
            "message": "활성 구독이 있어야 루틴 추천을 이용할 수 있습니다.",
            "request_id": "req-1",
            "retryable": False,
        }
    )
    app.dependency_overrides[get_chatbot_service] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chatbot/messages", headers=_HEADERS, json=_payload()
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200  # 스트림은 항상 200으로 시작하고, 에러는 이벤트로 전달된다.
    events = _parse_sse(response.text)
    assert events == [
        (
            "error",
            {
                "code": "CHATBOT_SUBSCRIPTION_REQUIRED",
                "message": "활성 구독이 있어야 루틴 추천을 이용할 수 있습니다.",
                "request_id": "req-1",
                "retryable": False,
            },
        )
    ]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/integration/chatbot/test_chat_api.py -v`
Expected: FAIL — 라우터가 아직 `ChatResponse` JSON을 반환하므로 `response.headers["content-type"]`가 `application/json`이라 첫 테스트 실패, `FakeChatbotService.chat()`이 async generator라 기존 라우터 코드(`return await service.chat(request)`)와 타입이 맞지 않아 다른 테스트들도 실패

- [ ] **Step 3: `app/chatbot/router.py`를 `StreamingResponse`로 교체**

`app/chatbot/router.py` 전체를 다음으로 교체:

```python
"""회원 챗봇 API. LangGraph/LangChain/Gemini를 직접 import하지 않는다 —
요청 변환과 ChatbotService 호출만 담당한다."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.chatbot.dependencies import get_chatbot_service
from app.chatbot.schemas import ChatRequest
from app.chatbot.service import ChatbotService
from app.common.auth import verify_internal_api_key

router = APIRouter(
    prefix="/api/v1/chatbot",
    tags=["chatbot"],
    dependencies=[Depends(verify_internal_api_key)],
)


@router.post("/messages")
async def send_message(
    request: ChatRequest,
    service: ChatbotService = Depends(get_chatbot_service),
) -> StreamingResponse:
    """회원 챗봇 대화 1턴. SSE(text/event-stream)로 델타를 흘려보내고
    마지막에 done 또는 error 이벤트로 마무리한다."""
    return StreamingResponse(service.chat(request), media_type="text/event-stream")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/integration/chatbot/test_chat_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add app/chatbot/router.py tests/integration/chatbot/test_chat_api.py
git commit -m "feat: 챗봇 라우터를 StreamingResponse(SSE)로 전환"
```

---

## Task 7: 전체 회귀 테스트

**Files:**
- 없음 (테스트 실행만)

**Interfaces:**
- Consumes: Task 1~6에서 만든 모든 코드
- Produces: 없음 — 최종 확인 단계

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run: `pytest -v`
Expected: PASS — 기존 테스트(diet, routine, trainer_report 등 챗봇과 무관한 도메인 포함) 전부와 이번에 수정한 챗봇/LLM 테스트가 모두 통과해야 한다.

- [ ] **Step 2: 실패가 있으면 원인별로 수정**

`generate()` → `stream()` 전환 과정에서 놓친 호출부(예: 다른 도메인이 `ChatbotDeps.llm.generate()`를 직접 참조하는 곳이 있는지)가 있으면 이 스텝에서 잡는다. 수정 후 Step 1을 다시 실행해 전체 통과를 확인한다.

- [ ] **Step 3: 최종 커밋(수정이 있었던 경우에만)**

```bash
git add -A
git commit -m "fix: 챗봇 SSE 스트리밍 전환 후 회귀 테스트 수정"
```

## 확인이 필요한 사항 (스펙에서 이월)

- Spring 팀이 SSE(`text/event-stream`) 응답을 소비할 준비가 되어 있는지, 에러를 HTTP status 대신 이벤트 body의 `code` 필드로 분기하는 방식에 동의하는지는 이 구현 계획의 범위 밖이며 별도로 전달해야 한다.
- Gemini function calling 중간 턴에서 텍스트 콘텐츠가 실제로 비어 있는지(델타 유출 없음 가정)는 실제 Gemini API 스트리밍 응답으로 별도 검증이 필요하다(`tests/smoke/test_gemini_smoke.py`류 스모크 테스트에 케이스 추가를 고려할 것).
