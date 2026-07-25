# 챗봇 SSE delta 어절 단위 분할 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ChatbotService.chat()`이 SSE `delta` 이벤트를 어절(단어) 단위로 잘게 쪼개 보내도록 바꿔, 프론트엔드가 타이핑 효과를 자연스럽게 적용할 수 있게 한다.

**Architecture:** LangGraph 노드들은 지금처럼 텍스트를 `stream_queue`에 넣기만 하고, 분할 granularity는 전적으로 소비 측인 `ChatbotService.chat()`의 큐 소비 루프가 책임진다. 큐에서 꺼낸 텍스트를 요청 범위 누적 버퍼에 이어붙인 뒤, 공백으로 끝나는 완성된 어절만 즉시 delta로 내보내고 미완성 조각은 다음 청크와 이어붙이기 위해 보류한다. 스트림 종료 시 남은 버퍼를 flush한다.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pytest (`asyncio_mode = auto`), 표준 라이브러리 `re`

**설계 문서:** [docs/superpowers/specs/2026-07-25-chatbot-delta-word-chunking-design.md](../specs/2026-07-25-chatbot-delta-word-chunking-design.md)

## Global Constraints

- 모든 주석·docstring·커밋 메시지는 한국어로 작성한다 (기존 `app/chatbot` 코드 스타일과 동일).
- **git 커밋/푸쉬/머지는 사용자가 직접 수행한다.** 각 Task의 마지막 "커밋" 스텝은 실행하지 말고, 변경 파일 목록과 제안 커밋 메시지를 사용자에게 안내한 뒤 사용자가 직접 실행하게 한다. `git status`/`git diff` 등 조회성 명령은 사용 가능.
- **테스트 실행 전 반드시 venv를 활성화한다.** 터미널이 전역 conda 환경(`pystudy_env`)으로 기본 활성화되어 있어, 활성화하지 않으면 `async def functions are not natively supported` 에러가 난다:
  ```
  .venv\Scripts\Activate.ps1
  ```
- 변경 범위를 최소화한다. `app/chatbot/nodes.py`, `app/llm/*`, `app/chatbot/router.py`, `app/chatbot/schemas.py`는 이번 작업에서 수정하지 않는다.
- SSE 이벤트 스키마(`delta` = `{"text": str}`, `done`, `error`)는 변경하지 않는다. 빈도만 바뀐다.
- **손실 없음 불변식:** 전송된 모든 delta의 `text`를 순서대로 이어붙이면 항상 원본 답변 텍스트와 정확히 같아야 한다(공백 포함). 기존 테스트 `test_chat_streams_deltas_before_done_event`가 이 계약을 검증한다.

---

### Task 1: `_split_ready_words` 어절 분할 헬퍼

큐에서 받은 누적 버퍼를 어절 단위로 쪼개는 순수 함수를 먼저 만든다. 순수 함수라 그래프·비동기 없이 단독으로 검증할 수 있고, Task 2는 이 함수를 배선하기만 하면 된다.

**Files:**
- Modify: `app/chatbot/service.py` (상단 import 및 모듈 레벨 함수 추가)
- Test: `tests/unit/chatbot/test_service.py`

**Interfaces:**
- Consumes: 없음 (표준 라이브러리 `re`만 사용)
- Produces: `_split_ready_words(buffer: str) -> tuple[list[str], str]` — `(즉시 내보낼 어절 목록, 남길 버퍼)`를 반환한다. 반환된 어절들과 남은 버퍼를 이어붙이면 항상 입력 `buffer`와 정확히 같다. 각 어절 문자열은 뒤따르는 공백까지 포함한다(예: `"안녕하세요 "`). Task 2가 이 함수를 `chat()`에서 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/chatbot/test_service.py`의 import 구문에 `_split_ready_words`를 추가한다. 기존 import 줄:

```python
from app.chatbot.service import ChatbotService
```

를 다음으로 바꾼다:

```python
from app.chatbot.service import ChatbotService, _split_ready_words
```

그리고 파일 맨 끝에 다음 테스트 4개를 추가한다:

```python
def test_split_ready_words_holds_incomplete_last_word() -> None:
    """마지막 조각이 공백으로 끝나지 않으면 다음 청크와 이어질 수 있으므로 보류한다."""
    words, pending = _split_ready_words("안녕하세요 오늘은")

    assert words == ["안녕하세요 "]
    assert pending == "오늘은"


def test_split_ready_words_emits_all_when_buffer_ends_with_whitespace() -> None:
    """버퍼가 공백으로 끝나면 모든 어절이 완성된 것이므로 전부 내보낸다."""
    words, pending = _split_ready_words("안녕 반가워 ")

    assert words == ["안녕 ", "반가워 "]
    assert pending == ""


