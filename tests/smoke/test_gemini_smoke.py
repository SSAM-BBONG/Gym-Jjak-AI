"""실제 Gemini API를 호출해서 챗봇 대화 경로가 진짜로 동작하는지 확인하는 smoke test.
기본 `pytest` 실행에서는 스킵되고, `pytest --run-smoke`로만 실행된다(trainer_report의
tests/trainer_report/test_smoke.py와 동일한 게이팅 방식)."""

import time

import pytest

from app.chatbot.state import IntentClassification
from app.core.dependencies import get_llm_client
from app.llm.models import LLMMessage


@pytest.mark.smoke
async def test_gemini_single_call_smoke() -> None:
    llm = get_llm_client()

    start = time.monotonic()
    response = await llm.generate(
        [LLMMessage(role="user", content="안녕하세요, 한 문장으로만 인사해 주세요.")]
    )
    elapsed = time.monotonic() - start

    print(f"\n[smoke] generate() 응답 시간: {elapsed:.2f}s")

    # 프롬프트 원문·API 키는 출력하지 않는다 (ERROR_HANDLING.md 로그 정책)
    assert response.text


@pytest.mark.smoke
async def test_gemini_structured_output_smoke() -> None:
    """챗봇 의도 분류가 실제로 구조화 출력을 만들어내는지 확인한다(1회 호출)."""
    llm = get_llm_client()

    start = time.monotonic()
    result = await llm.generate_structured(
        prompt=(
            "다음 메시지를 personal/service_policy/routine/reject 중 하나로 분류하세요.\n"
            "메시지: 결제 내역 알려줘"
        ),
        output_schema=IntentClassification,
    )
    elapsed = time.monotonic() - start

    print(f"\n[smoke] generate_structured() 응답 시간: {elapsed:.2f}s, intent={result.intent}")

    assert result.intent in ("personal", "service_policy", "routine", "reject")
