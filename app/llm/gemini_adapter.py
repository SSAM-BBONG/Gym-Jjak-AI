import base64
import asyncio
from typing import Callable

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from pydantic import BaseModel, ValidationError

from app.core.settings import settings
from app.llm.errors import LLMInvalidResponseError, LLMNetworkError, LLMRateLimitedError
from app.llm.models import LLMMessage, LLMResponse, ToolCall
from app.llm.port import StructuredOutput

_ROLE_TO_MESSAGE_CLASS = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


def _to_langchain_message(message: LLMMessage):
    """LangChain은 이 파일 안에서만 다룬다 — 이 함수 밖으로 LangChain 타입이 나가지 않는다."""
    if message.role == "tool":
        return ToolMessage(content=message.content, tool_call_id=message.tool_call_id or "")
    if message.role == "assistant" and message.tool_calls:
        # 이전 턴에서 모델이 요청한 도구 호출을 그대로 재현해야 LangChain이
        # 뒤따르는 ToolMessage들과 올바르게 짝지어준다.
        return AIMessage(
            content=message.content,
            tool_calls=[
                {"name": tc.name, "args": tc.args, "id": tc.id} for tc in message.tool_calls
            ],
        )
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
        self._model: ChatGoogleGenerativeAI | None = None

    def _get_model(self) -> ChatGoogleGenerativeAI:
        if self._model is not None:
            return self._model
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY 환경변수가 필요합니다.")
        self._model = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.1,
            max_retries=0,
        )
        return self._model

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[Callable] | None = None,
    ) -> LLMResponse:
        base_model = self._get_model()
        model = base_model.bind_tools(tools) if tools else base_model
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

    async def generate_structured_image(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
        output_schema: type[StructuredOutput],
    ) -> StructuredOutput:
        """이미지 한 장을 Gemini native JSON Schema 출력으로 분석한다."""
        encoded = base64.b64encode(image_bytes).decode("ascii")
        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image", "base64": encoded, "mime_type": mime_type},
        ])
        structured_model = self._get_model().with_structured_output(
            schema=output_schema.model_json_schema(),
            method="json_schema",
        )
        result = await asyncio.wait_for(
            structured_model.ainvoke([message]),
            timeout=settings.gemini_timeout_seconds,
        )
        if isinstance(result, BaseModel):
            return output_schema.model_validate(result.model_dump())
        return output_schema.model_validate(result)

    async def generate_structured(
        self,
        *,
        prompt: str,
        output_schema: type[StructuredOutput],
    ) -> StructuredOutput:
        """이미지 없이 텍스트 프롬프트만으로 구조화 출력을 받는다.
        generate_structured_image()와 달리 이미지 파트가 필요 없는 순수 텍스트 호출이다."""
        structured_model = self._get_model().with_structured_output(
            schema=output_schema.model_json_schema(),
            method="json_schema",
        )
        try:
            result = await asyncio.wait_for(
                structured_model.ainvoke([HumanMessage(content=prompt)]),
                timeout=settings.gemini_timeout_seconds,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise LLMNetworkError(str(e)) from e
        except ChatGoogleGenerativeAIError as e:
            error_text = str(e)
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                raise LLMRateLimitedError(error_text) from e
            raise LLMNetworkError(error_text) from e

        try:
            if isinstance(result, BaseModel):
                return output_schema.model_validate(result.model_dump())
            return output_schema.model_validate(result)
        except ValidationError as e:
            raise LLMInvalidResponseError(str(e)) from e
