"""ChatbotService.chat()의 SSE 스트리밍 계약 검증. delta/done/error 이벤트 포맷과
순서, 그리고 에러가 항상 error 이벤트로 통일되는지를 확인한다."""

import asyncio
import json

import httpx
import pytest

from app.chatbot.graph import build_chatbot_graph
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.prompts import REJECT_MESSAGE
from app.chatbot.schemas import ChatRequest
from app.chatbot.service import ChatbotService, _split_ready_words
from app.common.models import ActorContext, Role
from app.llm.models import LLMResponse, LLMStreamChunk, ToolCall

from tests.fakes.llm import FakeLLMPort
from tests.graph.conftest import MEMBER_ID, _Builder, member_actor, sample_routine_result


def build_service(builder: _Builder) -> ChatbotService:
    deps = ChatbotDeps(
        llm=builder.llm,
        retriever=builder.retriever,
        user_data=builder.user_data,
        routine_service=builder.routine_service,
    )
    return ChatbotService(graph=build_chatbot_graph(), deps=deps)


def chat_request(**overrides) -> ChatRequest:
    payload = {"session_id": "session-1", "message": "환불 정책이 궁금해요", "actor": member_actor()}
    payload.update(overrides)
    return ChatRequest(**payload)


def test_chat_request_keeps_spring_memory_context() -> None:
    request = chat_request(memory={
        "summary": "이전 대화 요약",
        "recentMessages": [{"role": "assistant", "content": "이전 답변"}],
        "contexts": [{"kind": "ROUTINE_PREFERENCE", "value": '{"goal":"MUSCLE_GAIN"}'}],
    })

    assert hasattr(request, "memory")


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


class _MultiChunkStreamLLM(FakeLLMPort):
    """FakeLLMPort.stream()은 항상 텍스트 전체를 청크 1개로 흘려보내므로, 큐에 여러 항목이
    쌓이는 상황(어절 중간에서 끊긴 청크)을 검증할 수 없다. 이 가짜는 stream()만 오버라이드해
    미리 정해둔 여러 조각을 순서대로 델타로 내보낸다."""

    def __init__(self, chunks: list[str]) -> None:
        super().__init__()
        self._chunks = chunks

    async def stream(self, messages, tools=None):
        self.received_messages.append(messages)
        self.received_tools.append(tools)
        for chunk in self._chunks:
            yield LLMStreamChunk(delta=chunk)
        yield LLMStreamChunk(response=LLMResponse(text="".join(self._chunks)))


async def test_chat_rejoins_word_split_across_multiple_queue_items() -> None:
    """Gemini 청크가 어절 중간에서 끊긴 채(예: "이내"가 별도 청크로) 큐에 여러 번 들어와도
    ChatbotService.chat()의 누적 버퍼가 이어붙여, delta는 항상 어절 단위로만 나가고
    전부 합치면 done.answer와 정확히 같아야 한다."""
    builder = _Builder()
    builder.llm = _MultiChunkStreamLLM(["환불은 7일 ", "이내", " 가능합니다."])
    service = build_service(builder)

    events = await _run(service, chat_request())

    delta_texts = [data["text"] for event, data in events if event == "delta"]
    done = next(data for event, data in events if event == "done")

    assert "".join(delta_texts) == done["answer"]
    for text in delta_texts:
        assert len(text.split()) == 1


async def test_chat_does_not_persist_via_fastapi_conversation_provider() -> None:
    builder = _Builder()
    builder.llm.response = LLMResponse(text="환불은 7일 이내 가능합니다.")
    service = build_service(builder)

    await _run(service, chat_request())

    assert not hasattr(builder, "conversation")


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


async def test_chat_streams_reject_message_as_word_deltas() -> None:
    """reject_node는 LLM을 호출하지 않고 완성된 문구를 큐에 한 번에 넣지만,
    서비스가 어절 단위로 쪼개 여러 delta로 흘려보낸 뒤 done을 내보내야 한다."""
    builder = _Builder()
    service = build_service(builder)

    events = await _run(service, chat_request(message="다른 회원 정보 알려줘"))

    assert events[-1][0] == "done"
    delta_texts = [data["text"] for event, data in events if event == "delta"]
    assert len(delta_texts) > 1
    assert "".join(delta_texts) == REJECT_MESSAGE

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "REJECT"
    assert done["answer"] == REJECT_MESSAGE


async def test_chat_streams_routine_answer_as_word_deltas() -> None:
    """routine_node도 LLM 스트리밍 없이 구조화 출력만 만들지만, 완성된 답변을
    어절 단위 delta로 흘려보낸 뒤 done 이벤트를 내보내야 한다."""
    builder = _Builder()
    builder.llm.structured_response = sample_routine_result()
    service = build_service(builder)

    events = await _run(service, chat_request(message="루틴 추천해줘"))

    assert events[-1][0] == "done"
    delta_texts = [data["text"] for event, data in events if event == "delta"]
    assert len(delta_texts) > 1

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "ROUTINE"
    assert "".join(delta_texts) == done["answer"]
    assert done["quick_replies"][0]["question_id"] == "ROUTINE_GOAL"


async def test_chat_allows_trainer_actor_after_spring_authorizes_access() -> None:
    builder = _Builder()
    service = build_service(builder)

    # Spring이 접근 권한을 검증한 트레이너 요청은 FastAPI SSE done 이벤트까지 진행한다.
    events = await _run(
        service, chat_request(actor=ActorContext(user_id=20, role=Role.TRAINER))
    )

    assert events[-1][0] == "done"
    assert all(event != "error" for event, _ in events)


async def test_chat_uses_spring_tool_for_function_calling(respx_mock) -> None:
    builder = _Builder()
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_latest_inbody", args={}, id="call-1")]),
        LLMResponse(text="최근 인바디 기록이 없습니다."),
    ]
    route = respx_mock.get("http://localhost:8080/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(200, json={"data": None})
    )
    service = build_service(builder)

    events = await _run(service, chat_request(message="최근 인바디 알려줘"))

    done = next(data for event, data in events if event == "done")
    assert done["category"] == "PERSONAL"
    assert route.called
    request_headers = route.calls[0].request.headers
    assert request_headers["X-Internal-Api-Key"] == "local-development-only"
    assert request_headers["X-Chatbot-Session-Id"] == "session-1"
    assert request_headers["X-Request-ID"] == done["request_id"]


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


async def test_chat_emits_llm_call_limit_exceeded_error_event(respx_mock) -> None:
    builder = _Builder()
    builder.llm.responses_queue = [
        LLMResponse(text="", tool_calls=[ToolCall(name="get_latest_inbody", args={"n": i}, id=f"call-{i}")])
        for i in range(10)
    ]
    respx_mock.get("http://localhost:8080/internal/chatbot/tools/inbody/latest").mock(
        return_value=httpx.Response(200, json={"data": None})
    )
    service = build_service(builder)

    events = await _run(service, chat_request(message="결제 내역 알려줘"))

    assert len(events) == 1
    event, data = events[0]
    assert event == "error"
    assert data["code"] == "LLM_CALL_LIMIT_EXCEEDED"


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
