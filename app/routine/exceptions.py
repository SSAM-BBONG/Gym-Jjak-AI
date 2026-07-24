from app.core.exceptions import AppError


class ActorRoleNotAllowedError(AppError):
    """회원 전용 경로를 트레이너가, 또는 그 반대로 호출했을 때."""

    def __init__(self) -> None:
        super().__init__(403, "ROLE_NOT_ALLOWED", "이 기능을 사용할 권한이 없습니다.", retryable=False)
