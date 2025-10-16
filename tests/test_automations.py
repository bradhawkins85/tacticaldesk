import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def automation_db(tmp_path, monkeypatch):
    db_path = tmp_path / "automations.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_seeded_automations_visible_in_api_and_ui():
    with TestClient(app) as client:
        response = client.get("/api/automations")
        assert response.status_code == 200
        payload = response.json()
        names = {item["name"] for item in payload}
        assert "Lifecycle automation" in names
        assert "Incident escalation" in names

        html_response = client.get("/automation")
        assert html_response.status_code == 200
        html = html_response.text
        assert "Automation Control Tower" in html
        assert "data-automation-id" in html
        assert "Lifecycle automation" in html
        assert "Incident escalation" in html


def test_update_scheduled_automation():
    with TestClient(app) as client:
        scheduled = client.get("/api/automations", params={"kind": "scheduled"})
        assert scheduled.status_code == 200
        scheduled_items = scheduled.json()
        target = next(item for item in scheduled_items if item["name"] == "Lifecycle automation")
        automation_id = target["id"]

        payload = {
            "name": "Lifecycle automation (patched)",
            "description": "Updated secure update automation.",
            "cadence": "Daily at 04:00 UTC",
            "next_run_at": "2025-12-01T04:00:00Z",
            "last_run_at": "2025-11-30T04:00:00Z",
        }
        update = client.patch(f"/api/automations/{automation_id}", json=payload)
        assert update.status_code == 200
        body = update.json()
        assert body["name"] == payload["name"]
        assert body["cadence"] == payload["cadence"]
        assert body["next_run_at"].startswith("2025-12-01T04:00:00")

        html = client.get("/automation").text
        assert "Lifecycle automation (patched)" in html
        assert "Daily at 04:00 UTC" in html


def test_update_event_automation_status():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        event_items = events.json()
        target = next(item for item in event_items if item["name"] == "Incident escalation")
        automation_id = target["id"]

        payload = {
            "status": "Monitoring",
            "last_trigger_at": "2025-12-05T09:30:00Z",
        }
        update = client.patch(f"/api/automations/{automation_id}", json=payload)
        assert update.status_code == 200
        body = update.json()
        assert body["status"] == "Monitoring"
        assert body["last_trigger_at"].startswith("2025-12-05T09:30:00")

        html = client.get("/automation").text
        assert "Monitoring" in html
        assert "2025" in html
