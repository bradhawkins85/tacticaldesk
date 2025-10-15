import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    monkeypatch.setenv("TACTICAL_DESK_MAINTENANCE_TOKEN", "test-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_registration_flow():
    with TestClient(app) as client:
        response = client.post(
            "/auth/register",
            json={"email": "admin@example.com", "password": "SecurePass123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_super_admin"] is True

        # Registration locked after the super admin exists
        response = client.post(
            "/auth/register",
            json={"email": "admin2@example.com", "password": "SecurePass123"},
        )
        assert response.status_code == 403

        login_response = client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "SecurePass123"},
        )
        assert login_response.status_code == 200
        assert login_response.json()["email"] == "admin@example.com"


def test_root_route_registers_when_no_admin():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Create the Super Admin" in response.text


def test_root_route_shows_login_after_admin_exists():
    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={"email": "admin@example.com", "password": "SecurePass123"},
        )
        response = client.get("/")
        assert response.status_code == 200
        assert "Welcome back" in response.text
