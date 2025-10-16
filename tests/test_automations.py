import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.automation_dispatcher import automation_dispatcher
from app.core.config import get_settings
from app.core.tickets import ticket_store
from app.main import app


@pytest.fixture(autouse=True)
def automation_db(tmp_path, monkeypatch):
    db_path = tmp_path / "automations.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_ticket_overrides():
    asyncio.run(ticket_store.reset())
    yield
    asyncio.run(ticket_store.reset())


@pytest.fixture(autouse=True)
def reset_automation_events():
    asyncio.run(automation_dispatcher.reset())
    yield
    asyncio.run(automation_dispatcher.reset())


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


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


def test_update_scheduled_automation_with_trigger_filters():
    with TestClient(app) as client:
        scheduled = client.get("/api/automations", params={"kind": "scheduled"})
        assert scheduled.status_code == 200
        scheduled_items = scheduled.json()
        target = next(item for item in scheduled_items if item["name"] == "Patch window compliance")
        automation_id = target["id"]

        payload = {
            "trigger_filters": {
                "match": "any",
                "conditions": [
                    {
                        "type": "Assigned to",
                        "operator": "equals",
                        "value": "Service Desk",
                    }
                ],
            }
        }

        response = client.patch(
            f"/api/automations/{automation_id}",
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["trigger_filters"]["conditions"][0]["type"] == "Assigned to"
        assert body["trigger_filters"]["conditions"][0]["value"] == "Service Desk"

        html = client.get(f"/automation/scheduled/{automation_id}")
        assert html.status_code == 200
        assert "Assigned to" in html.text


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
                    {"type": "Ticket Created"},
                    {
                        "type": "Ticket Status Changed From",
                        "operator": "equals",
                        "value": "Open",
                    },
                    {
                        "type": "Assigned SLA",
                        "operator": "equals",
                        "value": "Gold",
                    },
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

        def _normalize_conditions(raw_conditions):
            normalized = []
            for condition in raw_conditions:
                normalized.append(
                    {key: value for key, value in condition.items() if value is not None}
                )
            return normalized

        assert _normalize_conditions(body["trigger_filters"]["conditions"]) == payload[
            "trigger_filters"
        ]["conditions"]
        assert body["trigger"] is None

        html = client.get("/automation").text
        assert "ALL" in html
        assert "Ticket Created" in html
        assert "Ticket Status Changed From" in html
        assert "Equals" in html
        assert "Open" in html


def test_update_event_automation_ticket_actions():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        event_items = events.json()
        target = next(
            item for item in event_items if item["name"] == "Incident escalation"
        )
        automation_id = target["id"]

        payload = {
            "ticket_actions": [
                {
                    "action": "add-public-comment",
                    "value": "Notify stakeholders within 1 hour.",
                },
                {"action": "change-status", "value": "In Progress"},
            ]
        }

        response = client.patch(
            f"/api/automations/{automation_id}",
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["ticket_actions"]) == 2
        assert body["ticket_actions"][0]["action"] == "add-public-comment"
        assert (
            body["ticket_actions"][0]["value"]
            == "Notify stakeholders within 1 hour."
        )

        html = client.get(f"/automation/event/{automation_id}")
        assert html.status_code == 200
        assert "add-public-comment" in html.text
        assert "Notify stakeholders within 1 hour." in html.text

        refreshed = client.get("/api/automations", params={"kind": "event"})
        assert refreshed.status_code == 200
        updated = next(item for item in refreshed.json() if item["id"] == automation_id)
        assert len(updated["ticket_actions"]) == 2
        assert updated["ticket_actions"][1]["action"] == "change-status"


def test_event_automation_rejects_invalid_ticket_actions():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        automation_id = events.json()[0]["id"]

        response = client.patch(
            f"/api/automations/{automation_id}",
            json={
                "ticket_actions": [
                    {"action": "unsupported-action", "value": "Test"},
                ]
            },
        )
        assert response.status_code == 400
        detail = response.json().get("detail", "")
        assert "action" in detail.lower()


def test_event_automation_template_variables_rendered_in_ui():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        automations = events.json()
        assert automations, "Expected seeded automations"
        automation_id = automations[0]["id"]

        page = client.get(f"/automation/event/{automation_id}")
        assert page.status_code == 200
        html = page.text
        assert "Available template variables" in html
        assert "ticket.subject" in html
        assert "ticket.previous_status" in html
        assert "event.triggered_at" in html


def test_ticket_action_template_variables_render_in_dispatch_payload():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        event_items = events.json()
        target = next(item for item in event_items if item["name"] == "Incident escalation")
        automation_id = target["id"]

        configure = client.patch(
            f"/api/automations/{automation_id}",
            json={
                "trigger_filters": {
                    "match": "all",
                    "conditions": [
                        {"type": "Ticket Status Changed"},
                    ],
                },
                "ticket_actions": [
                    {
                        "action": "add-public-comment",
                        "value": (
                            "Ticket {{ ticket.id }} for {{ ticket.customer }} is now "
                            "{{ ticket.status }} (was {{ ticket.previous_status }})."
                        ),
                    }
                ],
            },
        )
        assert configure.status_code == 200

        form_payload = {
            "subject": "Database availability incident",
            "customer": "Quest Logistics",
            "customer_email": "quest.ops@example.com",
            "status": "In Progress",
            "priority": "High",
            "team": "Tier 2",
            "assignment": "Super Admin",
            "queue": "Critical response",
            "category": "Support",
            "summary": "Automated remediation playbook executing runtime checks.",
        }

        response = client.post(
            "/tickets/TD-4821",
            data=form_payload,
            follow_redirects=False,
        )
        assert response.status_code == 303

        events = asyncio.run(automation_dispatcher.list_events())
        triggered = [
            event
            for event in events
            if event.event_type == "Automation Triggered"
            and event.payload.get("automation_id") == automation_id
        ]
        assert triggered, "Expected Automation Triggered event to be recorded"

        payload = triggered[-1].payload
        assert payload["trigger_event"] == "Ticket Status Changed"
        variables = payload["variables"]
        assert variables["ticket.subject"] == form_payload["subject"]
        assert variables["ticket.status"] == form_payload["status"]
        assert "ticket.previous_status" in variables
        actions = payload["actions"]
        assert actions, "Expected rendered ticket actions"
        rendered_value = actions[0]["value"]
        assert "TD-4821" in rendered_value
        assert form_payload["status"] in rendered_value
        assert variables["ticket.previous_status"] in rendered_value
        assert payload["triggered_at"].endswith("Z")


def test_ticket_update_triggers_event_automation():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        event_items = events.json()
        target = next(
            item for item in event_items if item["name"] == "Incident escalation"
        )
        automation_id = target["id"]
        original_last_trigger = target.get("last_trigger_at")

        configure_response = client.patch(
            f"/api/automations/{automation_id}",
            json={
                "trigger_filters": {
                    "match": "all",
                    "conditions": [
                        {"type": "Ticket Updated by Technician"},
                    ],
                }
            },
        )
        assert configure_response.status_code == 200

        form_payload = {
            "subject": "Query for Opensource Project - follow up",
            "customer": "Quest Logistics",
            "customer_email": "quest.labs@example.com",
            "status": "Open",
            "priority": "High",
            "team": "Tier 1",
            "assignment": "Unassigned",
            "queue": "Critical response",
            "category": "Support",
            "summary": "Technician posted updated troubleshooting notes.",
        }

        ticket_response = client.post(
            "/tickets/TD-4821",
            data=form_payload,
            follow_redirects=False,
        )
        assert ticket_response.status_code == 303

        refreshed = client.get("/api/automations", params={"kind": "event"})
        assert refreshed.status_code == 200
        updated = next(item for item in refreshed.json() if item["id"] == automation_id)
        assert updated["last_trigger_at"] is not None
        assert updated["last_trigger_at"] != original_last_trigger

        parsed_original = _parse_iso8601(original_last_trigger)
        parsed_updated = _parse_iso8601(updated["last_trigger_at"])
        assert parsed_updated is not None
        if parsed_original is not None:
            assert parsed_updated > parsed_original


def test_manual_run_endpoint_updates_last_run():
    with TestClient(app) as client:
        scheduled = client.get("/api/automations", params={"kind": "scheduled"})
        assert scheduled.status_code == 200
        scheduled_items = scheduled.json()
        target = next(item for item in scheduled_items if item["name"] == "Patch window compliance")
        automation_id = target["id"]
        original_last_run = target.get("last_run_at")

        run_response = client.post(f"/api/automations/{automation_id}/run")
        assert run_response.status_code == 200
        payload = run_response.json()
        assert payload["detail"].startswith("Queued manual execution")
        assert "last_run_at" in payload

        refreshed = client.get("/api/automations", params={"kind": "scheduled"})
        assert refreshed.status_code == 200
        updated = next(item for item in refreshed.json() if item["id"] == automation_id)
        assert updated["last_run_at"] is not None
        assert updated["last_run_at"].startswith(payload["last_run_at"][:19])
        if original_last_run:
            assert updated["last_run_at"] != original_last_run


def test_run_endpoint_rejects_event_automations():
    with TestClient(app) as client:
        events = client.get("/api/automations", params={"kind": "event"})
        assert events.status_code == 200
        target = events.json()[0]
        response = client.post(f"/api/automations/{target['id']}/run")
        assert response.status_code == 400
        assert "scheduled" in response.json().get("detail", "").lower()


def test_delete_automation_removes_from_api_and_ui():
    with TestClient(app) as client:
        automations = client.get("/api/automations")
        assert automations.status_code == 200
        target = next(item for item in automations.json() if item["name"] == "Backup integrity")
        automation_id = target["id"]

        delete_response = client.delete(f"/api/automations/{automation_id}")
        assert delete_response.status_code == 204

        remaining = client.get("/api/automations")
        assert remaining.status_code == 200
        remaining_ids = {item["id"] for item in remaining.json()}
        assert automation_id not in remaining_ids

        html = client.get("/automation").text
        assert "Backup integrity" not in html


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
