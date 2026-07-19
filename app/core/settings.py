from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str
    gemini_model: str = "gemini-flash-latest"

    spring_base_url: str = "http://localhost:8080"
    internal_api_key: str = ""


settings = Settings()
