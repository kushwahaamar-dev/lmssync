import pytest
from config.settings import load_settings, ConfigurationError, Settings

def test_load_settings_success(mock_env):
    """Test loading settings with valid environment variables."""
    settings = load_settings()
    
    assert isinstance(settings, Settings)
    assert settings.canvas.base_url == "https://canvas.test"
    assert settings.canvas.access_token == "test_token"
    assert settings.microsoft.client_id == "test_client"
    assert settings.sync.task_list_name == "Test List"

def test_load_settings_missing_canvas_url(monkeypatch):
    """Test error when Canvas URL is missing."""
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    # Ensure other vars are set to isolate the error
    monkeypatch.setenv("CANVAS_ACCESS_TOKEN", "token")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "id")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "tenant")
    
    with pytest.raises(ConfigurationError, match="CANVAS_BASE_URL is required"):
        load_settings()

def test_load_settings_invalid_url(monkeypatch):
    """Test error when Canvas URL is not HTTPS."""
    monkeypatch.setenv("CANVAS_BASE_URL", "http://insecure.test")
    monkeypatch.setenv("CANVAS_ACCESS_TOKEN", "token")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "id")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "tenant")
    
    with pytest.raises(ConfigurationError, match="must use HTTPS"):
        load_settings()
