from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """앱 전체 환경설정 단일 출처. `.env`에서 값을 읽고, 없는 값은 아래 기본값을 쓴다."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "test", "production"] = "local"

    # 빈 기본값은 .env가 없는 테스트/CI 환경에서 import가 깨지지 않기 위한 것이며,
    # 실제 키 검증은 LLM 어댑터 생성 시점에 수행한다.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_max_retries: int = 0
    embedding_dimensions: int = 768
    gemini_timeout_seconds: float = Field(default=20.0, gt=0, le=60)

    spring_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8080")
    # diet/router.py가 secrets.compare_digest(str, str)로 직접 비교하므로
    # diet가 global 이관을 마치기 전까지 str 타입을 유지한다.
    internal_api_key: str = "local-development-only"
    spring_connect_timeout_seconds: float = 2.0
    spring_read_timeout_seconds: float = 5.0

    chroma_mode: Literal["persistent", "http"] = "persistent"
    chroma_persist_directory: Path = Path("data/indexes/chroma")
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_timeout_seconds: float = 3.0

    request_timeout_seconds: float = 60.0
    llm_call_limit: int = 6
    tool_call_limit: int = 5

    image_download_timeout_seconds: float = Field(default=5.0, gt=0, le=15)
    image_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Settings를 프로세스당 한 번만 생성해 캐싱한다. 챗봇 코드는 이 함수만 사용한다."""
    return Settings()


def __getattr__(name: str) -> Settings:
    # 기존 diet/llm 코드의 `from app.core.settings import settings` 하위호환.
    # import 시점이 아니라 실제 참조 시점에 생성해 테스트 수집 단계의 .env 접근을 막는다.
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
