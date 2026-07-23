"""GeminiAdapter.generate_structured()의 계약만 검증한다.
기존 generate()/generate_structured_image()는 trainer_report/diet 소유 로직이라
여기서 재검증하지 않는다 — append로 추가한 새 메서드만 다룬다."""

from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import BaseModel

from app.llm.errors import LLMInvalidResponseError, LLMNetworkError
from app.llm.gemini_adapter import GeminiAdapter


class _Plan(BaseModel):
    title: str
    steps: list[str]


class _FakeStructuredModel:
    def __init__(self, result: object) -> None:
        self._result = result
        self.ainvoke = AsyncMock(return_value=result)


def _adapter_with_structured_model(result: object) -> GeminiAdapter:
    adapter = GeminiAdapter()
    fake_structured_model = _FakeStructuredModel(result)
    fake_base_model = type(
        "FakeBaseModel",
        (),
        {"with_structured_output": lambda self, schema, method: fake_structured_model},
    )()
    adapter._model = fake_base_model
    return adapter, fake_structured_model


async def test_generate_structured_returns_validated_output() -> None:
    adapter, fake_model = _adapter_with_structured_model(
        {"title": "3일 루틴", "steps": ["가슴", "등", "하체"]}
    )

    result = await adapter.generate_structured(prompt="루틴 짜줘", output_schema=_Plan)

    assert result == _Plan(title="3일 루틴", steps=["가슴", "등", "하체"])
    fake_model.ainvoke.assert_awaited_once()


async def test_generate_structured_wraps_invalid_result_as_llm_error() -> None:
    adapter, _ = _adapter_with_structured_model({"title": "3일 루틴"})  # steps 누락

    with pytest.raises(LLMInvalidResponseError):
        await adapter.generate_structured(prompt="루틴 짜줘", output_schema=_Plan)


async def test_generate_structured_converts_network_error() -> None:
    adapter, fake_model = _adapter_with_structured_model(None)
    fake_model.ainvoke.side_effect = httpx.TimeoutException("timeout")

    with pytest.raises(LLMNetworkError):
        await adapter.generate_structured(prompt="루틴 짜줘", output_schema=_Plan)

    fake_model.ainvoke.assert_awaited_once()
