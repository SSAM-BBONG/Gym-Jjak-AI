from fastapi import FastAPI

from app.core.error_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import request_context_middleware
from app.diet.router import router as diet_router
from app.trainer_report.router import router as trainer_report_router


def create_app() -> FastAPI:
    setup_logging()

    fastapi_app = FastAPI(title="Gym-Jjak AI Server", version="1.0.0")

    fastapi_app.middleware("http")(request_context_middleware)
    register_exception_handlers(fastapi_app)

    @fastapi_app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok"}

    @fastapi_app.get("/")
    def read_root():
        return {"message": "Hello, GymJjak AI!"}

    fastapi_app.include_router(diet_router)
    fastapi_app.include_router(trainer_report_router)

    return fastapi_app


app = create_app()
