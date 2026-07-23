FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 의존성 레이어 분리로 소스 변경 시 설치 캐시 재사용
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# RAG 기본 문서를 포함한 애플리케이션 소스 복사
COPY . .

EXPOSE 8000

# VPC 내부 Spring 서버 요청을 수신하는 FastAPI 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
