from typing import Callable

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from app.core.settings import settings
from app.llm.errors import LLMInvalidResponseError, LLMNetworkError, LLMRateLimitedError
from app.llm.models import LLMMessage, LLMResponse, ToolCall

_ROLE_TO_MESSAGE_CLASS = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


def _to_langchain_message(message: LLMMessage):
    """LangChain은 이 파일 안에서만 다룬다 — 이 함수 밖으로 LangChain 타입이 나가지 않는다."""
    if message.role == "tool":
        return ToolMessage(content=message.content, tool_call_id=message.tool_call_id or "")
    message_cls = _ROLE_TO_MESSAGE_CLASS[message.role]
    return message_cls(content=message.content)


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
    """LLMPort 구현체. Gemini 모델 1회 호출과 오류 변환만 담당한다.
    LangChain은 이 파일 안에서만 사용한다."""

    def __init__(self) -> None:
        self._model = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[Callable] | None = None,
    ) -> LLMResponse:
        model = self._model.bind_tools(tools) if tools else self._model
        langchain_messages = [_to_langchain_message(m) for m in messages]

        try:
            response = await model.ainvoke(langchain_messages)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise LLMNetworkError(str(e)) from e
        except ChatGoogleGenerativeAIError as e:
            error_text = str(e)
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                raise LLMRateLimitedError(error_text) from e
            raise LLMNetworkError(error_text) from e

        tool_calls = [
            ToolCall(name=tc["name"], args=tc["args"], id=tc["id"])
            for tc in (response.tool_calls or [])
        ]
        text = _extract_text(response.content)

        if text is None and not tool_calls:
            raise LLMInvalidResponseError("Gemini 응답에 text와 tool_calls가 모두 없습니다.")

        return LLMResponse(text=text, tool_calls=tool_calls)
