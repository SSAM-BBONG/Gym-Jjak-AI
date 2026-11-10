"""GeminiAdapter.generate_structured()의 계약만 검증한다.
기존 generate()/generate_structured_image()는 trainer_report/diet 소유 로직이라
여기서 재검증하지 않는다 — append로 추가한 새 메서드만 다룬다."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from pydantic import BaseModel

from app.llm import gemini_adapter
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


async def test_generate_structured_logs_token_usage(caplog) -> None:
    adapter, fake_model = _adapter_with_structured_model({"title": "루틴", "steps": ["가슴"]})
    adapter._feature = "routine"
    usage = {
        "input_tokens": 1118,
        "output_tokens": 1978,
        "total_tokens": 3096,
        "output_token_details": {"reasoning": 578},
    }

    async def _invoke_with_usage(messages, config):
        # 실제 Gemini 호출처럼 콜백에 usage_metadata가 담긴 결과를 알린다.
        message = AIMessage(content="", usage_metadata=usage, response_metadata={"model_name": "gemini-test"})
        config["callbacks"][0].on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]))
        return {"title": "루틴", "steps": ["가슴"]}

    fake_model.ainvoke.side_effect = _invoke_with_usage

    with caplog.at_level(logging.INFO, logger="app.llm.gemini_adapter"):
        await adapter.generate_structured(prompt="루틴 짜줘", output_schema=_Plan)

    log = next(r.getMessage() for r in caplog.records if "llm_token_usage" in r.getMessage())
    assert "feature=routine" in log
    assert "input_tokens=1118" in log
    assert "output_tokens=1978" in log
    assert "reasoning_tokens=578" in log
    assert "total_tokens=3096" in log


def test_thinking_level_is_passed_only_when_configured(monkeypatch) -> None:
    created: list[dict] = []
    monkeypatch.setattr(gemini_adapter, "ChatGoogleGenerativeAI", lambda **kwargs: created.append(kwargs))
    monkeypatch.setattr(
        gemini_adapter, "settings", SimpleNamespace(gemini_api_key="test-key", gemini_model="gemini-test")
    )

    GeminiAdapter(thinking_level="low")._get_model()
    GeminiAdapter()._get_model()

    assert created[0]["thinking_level"] == "low"
    assert "thinking_level" not in created[1]


async def test_generate_structured_converts_network_error() -> None:
    adapter, fake_model = _adapter_with_structured_model(None)
    fake_model.ainvoke.side_effect = httpx.TimeoutException("timeout")

    with pytest.raises(LLMNetworkError):
        await adapter.generate_structured(prompt="루틴 짜줘", output_schema=_Plan)

    fake_model.ainvoke.assert_awaited_once()
