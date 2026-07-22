class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


def internal_auth_failed() -> AppError:
    return AppError(401, "INTERNAL_AUTH_FAILED", "AI 서버 인증에 실패했습니다.")


def llm_timeout() -> AppError:
    return AppError(504, "LLM_TIMEOUT", "AI 분석 응답 시간이 초과되었습니다.", True)


def llm_error(message: str) -> AppError:
    return AppError(502, "LLM_NETWORK_ERROR", message, True)
