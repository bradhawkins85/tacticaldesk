import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def playbook_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "playbooks.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()


def test_seeded_playbooks_available(playbook_db: Path):
    with TestClient(app) as client:
        response = client.get("/api/playbooks")
        assert response.status_code == 200
        payload = response.json()
        names = {item["name"] for item in payload}
        assert "Run secure update" in names
        assert "Quarterly patch audit" in names

        html_response = client.get("/admin/playbooks")
        assert html_response.status_code == 200
        html = html_response.text
        assert "Playbook catalogue" in html
        assert "Run secure update" in html
        assert "Quarterly patch audit" in html


def test_create_update_and_delete_playbook(playbook_db: Path):
    with TestClient(app) as client:
        create_payload = {
            "name": "Disaster Recovery",
            "slug": "disaster-recovery",
            "description": "Coordinate failover runbooks.",
        }
        create_response = client.post("/api/playbooks", json=create_payload)
        assert create_response.status_code == 201
        created = create_response.json()
        playbook_id = created["id"]
        assert created["automation_count"] == 0

        # Link a synthetic automation to ensure rename cascades.
        connection = sqlite3.connect(playbook_db)
        try:
            connection.execute(
                """
                INSERT INTO automations (
                    name,
                    description,
                    playbook,
                    kind,
                    cadence,
                    trigger,
                    status,
                    action_label,
                    action_endpoint,
                    action_output_selector
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "DR nightly validation",
                    "Exercise disaster recovery documentation.",
                    "Disaster Recovery",
                    "scheduled",
                    "Every night",
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        delete_conflict = client.delete(f"/api/playbooks/{playbook_id}")
        assert delete_conflict.status_code == 409
        assert "automations" in delete_conflict.json()["detail"].lower()

        update_payload = {
            "name": "Disaster Recovery Prime",
            "slug": "disaster-recovery-prime",
        }
        update_response = client.patch(
            f"/api/playbooks/{playbook_id}", json=update_payload
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["name"] == "Disaster Recovery Prime"
        assert updated["slug"] == "disaster-recovery-prime"

        # Ensure automations were updated to the new playbook name.
        connection = sqlite3.connect(playbook_db)
        try:
            cursor = connection.execute(
                "SELECT playbook FROM automations WHERE name = ?",
                ("DR nightly validation",),
            )
            row = cursor.fetchone()
        finally:
            connection.close()
        assert row is not None
        assert row[0] == "Disaster Recovery Prime"

        # Remove automation link so deletion succeeds.
        connection = sqlite3.connect(playbook_db)
        try:
            connection.execute(
                "DELETE FROM automations WHERE name = ?",
                ("DR nightly validation",),
            )
            connection.commit()
        finally:
            connection.close()

        delete_response = client.delete(f"/api/playbooks/{playbook_id}")
        assert delete_response.status_code == 204

        # Ensure playbook no longer returned by API.
        list_response = client.get("/api/playbooks")
        assert list_response.status_code == 200
        remaining_names = {item["name"] for item in list_response.json()}
        assert "Disaster Recovery" not in remaining_names
        assert "Disaster Recovery Prime" not in remaining_names
