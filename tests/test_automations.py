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
            "cron_expression": "0 4 * * *",
            "next_run_at": "2025-12-01T04:00:00Z",
            "last_run_at": "2025-11-30T04:00:00Z",
        }
        update = client.patch(f"/api/automations/{automation_id}", json=payload)
        assert update.status_code == 200
        body = update.json()
        assert body["name"] == payload["name"]
        assert body["cron_expression"] == payload["cron_expression"]
        assert body["next_run_at"].startswith("2025-12-01T04:00:00")

        html = client.get("/automation").text
        assert "Lifecycle automation (patched)" in html
        assert "0 4 * * *" in html


def test_scheduled_automation_rejects_invalid_cron():
    with TestClient(app) as client:
        scheduled = client.get("/api/automations", params={"kind": "scheduled"})
        assert scheduled.status_code == 200
        automation_id = scheduled.json()[0]["id"]

        response = client.patch(
            f"/api/automations/{automation_id}",
            json={"cron_expression": "invalid"},
        )
        assert response.status_code == 400
        detail = response.json().get("detail")
        assert "Cron expression" in detail


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


def test_event_automation_trigger_validation():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        automation_id = events.json()[0]["id"]

        response = client.patch(
            f"/api/automations/{automation_id}",
            json={"trigger": "Unsupported"},
        )
        assert response.status_code == 400
        detail = response.json().get("detail")
        assert "trigger" in detail.lower()

        filters_response = client.patch(
            f"/api/automations/{automation_id}",
            json={
                "trigger_filters": {
                    "match": "any",
                    "conditions": ["Unsupported"],
                }
            },
        )
        assert filters_response.status_code == 400
        filter_detail = filters_response.json().get("detail")
        assert "trigger" in filter_detail.lower()


def test_update_event_automation_trigger_filters():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        event_items = events.json()
        target = next(
            item for item in event_items if item["name"] == "Incident escalation"
        )
        automation_id = target["id"]

        payload = {
            "trigger_filters": {
                "match": "all",
                "conditions": [
                    "Ticket Created",
                    "Ticket Status Changed",
                ],
            }
        }

        update = client.patch(
            f"/api/automations/{automation_id}",
            json=payload,
        )
        assert update.status_code == 200
        body = update.json()
        assert body["trigger_filters"]["match"] == "all"
        assert body["trigger_filters"]["conditions"] == payload["trigger_filters"][
            "conditions"
        ]
        assert body["trigger"] is None

        html = client.get("/automation").text
        assert "ALL: Ticket Created, Ticket Status Changed" in html


def test_automation_edit_page_loads():
    with TestClient(app) as client:
        response = client.get("/api/automations")
        assert response.status_code == 200
        automations = response.json()
        assert automations, "Expected seeded automations"
        automation_id = automations[0]["id"]

        page = client.get(f"/automation/{automation_id}")
        assert page.status_code == 200
        html = page.text
        assert "automation-edit-page" in html
        assert "automation-editor__kind" in html
        assert "data-role=\"automation-edit-page\"" in html
