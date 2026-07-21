from fastapi import FastAPI

from app.core.exceptions import register_exception_handlers
from app.trainer_report.router import router as trainer_report_router

app = FastAPI()

register_exception_handlers(app)

app.include_router(trainer_report_router)


@app.get("/")
def read_root():
    return {"message": "Hello, GymJjak AI!"}
