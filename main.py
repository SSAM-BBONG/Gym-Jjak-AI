from fastapi import FastAPI

from app.chatbot.router import router as chatbot_router
from app.core.error_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import request_context_middleware
from app.diet.router import router as diet_router
from app.routine.router import router as routine_router
from app.trainer_report.router import router as trainer_report_router


def create_app() -> FastAPI:
    """FastAPI 앱 조립부. 미들웨어·예외 핸들러·라우터를 연결하기만 하고 로직은 두지 않는다."""
    setup_logging()

    fastapi_app = FastAPI(title="Gym-Jjak AI Server", version="1.0.0")

    fastapi_app.middleware("http")(request_context_middleware)
    register_exception_handlers(fastapi_app)

    @fastapi_app.get("/health", tags=["ops"])
    def health():
        """헬스체크. 배포 환경의 liveness probe용."""
        return {"status": "ok"}

    @fastapi_app.get("/")
    def read_root():
        """루트 경로 동작 확인용 엔드포인트."""
        return {"message": "Hello, GymJjak AI!"}

    fastapi_app.include_router(diet_router)
    fastapi_app.include_router(trainer_report_router)
    fastapi_app.include_router(chatbot_router)
    fastapi_app.include_router(routine_router)

    return fastapi_app


app = create_app()
