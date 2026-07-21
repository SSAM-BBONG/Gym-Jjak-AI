import base64
import asyncio
from typing import Callable

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.core.settings import settings
from app.llm.port import LLMResponse, StructuredOutput, ToolCall


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
        messages: list[tuple[str, str]],
        tools: list[Callable] | None = None,
    ) -> LLMResponse:
        base_model = self._get_model()
        model = base_model.bind_tools(tools) if tools else base_model
        response = await model.ainvoke(messages)

        tool_calls = [
            ToolCall(name=tc["name"], args=tc["args"], id=tc["id"])
            for tc in (response.tool_calls or [])
        ]

        text = _extract_text(response.content)
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