def test_split_ready_words_rejoins_word_split_across_chunks() -> None:
    """Gemini 청크는 어절 중간에서 끊길 수 있다. 버퍼를 이어붙이면
    원래 어절 경계에서만 delta가 나가야 한다."""
    words, pending = _split_ready_words("오늘은 운동")
    assert words == ["오늘은 "]
    assert pending == "운동"

    words, pending = _split_ready_words(pending + "을 하고")
    assert words == ["운동을 "]
    assert pending == "하고"


def test_split_ready_words_never_drops_characters() -> None:
    """어절 목록과 남은 버퍼를 합치면 항상 원본과 같아야 한다(선행 공백·개행 포함)."""
    for buffer in ["", "   ", "  안녕", "첫 줄\n둘째 줄", "끝에 공백 두 개  "]:
        words, pending = _split_ready_words(buffer)
        assert "".join(words) + pending == buffer
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv\Scripts\Activate.ps1; pytest tests/unit/chatbot/test_service.py -v -k split_ready_words
```

Expected: 4개 테스트 모두 collection 단계에서 `ImportError: cannot import name '_split_ready_words' from 'app.chatbot.service'`로 실패.

- [ ] **Step 3: 최소 구현 작성**

`app/chatbot/service.py` 상단의 import 블록에 `re`를 추가한다. 현재:

```python
import asyncio
import json
import logging
from typing import AsyncIterator
```

를 다음으로 바꾼다:

```python
import asyncio
import json
import logging
import re
from typing import AsyncIterator
```

그리고 `_LLM_ERROR_RETRYABLE` 딕셔너리 정의 바로 아래, `_sse_event` 함수 정의 위에 다음을 추가한다:

```python
# 선행 공백까지 포함해 매칭해야 어절 사이 공백이 유실되지 않는다.
_WORD_PATTERN = re.compile(r"\s*\S+\s*")


def _split_ready_words(buffer: str) -> tuple[list[str], str]:
    """누적 버퍼를 어절 단위로 쪼개 (즉시 내보낼 어절, 남길 버퍼)를 반환한다.

    LLM 스트리밍 청크는 어절 중간에서 끊길 수 있으므로(예: "운동" + "을 하고"),
    공백으로 끝나지 않는 마지막 조각은 미완성 어절로 보고 다음 청크와 이어붙이도록
    남긴다. 반환값을 이어붙이면 항상 입력 buffer와 정확히 같다 — delta를 전부
    합치면 원본 답변이 되어야 하는 계약을 이 함수가 지킨다."""
    words = [m.group() for m in _WORD_PATTERN.finditer(buffer)]
    if not words:
        return [], buffer
    if not words[-1][-1].isspace():
        return words[:-1], words[-1]
    return words, ""
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv\Scripts\Activate.ps1; pytest tests/unit/chatbot/test_service.py -v -k split_ready_words
```

Expected: 4 passed.

- [ ] **Step 5: 커밋 (사용자가 직접 실행)**

실행하지 말고, 아래 내용을 사용자에게 안내한다.

변경 파일: `app/chatbot/service.py`, `tests/unit/chatbot/test_service.py`

제안 커밋 메시지:

```
feat: SSE delta 어절 분할 헬퍼 _split_ready_words 추가

LLM 청크가 어절 중간에서 끊겨도 올바른 어절 경계에서만 분할되도록
누적 버퍼 기반 순수 함수를 추가한다. 배선은 다음 커밋에서 한다.
```

---

### Task 2: `chat()` 루프에 어절 분할 배선 + 문서 갱신

Task 1의 헬퍼를 실제 SSE 스트림에 연결한다. 기존 테스트 2개가 "완성된 답변은 delta 1개로 나간다"고 단언하고 있어 함께 갱신하고, 같은 내용을 명시한 아키텍처 문서도 이 Task에서 함께 고친다 — 코드와 문서가 어긋난 상태로 커밋되지 않게 하기 위해서다.

**Files:**
- Modify: `app/chatbot/service.py:199-214` (`chat()`의 큐 소비 루프)
- Modify: `tests/unit/chatbot/test_service.py` (기존 테스트 2개 갱신)
- Modify: `.docs/ARCHITECTURE.md:426-427` ("📡 SSE 스트리밍 응답" 절)

**Interfaces:**
- Consumes: Task 1의 `_split_ready_words(buffer: str) -> tuple[list[str], str]`
- Produces: 없음 (외부 계약 변경 없음 — `delta` 이벤트 스키마 `{"text": str}` 그대로)

- [ ] **Step 1: 기존 테스트를 새 동작에 맞게 갱신**

`tests/unit/chatbot/test_service.py`에서 아래 두 테스트를 찾아 통째로 교체한다.

교체 전 (현재 파일에 있는 내용):

```python
async def test_chat_emits_single_delta_before_done_for_reject_route() -> None:
    """reject_node는 LLM을 호출하지 않지만, 프론트 경험 일관성을 위해 거절 메시지를
    delta 이벤트로 한 번은 흘려보낸 뒤 done 이벤트를 내보내야 한다."""
    builder = _Builder()
    service = build_service(builder)

    events = await _run(service, chat_request(message="주식 추천해줘"))

    assert events[-1][0] == "done"
    delta_events = [data for event, data in events if event == "delta"]
    assert len(delta_events) == 1
    assert delta_events[0]["text"] == REJECT_MESSAGE
