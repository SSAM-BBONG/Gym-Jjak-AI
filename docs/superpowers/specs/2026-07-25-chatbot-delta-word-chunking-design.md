# 챗봇 SSE delta 어절 단위 분할 설계

- 날짜: 2026-07-25
- 대상: `app/chatbot/service.py` (`ChatbotService.chat()`)
- 작성 배경: 프론트엔드에서 "delta 텍스트가 한 번에 너무 크게(약 2문장씩) 온다, 스트리밍 타이핑 효과를 적용하기 어려우니 더 짧게 여러 번 보내달라"는 요청을 받음. 실제 원인은 인위적인 버퍼링 코드가 아니라, `langchain-google-genai`의 `astream()`이 원래 문장 단위에 가까운 청크를 주고, `agent_node`/`rag_node`가 그 청크를 그대로 큐에 넣으며, `greeting_node`/`reject_node`/`routine_node`는 완성된 답변 전체를 단일 delta로 큐에 넣기 때문(`app/chatbot/nodes.py`). `chat()`의 큐 소비 루프도 큐에서 꺼낸 조각을 가공 없이 1:1로 SSE delta 이벤트로 전달하고 있었다([2026-07-22 스트리밍 설계](2026-07-22-chatbot-streaming-design.md) 참고).

## 범위

- **포함**: `ChatbotService.chat()`의 큐 소비 루프에 어절(단어) 단위 분할 로직 추가. 큐에서 받은 텍스트를 누적 버퍼에 이어붙이고, 공백/개행으로 끝나는 완성된 어절만 즉시 delta로 전송한다.
- **제외**: 노드(`agent_node`, `rag_node`, `greeting_node`, `reject_node`, `routine_node`) 자체 수정. 노드는 지금처럼 텍스트를 큐에 넣기만 하면 되며, 분할 granularity는 전적으로 소비 측(`chat()`) 책임으로 둔다. LLM 어댑터(`gemini_adapter.py`) 스트리밍 방식도 변경하지 않는다.
- 문자 수 기준 분할, 문장부호 기준 분할, 설정 가능한 청크 크기(설정값) 등은 검토했으나 채택하지 않음 — 사용자가 어절 단위 고정 방식을 요청함.

## 전체 아키텍처

```
ChatbotService.chat()
  큐 소비 루프:
    item = await queue.get()
    - _StreamDone이면: 루프 종료 → 남은 버퍼 flush → 기존 error/done 처리로 진행
    - 문자열이면:
        pending_text += item
        ready_words, pending_text = _split_ready_words(pending_text)
        ready_words 각각을 delta 이벤트로 yield
  (task 완료 후 error/done 이벤트 처리는 기존과 동일, 변경 없음)
```

노드 5곳, `LLMPort`/`gemini_adapter.py`, SSE 이벤트 포맷(`delta`/`done`/`error`)은 모두 기존과 동일하다. 오직 `delta` 이벤트가 나가는 **빈도와 텍스트 조각의 크기**만 바뀐다.

## 분할 알고리즘

```python
_WORD_PATTERN = re.compile(r"\S+\s*")

def _split_ready_words(buffer: str) -> tuple[list[str], str]:
    """buffer를 어절(공백/개행 포함) 단위로 쪼갠다. 마지막 조각이 공백으로
    끝나지 않으면 다음 청크와 이어질 수 있는 미완성 어절이므로 보류한다."""
    matches = list(_WORD_PATTERN.finditer(buffer))
    if not matches:
        return [], buffer
    if not matches[-1].group().endswith((" ", "\n", "\t")):
        return [m.group() for m in matches[:-1]], matches[-1].group()
    return [m.group() for m in matches], ""
```

`pending_text`는 `chat()` 호출(요청) 범위의 지역 변수로 유지한다 — 요청 간 공유되지 않는다.

### 왜 버퍼링이 필요한가 (청크 경계 문제)

Gemini 스트리밍 청크는 어절 중간에서 끊길 수 있다(예: `"운동"` + `"을 하고"` 두 청크로 나뉨). 각 청크를 독립적으로 공백 분할하면 `"운동"`이 완성된 어절처럼 잘못 전송된다. 버퍼에 이어붙이고 실제 공백이 나타날 때까지 마지막 조각을 보류하면, 원래 어절 경계가 여러 청크에 걸쳐 있어도 항상 올바른 지점에서만 delta가 나간다.

## 마무리 처리 (flush)

`_StreamDone` 신호를 받아 루프를 빠져나가기 직전, `pending_text`에 남은 텍스트가 있으면 마지막 delta로 한 번 더 flush한다:

```python
if pending_text:
    yield _sse_event("delta", {"text": pending_text})
```

`greeting_node`/`reject_node`처럼 완성된 문자열 전체가 한 번에 큐에 들어오는 경우도 동일 경로를 타므로, 앞부분 어절들은 이미 개별 delta로 나가고 마지막 어절(공백 없이 끝나는 경우가 일반적)만 flush 시점에 나간다.

## 영향 범위

- 변경 파일: `app/chatbot/service.py` 1개만 수정 (정규식 상수 + `_split_ready_words` 헬퍼 + `chat()` 루프 수정).
- 노드(`nodes.py`), LLM 포트/어댑터, 라우터, 스키마, SSE 이벤트 포맷 문서(`docs/API.md` 등)는 변경 없음 — delta 이벤트 스키마(`{"text": str}`)는 그대로 유지되고 빈도만 바뀐다.

## 테스트 영향

- 기존 `tests/unit/chatbot/test_service.py` 중 아래 2개가 현재 가정("완성된 답변은 delta 1개로만 나간다")과 충돌하여 갱신이 필요하다:
  - `test_chat_emits_single_delta_before_done_for_reject_route`
  - `test_chat_emits_single_delta_before_done_for_routine_route`
  - 갱신 방향: `len(delta_events) == 1` 단언을 제거하고, `"".join(text) == 원문 메시지` 방식으로 재작성한다(어절 개수는 메시지 내용에 따라 달라지므로 정확한 개수를 하드코딩하지 않는다).
- `test_chat_streams_deltas_before_done_event`는 이미 `"".join(delta_texts) == 전체 텍스트` 방식이라 수정 없이 통과한다.
- 새 테스트: 어절 경계가 두 개의 큐 아이템(Gemini 청크)에 걸쳐 나뉘는 경우(`"운동"` + `"을 하고"` 같은 패턴)에도 올바른 어절로 재조합되어 나가는지 검증하는 케이스를 추가한다.
