from app.core.exceptions import AppError


class LLMCallLimitExceededError(AppError):
    """한 요청 안에서 LLM 호출 한도(settings.llm_call_limit)를 초과했을 때."""

    def __init__(self) -> None:
        super().__init__(
            503,
            "LLM_CALL_LIMIT_EXCEEDED",
            "요청 처리 중 호출 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
            retryable=True,
        )


class ChatRequestTimeoutError(AppError):
    """그래프 실행이 request_timeout_seconds(기본 60초)를 넘겼을 때."""

    def __init__(self) -> None:
        super().__init__(
            504,
            "CHATBOT_REQUEST_TIMEOUT",
            "요청 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
            retryable=True,
        )
