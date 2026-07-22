"""챗봇 루틴 추천(Task 8)이 필요로 하는 텍스트 전용 구조화 출력 계약.
diet의 generate_structured_image()는 이미지가 필수라 재사용할 수 없어,
같은 LLMPort에 이미지 없는 generate_structured()를 append로 추가한다."""

from pydantic import BaseModel

from tests.fakes.llm import FakeLLMPort


class _Greeting(BaseModel):
    text: str
    confidence: float


async def test_fake_llm_generate_structured_returns_configured_value() -> None:
    llm = FakeLLMPort(structured_response=_Greeting(text="안녕하세요", confidence=0.9))

    result = await llm.generate_structured(prompt="인사해줘", output_schema=_Greeting)

    assert result == _Greeting(text="안녕하세요", confidence=0.9)
    assert llm.structured_call_count == 1


async def test_fake_llm_generate_structured_records_prompt_and_schema() -> None:
    llm = FakeLLMPort(structured_response=_Greeting(text="안녕", confidence=0.5))

    await llm.generate_structured(prompt="인사해줘", output_schema=_Greeting)

    assert llm.structured_prompts == ["인사해줘"]
    assert llm.structured_schemas == [_Greeting]