```

교체 후:

```python
async def test_chat_streams_reject_message_as_word_deltas() -> None:
    """reject_node는 LLM을 호출하지 않고 완성된 문구를 큐에 한 번에 넣지만,
    서비스가 어절 단위로 쪼개 여러 delta로 흘려보낸 뒤 done을 내보내야 한다."""
    builder = _Builder()
    service = build_service(builder)

    events = await _run(service, chat_request(message="주식 추천해줘"))

    assert events[-1][0] == "done"
    delta_texts = [data["text"] for event, data in events if event == "delta"]
    assert len(delta_texts) > 1
    assert "".join(delta_texts) == REJECT_MESSAGE
```

이어서 그 아래 테스트도 교체한다.

교체 전:

```python
async def test_chat_emits_single_delta_before_done_for_routine_route() -> None:
    """routine_node도 LLM 스트리밍 없이 구조화 출력만 만들지만, 완성된 요약을
    delta 이벤트로 한 번은 흘려보낸 뒤 done 이벤트를 내보내야 한다."""
    builder = _Builder()
    builder.llm.structured_response = sample_routine_result()
```

교체 후 (함수 이름과 docstring만 바꾸고 셋업 두 줄은 그대로 유지):

```python
async def test_chat_streams_routine_answer_as_word_deltas() -> None:
    """routine_node도 LLM 스트리밍 없이 구조화 출력만 만들지만, 완성된 답변을
    어절 단위 delta로 흘려보낸 뒤 done 이벤트를 내보내야 한다."""
    builder = _Builder()
    builder.llm.structured_response = sample_routine_result()
```

같은 테스트 함수의 단언 부분도 교체한다.

교체 전:

```python
    assert events[-1][0] == "done"
    delta_events = [data for event, data in events if event == "delta"]
    assert len(delta_events) == 1

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "ROUTINE"
    assert delta_events[0]["text"] == done["answer"]
    assert done["quick_replies"][0]["question_id"] == "ROUTINE_GOAL"
```

교체 후:

```python
    assert events[-1][0] == "done"
    delta_texts = [data["text"] for event, data in events if event == "delta"]
    assert len(delta_texts) > 1

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "ROUTINE"
    assert "".join(delta_texts) == done["answer"]
    assert done["quick_replies"][0]["question_id"] == "ROUTINE_GOAL"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv\Scripts\Activate.ps1; pytest tests/unit/chatbot/test_service.py -v -k "word_deltas"
```

Expected: 2개 모두 FAIL. `assert len(delta_texts) > 1`에서 `assert 1 > 1`로 실패한다 — 아직 서비스가 큐 아이템을 1:1로 내보내기 때문이다.

- [ ] **Step 3: `chat()` 큐 소비 루프 구현**

`app/chatbot/service.py`에서 아래 블록을 찾아 교체한다.

교체 전:

```python
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
```

교체 후:

```python
            task = asyncio.create_task(self._run_graph_and_signal(initial_state, config, queue))
            done_signal: _StreamDone | None = None
            # 노드는 LLM 청크나 완성된 문구를 그대로 큐에 넣는다. 프론트가 타이핑 효과를
            # 적용할 수 있도록 잘게 쪼개는 책임은 여기(소비 측)에만 둔다.
            pending_text = ""
            try:
                while done_signal is None:
                    item = await queue.get()
                    if isinstance(item, _StreamDone):
                        done_signal = item
                    else:
                        ready_words, pending_text = _split_ready_words(pending_text + item)
                        for word in ready_words:
                            yield _sse_event("delta", {"text": word})
                # 마지막 어절은 뒤에 공백이 없어 보류되어 있으므로 반드시 flush한다.
                # 에러로 끝난 경우에도 이미 생성된 텍스트는 그대로 내보낸다.
                if pending_text:
                    yield _sse_event("delta", {"text": pending_text})
            finally:
                if not task.done():
                    task.cancel()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv\Scripts\Activate.ps1; pytest tests/unit/chatbot/test_service.py -v
