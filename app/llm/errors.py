class LLMError(Exception):
    """공통 LLM 오류. code는 ERROR_HANDLING.md의 오류 코드 체계를 따른다."""

    code: str = "LLM_ERROR"


class LLMNetworkError(LLMError):
    """연결 실패, 타임아웃, 5xx 등 일시적 통신 장애."""

    code = "LLM_NETWORK_ERROR"


class LLMRateLimitedError(LLMError):
    """Gemini 요청 한도(429) 초과."""

    code = "LLM_RATE_LIMITED"


class LLMInvalidResponseError(LLMError):
    """응답 구조가 기대와 달라 파싱/검증에 실패한 경우."""

    code = "LLM_INVALID_RESPONSE"
