from typing import Callable

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.settings import settings
from app.llm.port import LLMResponse, ToolCall


def _extract_text(content: object) -> str | None:
    """최신 Gemini 응답은 content가 문자열이 아니라
    [{'type': 'text', 'text': '...'}] 형태의 리스트로 오는 경우가 있어 이를 흡수한다."""
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "".join(parts)
        return text or None
    return None


class GeminiAdapter:
    """LLMPort 구현체. LangChain은 이 파일 안에서만 사용한다."""

    def __init__(self) -> None:
        self._model = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
        )

    async def generate(
        self,
        messages: list[tuple[str, str]],
        tools: list[Callable] | None = None,
    ) -> LLMResponse:
        model = self._model.bind_tools(tools) if tools else self._model
        response = await model.ainvoke(messages)

        tool_calls = [
            ToolCall(name=tc["name"], args=tc["args"], id=tc["id"])
            for tc in (response.tool_calls or [])
        ]

        text = _extract_text(response.content)
        return LLMResponse(text=text, tool_calls=tool_calls)
