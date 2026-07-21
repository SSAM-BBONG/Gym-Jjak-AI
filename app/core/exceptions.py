import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.llm.errors import LLMError

_LLM_ERROR_STATUS = {
    "LLM_NETWORK_ERROR": 503,
    "LLM_RATE_LIMITED": 503,
    "LLM_INVALID_RESPONSE": 502,
}


def register_exception_handlers(app: FastAPI) -> None:
    """ERROR_HANDLING.md 공통 응답 포맷: {code, message, request_id, retryable}
    Gemini 세부 오류는 로그로만 남기고, 사용자(Java)에게는 단순화된 메시지만 반환한다."""

    @app.exception_handler(LLMError)
    async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
        request_id = str(uuid.uuid4())
        status_code = _LLM_ERROR_STATUS.get(exc.code, 500)
        return JSONResponse(
            status_code=status_code,
            content={
                "code": exc.code,
                "message": "AI 서버 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                "request_id": request_id,
                "retryable": True,
            },
        )
