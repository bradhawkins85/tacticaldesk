import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def configure_environment(tmp_path, monkeypatch):
    db_path = tmp_path / "automation.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "1")
    monkeypatch.setenv("TACTICAL_DESK_MAINTENANCE_TOKEN", "test-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_automation_view_exposes_update_controls():
    with TestClient(app) as client:
        response = client.get("/automation")
        assert response.status_code == 200
        body = response.text
        assert "data-endpoint=\"/maintenance/update\"" in body
        assert "data-role=\"maintenance-token\"" in body
        assert "Awaiting secure update request" in body
