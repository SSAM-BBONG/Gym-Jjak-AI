from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = Field(default=20.0, gt=0, le=60)

    spring_base_url: str = "http://localhost:8080"
    internal_api_key: str = "local-development-only"

    image_download_timeout_seconds: float = Field(default=5.0, gt=0, le=15)
    image_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)


settings = Settings()
