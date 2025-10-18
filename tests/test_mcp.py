from __future__ import annotations

import asyncio
from typing import Iterator, Tuple

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.tickets import ticket_store
from app.main import app


@pytest.fixture
def mcp_client(monkeypatch) -> Iterator[Tuple[TestClient, str]]:
    api_key = "test-mcp-key"
    get_settings.cache_clear()
    monkeypatch.setenv("TACTICAL_DESK_MCP_API_KEY", api_key)
    asyncio.run(ticket_store.reset())
    with TestClient(app) as client:
        yield client, api_key
    asyncio.run(ticket_store.reset())
    get_settings.cache_clear()
    monkeypatch.delenv("TACTICAL_DESK_MCP_API_KEY", raising=False)


def test_mcp_requires_configuration(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("TACTICAL_DESK_MCP_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.get("/api/mcp/resources", headers={"X-API-Key": "missing"})
    assert response.status_code == 503
    get_settings.cache_clear()


def test_mcp_rejects_invalid_api_key(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("TACTICAL_DESK_MCP_API_KEY", "valid-key")
    with TestClient(app) as client:
        response = client.get("/api/mcp/resources", headers={"X-API-Key": "invalid"})
    assert response.status_code == 401
    get_settings.cache_clear()
    monkeypatch.delenv("TACTICAL_DESK_MCP_API_KEY", raising=False)


def test_mcp_list_resources(mcp_client) -> None:
    client, api_key = mcp_client
    response = client.get("/api/mcp/resources", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    payload = response.json()
    assert any(item["slug"] == "organizations" for item in payload)


def test_mcp_create_and_fetch_organization(mcp_client) -> None:
    client, api_key = mcp_client
    create_response = client.post(
        "/api/mcp/execute",
        json={
            "resource": "organizations",
            "operation": "create",
            "payload": {
                "name": "MCP Org",
                "slug": "mcp-org",
                "description": "Created via MCP connector",
            },
        },
        headers={"X-API-Key": api_key},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["data"]["slug"] == "mcp-org"

    list_response = client.post(
        "/api/mcp/execute",
        json={
            "resource": "organizations",
            "operation": "list",
        },
        headers={"X-API-Key": api_key},
    )
    assert list_response.status_code == 200
    records = list_response.json()["data"]
    assert any(org["slug"] == "mcp-org" for org in records)


def test_mcp_ticket_workflow(mcp_client) -> None:
    client, api_key = mcp_client
    create_ticket = client.post(
        "/api/mcp/execute",
        json={
            "resource": "tickets",
            "operation": "create",
            "payload": {
                "subject": "MCP Ticket",
                "customer": "Example Corp",
                "customer_email": "customer@example.com",
                "status": "Open",
                "priority": "High",
                "team": "Tier 1",
                "assignment": "Unassigned",
                "queue": "General",
                "category": "Support",
                "summary": "Initial ticket created via MCP.",
            },
        },
        headers={"X-API-Key": api_key},
    )
    assert create_ticket.status_code == 200
    ticket_payload = create_ticket.json()
    ticket_id = ticket_payload["meta"]["id"]
    assert ticket_payload["data"]["subject"] == "MCP Ticket"

    reply_response = client.post(
        "/api/mcp/execute",
        json={
            "resource": "tickets",
            "operation": "append-reply",
            "identifier": ticket_id,
            "payload": {
                "actor": "ChatGPT Agent",
                "channel": "Portal reply",
                "summary": "Follow-up",
                "message": "Ticket reply sent via MCP connector.",
            },
        },
        headers={"X-API-Key": api_key},
    )
    assert reply_response.status_code == 200
    reply_body = reply_response.json()["data"]
    assert reply_body["summary"] == "Follow-up"

    fetch_response = client.post(
        "/api/mcp/execute",
        json={
            "resource": "tickets",
            "operation": "retrieve",
            "identifier": ticket_id,
        },
        headers={"X-API-Key": api_key},
    )
    assert fetch_response.status_code == 200
    fetched_ticket = fetch_response.json()["data"]
    assert fetched_ticket["id"] == ticket_id
    assert fetched_ticket["subject"] == "MCP Ticket"
