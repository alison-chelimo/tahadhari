from app.config import Settings, get_settings
from app.supabase_client import get_supabase_client


def test_get_supabase_client_builds_from_settings(mocker):
    get_settings.cache_clear()
    get_supabase_client.cache_clear()
    mocker.patch(
        "app.supabase_client.get_settings",
        return_value=Settings(supabase_url="https://example.supabase.co", supabase_key="test-key"),
    )
    mock_create_client = mocker.patch("app.supabase_client.create_client")

    get_supabase_client()

    mock_create_client.assert_called_once_with("https://example.supabase.co", "test-key")


def test_get_supabase_client_is_cached(mocker):
    get_settings.cache_clear()
    get_supabase_client.cache_clear()
    mocker.patch(
        "app.supabase_client.get_settings",
        return_value=Settings(supabase_url="https://example.supabase.co", supabase_key="test-key"),
    )
    mock_create_client = mocker.patch("app.supabase_client.create_client")

    first = get_supabase_client()
    second = get_supabase_client()

    assert first is second
    mock_create_client.assert_called_once()
