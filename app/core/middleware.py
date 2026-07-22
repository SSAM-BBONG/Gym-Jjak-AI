import logging
import time

from fastapi import Request

from app.core.logging import REQUEST_ID_HEADER, get_request_id, set_request_id

logger = logging.getLogger(__name__)


async def request_context_middleware(request: Request, call_next):
    """Spring이 보낸 X-Request-ID를 보존하거나 없으면 생성해 요청 처리 동안 유지하고,
    성공 응답 헤더에 실어 보낸다. 예외 응답의 헤더는 core/error_handlers.py의
    _error_response()가 직접 채우므로 이 미들웨어를 거치지 않아도 항상 붙는다."""
    request_id = set_request_id(request.headers.get(REQUEST_ID_HEADER))
    started = time.perf_counter()
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    logger.info(
        "%s %s -> %s %.0fms",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response
