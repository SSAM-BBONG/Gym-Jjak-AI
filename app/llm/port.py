from typing import Callable, Protocol

from app.llm.models import LLMMessage, LLMResponse


class LLMPort(Protocol):
    """공통 LLM 호출 인터페이스. Gemini를 1회 호출하고 공통 응답으로 변환하는 역할까지만 담당한다.
    Function Calling 반복, RAG 검색, 프롬프트 구성 등 오케스트레이션은 각 도메인(chain.py)이 담당한다."""

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[Callable] | None = None,
    ) -> LLMResponse: ...
