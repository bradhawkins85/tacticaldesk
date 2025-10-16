import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def integration_db(tmp_path, monkeypatch):
    db_path = tmp_path / "integrations.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_seeded_integrations_available():
    with TestClient(app) as client:
        response = client.get("/api/integrations")
        assert response.status_code == 200
        payload = response.json()
        slugs = {item["slug"] for item in payload}
        assert {"syncro-rmm", "tactical-rmm", "xero"}.issubset(slugs)
        status_map = {item["slug"]: item["enabled"] for item in payload}
        assert status_map["syncro-rmm"] is True
        assert status_map["tactical-rmm"] is True
        assert status_map["xero"] is False


def test_toggle_integration_updates_navigation():
    with TestClient(app) as client:
        disable_response = client.patch("/api/integrations/syncro-rmm", json={"enabled": False})
        assert disable_response.status_code == 200
        assert disable_response.json()["enabled"] is False

        html_response = client.get("/integrations")
        assert html_response.status_code == 200
        html = html_response.text
        assert "SyncroRMM" in html
        assert 'data-integration-link="syncro-rmm"' not in html


def test_update_integration_settings_reflected_in_detail():
    with TestClient(app) as client:
        payload = {
            "settings": {
                "base_url": "https://syncro.example/api",
                "api_key": "SecureKey123",
            }
        }
        response = client.patch("/api/integrations/syncro-rmm", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["api_key"] == "SecureKey123"

        detail_response = client.get("/integrations/syncro-rmm")
        assert detail_response.status_code == 200
        detail_html = detail_response.text
        assert "https://syncro.example/api" in detail_html
        assert "SecureKey123" in detail_html