```

Expected: 전체 통과. 특히 `test_chat_streams_deltas_before_done_event`(`"".join(delta_texts) == "환불은 7일 이내 가능합니다."`)가 계속 통과해야 한다 — 손실 없음 불변식이 지켜졌다는 뜻이다.

- [ ] **Step 5: 챗봇 전체 회귀 테스트**

```bash
.venv\Scripts\Activate.ps1; pytest tests/unit/chatbot tests/integration/chatbot tests/graph -v
```

Expected: 전부 통과. 실패가 있으면 delta 개수를 하드코딩한 다른 테스트가 있다는 뜻이므로, 해당 테스트도 "합치면 원문과 같다" 방식으로 갱신한다.

- [ ] **Step 6: 아키텍처 문서 갱신**

`.docs/ARCHITECTURE.md`의 "📡 SSE 스트리밍 응답" 절에서 아래 두 줄을 찾아 교체한다.

교체 전:

```markdown
- `agent_node`(개인 이용정보)와 `rag_node`(정책 RAG)는 Gemini 텍스트를 `LLMPort.stream()`으로 호출해 실제 토큰 단위 델타를 큐에 흘려보낸다.
- `routine_node`(루틴 추천)와 `reject_node`(정중한 거절)는 Gemini 구조화 출력 또는 고정 문구라 토큰 스트리밍이 불가능하므로, 완성된 답변을 **단일 delta**로 한 번 흘려보낸 뒤 곧바로 `done`으로 마무리한다 — 모든 라우트가 "delta 최소 1개 이상 → done" 순서를 지키도록 통일했다.
```

교체 후:

```markdown
- `agent_node`(개인 이용정보)와 `rag_node`(정책 RAG)는 Gemini 텍스트를 `LLMPort.stream()`으로 호출해 받은 청크를 그대로 큐에 흘려보낸다.
- `routine_node`(루틴 추천)와 `reject_node`(정중한 거절)는 Gemini 구조화 출력 또는 고정 문구라 토큰 스트리밍이 불가능하므로, 완성된 답변을 통째로 큐에 한 번 넣는다.
- **어절 단위 재분할(2026-07-25):** 노드가 큐에 넣는 조각의 크기는 라우트마다 제각각이므로, `ChatbotService.chat()`이 큐에서 꺼낸 텍스트를 누적 버퍼에 모았다가 **어절(공백) 단위로 쪼개** delta로 내보낸다(`_split_ready_words`). Gemini 청크가 어절 중간에서 끊겨도(예: `"운동"` + `"을 하고"`) 버퍼가 이어 붙여 주므로 항상 올바른 어절 경계에서만 delta가 나간다. 프론트엔드가 타이핑 효과를 적용하기 쉽도록 한 요청에 따른 변경이며, 모든 라우트가 "delta 최소 1개 이상 → done" 순서를 지키는 점은 동일하다. 전송된 delta들의 `text`를 순서대로 이어붙이면 항상 `done.answer`와 정확히 같다.
```

같은 파일 맨 아래 변경 이력 표에 다음 행을 추가한다:

```markdown
| 2026-07-25 | 프론트 요청(delta가 너무 큼)에 따라 `ChatbotService.chat()`이 delta를 어절 단위로 재분할하도록 변경. "📡 SSE 스트리밍 응답" 절의 노드별 delta 설명을 갱신 |
```

- [ ] **Step 7: 전체 회귀 테스트**

```bash
.venv\Scripts\Activate.ps1; pytest
```

Expected: 기존 baseline(170 passed, 6 skipped)에서 신규 테스트 4개가 늘어 174 passed, 6 skipped. 실패 0건.

- [ ] **Step 8: 커밋 (사용자가 직접 실행)**

실행하지 말고, 아래 내용을 사용자에게 안내한다.

변경 파일: `app/chatbot/service.py`, `tests/unit/chatbot/test_service.py`, `.docs/ARCHITECTURE.md`

제안 커밋 메시지:

```
feat: SSE delta를 어절 단위로 쪼개 전송

프론트에서 delta 한 건이 너무 커서 타이핑 효과를 적용하기 어렵다는
요청에 따라, chat() 큐 소비 루프가 텍스트를 어절 단위로 재분할한다.
노드는 그대로 두고 소비 측만 바꿔 라우트별 분기를 만들지 않았다.
```

---

## 검증 요약

구현 완료 후 다음을 확인한다:

- `pytest` 전체 통과 (174 passed, 6 skipped 예상)
- delta 텍스트를 전부 이어붙이면 `done.answer`와 정확히 일치 (기존 테스트 2개 + 신규 테스트가 검증)
- `app/chatbot/nodes.py`, `app/llm/` 하위 파일에 변경 없음 — `git status`로 확인
