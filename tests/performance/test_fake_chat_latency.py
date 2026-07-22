"""Fake LLM/Retriever/UserDataClient로 100개 요청을 그래프에 흘려 처리시간을 측정한다.
외부 API 비용 없이 애플리케이션 오버헤드와 그래프 분기 회귀를 감지하는 용도다.
Run: python -m pytest tests/performance/test_fake_chat_latency.py -q -s"""

import time

from app.llm.models import LLMResponse

from tests.graph.conftest import _Builder, chat_state
from app.chatbot.graph import build_chatbot_graph

_REQUEST_COUNT = 100


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(len(sorted_values) * p))
    return sorted_values[index]


async def test_fake_chat_latency_percentiles_and_error_rate() -> None:
    graph = build_chatbot_graph()
    durations: list[float] = []
    errors = 0

    for i in range(_REQUEST_COUNT):
        builder = _Builder()
        builder.llm.response = LLMResponse(text=f"응답 {i}")

        started = time.perf_counter()
        try:
            result = await graph.ainvoke(
                chat_state(message="환불 정책이 궁금해요", session_id=f"session-{i}"),
                config=builder.config(),
            )
            if result.get("error_code"):
                errors += 1
        except Exception:
            errors += 1
        durations.append((time.perf_counter() - started) * 1000)

    durations.sort()
    p50 = _percentile(durations, 0.50)
    p95 = _percentile(durations, 0.95)
    p99 = _percentile(durations, 0.99)
    error_rate = errors / _REQUEST_COUNT

    print(
        f"\n[fake-latency] n={_REQUEST_COUNT} "
        f"p50={p50:.2f}ms p95={p95:.2f}ms p99={p99:.2f}ms "
        f"error_rate={error_rate:.1%}"
    )

    assert error_rate == 0.0
    # Fake 구현체만 쓰므로 순수 애플리케이션 오버헤드다 — 실제 Gemini/Chroma 없이
    # 이 정도(500ms)를 넘으면 그래프 분기나 DI 조립에 회귀가 생겼다는 신호로 본다.
    assert p99 < 500
