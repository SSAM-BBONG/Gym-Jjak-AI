import base64
import asyncio
from typing import AsyncIterator

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from pydantic import BaseModel, ValidationError

from app.core.settings import settings
from app.llm.errors import LLMInvalidResponseError, LLMNetworkError, LLMRateLimitedError
from app.llm.models import LLMMessage, LLMResponse, LLMStreamChunk, ToolCall
from app.llm.port import StructuredOutput, ToolDefinition

_ROLE_TO_MESSAGE_CLASS = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}

# langchain-google-genai 내부 전용 키(밑줄 2개, non-public)를 문자열로 그대로 미러링한다.
# Gemini 2.5+/3 계열은 Function Calling 멀티턴에서 이전 턴의 thought_signature를 echo하지
# 않으면 400 INVALID_ARGUMENT로 거부한다. langchain-google-genai는 응답 파싱 시 이 키로
# AIMessage.additional_kwargs에 {tool_call_id: base64_signature}를 채워주고, 다음 턴 요청을
# 만들 때도 같은 키에서 서명을 읽어간다 — 그래서 우리도 왕복시킬 때 이 키를 그대로 써야 한다.
# 주의: langchain-google-genai 버전이 올라가며 이 내부 키 이름이 바뀌면 이 상수도 갱신해야 한다.
_THOUGHT_SIGNATURE_KEY = "__gemini_function_call_thought_signatures__"


def _to_langchain_message(message: LLMMessage):
    """LangChain은 이 파일 안에서만 다룬다 — 이 함수 밖으로 LangChain 타입이 나가지 않는다."""
    if message.role == "tool":
        return ToolMessage(content=message.content, tool_call_id=message.tool_call_id or "")
    if message.role == "assistant" and message.tool_calls:
        # 이전 턴에서 모델이 요청한 도구 호출을 그대로 재현해야 LangChain이
        # 뒤따르는 ToolMessage들과 올바르게 짝지어준다. thought_signature가 있으면
        # 같이 echo해야 Gemini 2.5+/3 계열이 요청을 거부하지 않는다.
        signature_map = {
            tc.id: tc.thought_signature for tc in message.tool_calls if tc.thought_signature
        }
        return AIMessage(
            content=message.content,
            tool_calls=[
                {"name": tc.name, "args": tc.args, "id": tc.id} for tc in message.tool_calls
            ],
            additional_kwargs=({_THOUGHT_SIGNATURE_KEY: signature_map} if signature_map else {}),
        )
    message_cls = _ROLE_TO_MESSAGE_CLASS[message.role]
    return message_cls(content=message.content)


def _raise_for_gemini_error(e: Exception) -> None:
    """ChatGoogleGenerativeAIError를 세분화한다. 429는 재시도 가능한 요청 한도 초과,
    INVALID_ARGUMENT(400)는 우리가 보낸 요청 자체가 잘못된 것이라 재시도해도 똑같이
    실패하므로 network error와 구분한다."""
    error_text = str(e)
    if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
        raise LLMRateLimitedError(error_text) from e
    if "INVALID_ARGUMENT" in error_text:
        raise LLMInvalidResponseError(error_text) from e
    raise LLMNetworkError(error_text) from e


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

    def __init__(self, *, temperature: float = 0.1) -> None:
        self._temperature = temperature
        self._model: ChatGoogleGenerativeAI | None = None

    def _get_model(self) -> ChatGoogleGenerativeAI:
        if self._model is not None:
            return self._model
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY 환경변수가 필요합니다.")
        self._model = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=self._temperature,
            max_retries=0,
        )
        return self._model

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        base_model = self._get_model()
        model = base_model.bind_tools(tools) if tools else base_model
        langchain_messages = [_to_langchain_message(m) for m in messages]

        try:
            response = await model.ainvoke(langchain_messages)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise LLMNetworkError(str(e)) from e
        except ChatGoogleGenerativeAIError as e:
            _raise_for_gemini_error(e)

        # Gemini가 함수 호출에 thought_signature를 실어 보내면 다음 턴에 그대로
        # echo해야 하므로, 여기서 추출해 각 ToolCall에 담아둔다.
        signature_map = response.additional_kwargs.get(_THOUGHT_SIGNATURE_KEY, {})
        tool_calls = [
            ToolCall(
                name=tc["name"],
                args=tc["args"],
                id=tc["id"],
                thought_signature=signature_map.get(tc["id"]),
            )
            for tc in (response.tool_calls or [])
        ]
        text = _extract_text(response.content)

        if text is None and not tool_calls:
            raise LLMInvalidResponseError("Gemini 응답에 text와 tool_calls가 모두 없습니다.")

        return LLMResponse(text=text, tool_calls=tool_calls)

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """generate()와 같은 호출을 토큰 단위로 흘려보낸다. tool_calls는 일반적으로
        마지막 청크에만 전체가 채워져 오므로, 각 청크의 tool_calls를 그때그때 최신값으로
        덮어써서 최종 청크의 값을 쓴다(langchain-google-genai 스트리밍 응답 구조 기준)."""
        base_model = self._get_model()
        model = base_model.bind_tools(tools) if tools else base_model
        langchain_messages = [_to_langchain_message(m) for m in messages]

        text_parts: list[str] = []
        tool_calls_raw: list[dict] = []
        # Gemini는 Function Call마다 별도 thought_signature를 보낼 수 있다.
        # 스트림 청크의 맵을 통째로 덮어쓰면 앞선 도구의 서명이 사라져,
        # 도구 결과를 받은 다음 Gemini 호출이 400으로 거절될 수 있다.
        thought_signature_map: dict[str, str] = {}
        try:
            async for chunk in model.astream(langchain_messages):
                piece = _extract_text(chunk.content)
                if piece:
                    text_parts.append(piece)
                    yield LLMStreamChunk(delta=piece)
                if chunk.tool_calls:
                    tool_calls_raw = chunk.tool_calls
                if chunk.additional_kwargs:
                    signatures = chunk.additional_kwargs.get(_THOUGHT_SIGNATURE_KEY)
                    if isinstance(signatures, dict):
                        thought_signature_map.update(signatures)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise LLMNetworkError(str(e)) from e
        except ChatGoogleGenerativeAIError as e:
            _raise_for_gemini_error(e)

        tool_calls = [
            ToolCall(
                name=tc["name"],
                args=tc["args"],
                id=tc["id"],
                thought_signature=thought_signature_map.get(tc["id"]),
            )
            for tc in tool_calls_raw
        ]
        text = "".join(text_parts) or None

        if text is None and not tool_calls:
            raise LLMInvalidResponseError("Gemini 스트리밍 응답에 text와 tool_calls가 모두 없습니다.")

        yield LLMStreamChunk(response=LLMResponse(text=text, tool_calls=tool_calls))

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
            _raise_for_gemini_error(e)

        try:
            if isinstance(result, BaseModel):
                return output_schema.model_validate(result.model_dump())
            return output_schema.model_validate(result)
        except ValidationError as e:
            raise LLMInvalidResponseError(str(e)) from e
