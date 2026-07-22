import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.logging import REQUEST_ID_HEADER, get_request_id
from app.llm.errors import LLMError

logger = logging.getLogger(__name__)

_LLM_ERROR_STATUS = {
    "LLM_NETWORK_ERROR": 503,
    "LLM_RATE_LIMITED": 503,
    "LLM_INVALID_RESPONSE": 502,
}

# LLM_INVALID_RESPONSE(요청 자체가 잘못됨/응답 구조 검증 실패)는 재시도해도 같은 결과를
# 반복하므로 retryable=False다. 네트워크·요청한도 초과만 사용자가 다시 시도할 여지가 있다.
_LLM_ERROR_RETRYABLE = {
    "LLM_NETWORK_ERROR": True,
    "LLM_RATE_LIMITED": True,
    "LLM_INVALID_RESPONSE": False,
}


def _error_response(status_code: int, code: str, message: str, retryable: bool) -> JSONResponse:
    """모든 오류 응답이 공유하는 빌더. 본문 request_id와 X-Request-ID 헤더를 항상 함께
    채운다. Exception 핸들러(ServerErrorMiddleware)는 커스텀 미들웨어 바깥에서 실행되어
    request_context_middleware가 응답 헤더를 붙일 기회를 얻지 못하므로, 헤더는 미들웨어가
    아니라 이 빌더가 직접 설정해 어떤 예외 경로에서도 누락되지 않게 한다."""
    request_id = get_request_id()
    return JSONResponse(
        status_code=status_code,
        headers={REQUEST_ID_HEADER: request_id},
        content={
            "code": code,
            "message": message,
            "request_id": request_id,
            "retryable": retryable,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """ERROR_HANDLING.md 공통 응답 포맷: {code, message, request_id, retryable}
    Gemini 세부 오류는 로그로만 남기고, 사용자(Java)에게는 단순화된 메시지만 반환한다."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """도메인에서 던진 AppError(및 하위 클래스)를 공통 오류 응답으로 변환한다."""
        logger.warning("handled_error code=%s", exc.code)
        return _error_response(exc.status_code, exc.code, exc.message, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Pydantic 요청 검증 실패를 422 공통 오류 응답으로 변환한다."""
        logger.warning(
            "request_validation_error count=%d errors=%s",
            len(exc.errors()),
            exc.errors(),
        )
        return _error_response(422, "REQUEST_VALIDATION_ERROR", "요청 형식이 올바르지 않습니다.", False)

    @app.exception_handler(LLMError)
    async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
        """Gemini 호출 실패(LLMError 계열)를 오류 코드별 상태코드로 변환한다."""
        logger.warning("llm_error code=%s", exc.code)
        status_code = _LLM_ERROR_STATUS.get(exc.code, 500)
        retryable = _LLM_ERROR_RETRYABLE.get(exc.code, False)
        message = (
            "AI 서버 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            if retryable
            else "요청을 처리하지 못했습니다. 다른 방식으로 다시 시도해 주세요."
        )
        return _error_response(status_code, exc.code, message, retryable)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """분류되지 않은 예외(버그)를 500 공통 오류 응답으로 변환하고 스택트레이스는 로그에만 남긴다."""
        logger.exception("unexpected_error")
        return _error_response(500, "INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", False)
