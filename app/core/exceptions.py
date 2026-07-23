class AppError(Exception):
    """모든 도메인 오류의 공통 기반 클래스. status_code/code/message/retryable을 담아
    error_handlers.py가 {code, message, request_id, retryable} 응답으로 변환한다."""

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


def chatbot_tool_unavailable() -> AppError:
    return AppError(
        503,
        "CHATBOT_TOOL_UNAVAILABLE",
        "챗봇 도구 데이터를 현재 불러올 수 없습니다.",
        retryable=True,
    )


def chatbot_tool_access_denied(status_code: int) -> AppError:
    return AppError(
        status_code,
        "CHATBOT_TOOL_ACCESS_DENIED",
        "챗봇 도구 접근이 거부되었습니다.",
    )


def chatbot_tool_response_invalid(status_code: int = 502) -> AppError:
    return AppError(
        status_code,
        "CHATBOT_TOOL_RESPONSE_INVALID",
        "챗봇 도구 응답 형식이 올바르지 않습니다.",
    )


def internal_auth_failed() -> AppError:
    """Spring이 보낸 X-Internal-Api-Key가 없거나 틀렸을 때 반환하는 401 오류."""
    return AppError(401, "INTERNAL_AUTH_FAILED", "AI 서버 인증에 실패했습니다.")
