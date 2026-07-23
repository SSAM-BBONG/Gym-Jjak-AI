from app.core.exceptions import AppError


class SubjectAccessDeniedError(AppError):
    """트레이너가 담당하지 않는 회원의 데이터를 조회하려 할 때."""

    def __init__(self) -> None:
        super().__init__(
            403,
            "TRAINER_SUBJECT_ACCESS_DENIED",
            "담당하지 않는 회원의 데이터는 조회할 수 없습니다.",
            retryable=False,
        )
