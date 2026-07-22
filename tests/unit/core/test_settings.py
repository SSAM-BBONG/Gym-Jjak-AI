from app.core.settings import Settings


def test_settings_can_be_created_without_env_file() -> None:
    settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        spring_base_url="http://spring.test",
        internal_api_key="test-internal-key",
    )

    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.gemini_max_retries == 0
    assert settings.chroma_mode == "persistent"
    assert settings.embedding_dimensions == 768
