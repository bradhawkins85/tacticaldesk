import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def setup_env(tmp_path, monkeypatch):
    db_path = tmp_path / "maintenance.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_scripts_endpoint_accessible_without_token():
    with TestClient(app) as client:
        response = client.get("/maintenance/scripts")
        assert response.status_code == 200
        payload = response.json()
        assert payload["enabled"] is False
        assert any(script["slug"] == "install" for script in payload["scripts"])


def test_install_disabled_when_not_enabled():
    with TestClient(app) as client:
        response = client.post("/maintenance/install")
        assert response.status_code == 503
