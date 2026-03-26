import pytest


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Limpa o cache de settings entre testes para isolar configurações."""
    from rundeck_mcp.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
