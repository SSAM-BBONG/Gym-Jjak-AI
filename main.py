import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError, register_exception_handlers
from app.core.logging import REQUEST_ID_HEADER, get_request_id, set_request_id, setup_logging
from app.diet.router import router as diet_router
from app.pt_recommendation.router import router as pt_recommendation_router
from app.trainer_report.router import router as trainer_report_router


setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Gym-Jjak AI Server", version="1.0.0")

register_exception_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
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


def error_body(code: str, message: str, retryable: bool) -> dict:
    return {
        "code": code,
        "message": message,
        "request_id": get_request_id(),
        "retryable": retryable,
    }


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    logger.warning("handled_error code=%s", exc.code)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.retryable),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    logger.warning(
        "request_validation_error count=%d errors=%s",
        len(exc.errors()),
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=error_body("REQUEST_VALIDATION_ERROR", "요청 형식이 올바르지 않습니다.", False),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logger.exception("unexpected_error")
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", False),
    )


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


@app.get("/")
def read_root():
    return {"message": "Hello, GymJjak AI!"}


app.include_router(diet_router)
app.include_router(pt_recommendation_router)
app.include_router(trainer_report_router)
