import pytest

from app.core.settings import Settings, get_settings


@pytest.fixture
def test_settings() -> Settings:
    # _env_file=None으로 실제 .env 접근을 차단한 테스트 전용 설정
    return Settings(
        _env_file=None,
        app_env="test",
        gemini_api_key="test-key",
        spring_base_url="http://spring.test",
        internal_api_key="test-internal-key",
    )


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    # 테스트 간 get_settings() 캐시 오염 방지
    get_settings.cache_clear()
