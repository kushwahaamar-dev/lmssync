import pytest
from pathlib import Path
import os
import sys

# Ensure src is in path for tests
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables."""
    monkeypatch.setenv("CANVAS_BASE_URL", "https://canvas.test")
    monkeypatch.setenv("CANVAS_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "test_client")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "test_tenant")
    monkeypatch.setenv("SYNC_TASK_LIST_NAME", "Test List")
