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


def internal_auth_failed() -> AppError:
    """Spring이 보낸 X-Internal-Api-Key가 없거나 틀렸을 때 반환하는 401 오류."""
    return AppError(401, "INTERNAL_AUTH_FAILED", "AI 서버 인증에 실패했습니다.")
