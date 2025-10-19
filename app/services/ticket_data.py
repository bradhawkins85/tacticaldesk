from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from app.core.tickets import ticket_store


def slugify_label(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return "-".join(tokens) or "general"


def describe_age(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "Just now"
    minutes = total_seconds // 60
    if minutes < 1:
        return "Less than a minute ago"
    hours = minutes // 60
    days = hours // 24
    weeks = days // 7
    if weeks >= 1:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    if days >= 1:
        return f"{days} day{'s' if days != 1 else ''} ago"
    if hours >= 1:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    return f"{minutes} minute{'s' if minutes != 1 else ''} ago"


def enrich_ticket_record(
    ticket: dict[str, object], now_utc: datetime
) -> dict[str, object]:
    base = dict(ticket)
    last_reply_dt = base.get("last_reply_dt")
    if isinstance(last_reply_dt, datetime):
        if last_reply_dt.tzinfo is None:
            last_reply_dt = last_reply_dt.replace(tzinfo=timezone.utc)
    else:
        last_reply_dt = now_utc
    base["last_reply_dt"] = last_reply_dt
    last_reply_iso = (
        last_reply_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    age_delta = now_utc - last_reply_dt

    status_value = str(base.get("status", ""))
    priority_value = str(base.get("priority", ""))
    assignment_value = str(base.get("assignment", ""))
    queue_value = str(base.get("queue", ""))
    team_value = str(base.get("team", ""))
    category_value = str(base.get("category", ""))

    filter_tokens = {
        "all",
        f"status-{slugify_label(status_value)}",
        f"priority-{slugify_label(priority_value)}",
        f"assignment-{slugify_label(assignment_value)}",
        f"queue-{slugify_label(queue_value)}",
        f"team-{slugify_label(team_value)}",
        f"category-{slugify_label(category_value)}",
    }
    if base.get("is_starred"):
        filter_tokens.add("flagged")
    if base.get("assets_visible"):
        filter_tokens.add("assets-visible")

    labels = base.get("labels") or []
    if not isinstance(labels, list):
        labels = []
    base["labels"] = labels
    if "channel" not in base:
        base["channel"] = "Portal"

    enriched = {
        **base,
        "last_reply_iso": last_reply_iso,
        "age_display": describe_age(age_delta),
        "filter_tokens": sorted(filter_tokens),
        "status_token": slugify_label(status_value),
        "priority_token": slugify_label(priority_value),
        "assignment_token": slugify_label(assignment_value),
    }
    return enriched


def build_ticket_records(now_utc: datetime) -> list[dict[str, object]]:
    """Return the static ticket catalogue used to seed the workspace."""

    seed_tickets: list[dict[str, object]] = [
        {
            "id": "TD-4821",
            "subject": "Query for Opensource Project",
            "customer": "Quest Logistics",
            "customer_email": "quest.labs@example.com",
            "status": "Open",
            "priority": "High",
            "team": "Tier 1",
            "category": "Support",
            "assignment": "Unassigned",
            "queue": "Critical response",
            "channel": "Email",
            "last_reply_dt": now_utc - timedelta(days=2, hours=6),
            "labels": ["SLA watch"],
            "is_starred": True,
            "assets_visible": True,
            "created_at_dt": now_utc - timedelta(days=3, hours=2),
            "due_at_dt": now_utc + timedelta(hours=6),
            "summary": "Investigating packet loss impacting the VPN tunnel between HQ and warehouse sites.",
            "history": [
                {
                    "actor": "Quest Logistics · Alicia Patel",
                    "direction": "inbound",
                    "channel": "Email",
                    "summary": "Client reports recurring VPN tunnel flaps on Cisco ASA.",
                    "body": (
                        "Hi Tactical Desk team,\n\n"
                        "We're continuing to see the HQ ↔ warehouse VPN tunnel drop every few hours. "
                        "The ASA event log shows keepalive failures. Can you confirm the monitoring profile "
                        "is still applied?"
                    ),
                    "timestamp_dt": now_utc - timedelta(days=2, hours=6),
                },
                {
                    "actor": "Super Admin",
                    "direction": "outbound",
                    "channel": "Portal reply",
                    "summary": "Requested logs and scheduled joint troubleshooting session.",
                    "body": (
                        "Thanks Alicia, we're correlating the drops with ISP latency spikes. "
                        "Please upload the latest ASA tech support bundle. We also reserved a remote session "
                        "for tomorrow 09:00 AM your time."
                    ),
                    "timestamp_dt": now_utc - timedelta(days=1, hours=18),
                },
                {
                    "actor": "Quest Logistics · Alicia Patel",
                    "direction": "inbound",
                    "channel": "Portal reply",
                    "summary": "Uploaded diagnostics and confirmed maintenance window availability.",
                    "body": (
                        "Bundle uploaded here: https://share.example.com/asa-bundle.zip\n"
                        "Confirmed maintenance window tomorrow 09:00 AM."
                    ),
                    "timestamp_dt": now_utc - timedelta(days=1, hours=3),
                },
            ],
            "watchers": ["network.ops@example.com", "tier1@tacticaldesk.example"],
        },
        {
            "id": "TD-4820",
            "subject": "Welcome to U Desk",
            "customer": "Demo Customer",
            "customer_email": "customer@demo.com",
            "status": "Pending",
            "priority": "Medium",
            "team": "Customer success",
            "category": "Onboarding",
            "assignment": "Shared",
            "queue": "Service requests",
            "channel": "Portal",
            "last_reply_dt": now_utc - timedelta(days=3, hours=4),
            "labels": ["First response"],
            "is_starred": False,
            "assets_visible": False,
            "created_at_dt": now_utc - timedelta(days=4, hours=5),
            "due_at_dt": now_utc + timedelta(days=1, hours=2),
            "summary": "Coordinating the onboarding runbook and provisioning initial workspace access.",
            "history": [
                {
                    "actor": "Demo Customer · Maria Gomez",
                    "direction": "inbound",
                    "channel": "Portal reply",
                    "summary": "Shared the user list and SSO metadata for onboarding.",
                    "body": (
                        "Attached the CSV with our first 25 agents. The Azure AD SAML metadata is also uploaded. "
                        "Let us know once SSO is staged so we can test."
                    ),
                    "timestamp_dt": now_utc - timedelta(days=3, hours=4),
                },
                {
                    "actor": "Customer Success · Liam Chen",
                    "direction": "outbound",
                    "channel": "Email",
                    "summary": "Confirmed receipt and outlined deployment milestones.",
                    "body": (
                        "Thanks Maria! We'll import the users today and configure SSO. "
                        "Expect an update with testing credentials by tomorrow noon."
                    ),
                    "timestamp_dt": now_utc - timedelta(days=2, hours=1),
                },
                {
                    "actor": "Demo Customer · Maria Gomez",
                    "direction": "inbound",
                    "channel": "Email",
                    "summary": "Provided branding assets and follow-up questions.",
                    "body": (
                        "Branding assets uploaded here: https://share.example.com/branding-kit.zip\n"
                        "Can you confirm the knowledge base migration schedule?"
                    ),
                    "timestamp_dt": now_utc - timedelta(days=1, hours=5),
                },
            ],
            "watchers": ["onboarding@tacticaldesk.example"],
        },
        {
            "id": "TD-4819",
            "subject": "Escalated: Endpoint isolation automation stalled",
            "customer": "Blue Harbor Finance",
            "customer_email": "it@blueharbor.example",
            "status": "Answered",
            "priority": "Urgent",
            "team": "Security operations",
            "category": "Incident response",
            "assignment": "My tickets",
            "queue": "Security incidents",
            "channel": "Phone",
            "last_reply_dt": now_utc - timedelta(hours=6),
            "labels": ["Escalated", "Automation"],
            "is_starred": True,
            "assets_visible": True,
            "created_at_dt": now_utc - timedelta(hours=12),
            "due_at_dt": now_utc + timedelta(hours=3),
            "summary": "Endpoint isolation automation failed due to outdated agent version on CFO laptop.",
            "history": [
                {
                    "actor": "Security Operations · Priya Singh",
                    "direction": "outbound",
                    "channel": "Phone",
                    "summary": "Initiated isolation workflow and observed agent failure logs.",
                    "body": (
                        "Isolation automation attempted at 08:42 UTC but failed with agent compatibility error. "
                        "Manual isolation required; coordinating with local support."
                    ),
                    "timestamp_dt": now_utc - timedelta(hours=11, minutes=30),
                },
                {
                    "actor": "Blue Harbor Finance · Michael Torres",
                    "direction": "inbound",
                    "channel": "Phone",
                    "summary": "Confirmed device availability and approved manual intervention.",
                    "body": (
                        "Laptop is on and connected to VPN. Security team has approval to perform manual isolation."
                    ),
                    "timestamp_dt": now_utc - timedelta(hours=10, minutes=5),
                },
                {
                    "actor": "Security Operations · Priya Singh",
                    "direction": "outbound",
                    "channel": "Portal reply",
                    "summary": "Performed manual isolation and scheduled agent upgrade.",
                    "body": (
                        "Device isolated manually. Scheduled agent upgrade for tonight 23:00 UTC. Monitoring for further alerts."
                    ),
                    "timestamp_dt": now_utc - timedelta(hours=6),
                },
            ],
            "watchers": ["soc.lead@tacticaldesk.example"],
        },
        {
            "id": "TD-4818",
            "subject": "Infrastructure: Weekly maintenance summary",
            "customer": "Internal",
            "customer_email": "infra@tacticaldesk.example",
            "status": "Resolved",
            "priority": "Low",
            "team": "Infrastructure",
            "category": "Maintenance",
            "assignment": "Shared",
            "queue": "Internal",
            "channel": "Automation",
            "last_reply_dt": now_utc - timedelta(days=1),
            "labels": ["Automation", "Report"],
            "is_starred": False,
            "assets_visible": False,
            "created_at_dt": now_utc - timedelta(days=1, hours=6),
            "due_at_dt": now_utc - timedelta(hours=2),
            "summary": "Weekly automation summary with patch compliance metrics and service restarts.",
            "history": [
                {
                    "actor": "Automation · Weekly maintenance digest",
                    "direction": "outbound",
                    "channel": "Automation",
                    "summary": "Posted the weekly maintenance summary including patch results.",
                    "body": (
                        "All production clusters patched successfully. 2 staging nodes pending reboot. "
                        "Services restarted on schedule with no detected incidents."
                    ),
                    "timestamp_dt": now_utc - timedelta(days=1, hours=6),
                },
                {
                    "actor": "Infrastructure · Alex Morgan",
                    "direction": "outbound",
                    "channel": "Portal reply",
                    "summary": "Confirmed pending staging node reboots scheduled tonight.",
                    "body": (
                        "Two staging nodes require manual reboot tonight 22:00 UTC. Change request approved."
                    ),
                    "timestamp_dt": now_utc - timedelta(hours=20),
                },
            ],
            "watchers": ["infra.manager@tacticaldesk.example"],
        },
        {
            "id": "TD-4817",
            "subject": "Customer escalation: Billing sync discrepancies",
            "customer": "Northwind Retail",
            "customer_email": "ops@northwind.example",
            "status": "Open",
            "priority": "High",
            "team": "Tier 2",
            "category": "Billing",
            "assignment": "Unassigned",
            "queue": "Customer escalations",
            "channel": "Email",
            "last_reply_dt": now_utc - timedelta(days=1, hours=2),
            "labels": ["Escalated", "Finance"],
            "is_starred": True,
            "assets_visible": True,
            "created_at_dt": now_utc - timedelta(days=1, hours=6),
            "due_at_dt": now_utc + timedelta(hours=12),
            "summary": "Monthly billing sync is missing credit adjustments for April invoices.",
            "history": [
                {
                    "actor": "Northwind Retail · Sara Lee",
                    "direction": "inbound",
                    "channel": "Email",
                    "summary": "Missing credit adjustments in billing sync export.",
                    "body": (
                        "April invoices do not include credit adjustments from the ERP. "
                        "We need corrected exports before finance closes the books."
                    ),
                    "timestamp_dt": now_utc - timedelta(days=1, hours=2),
                },
                {
                    "actor": "Billing Team · Omar Haddad",
                    "direction": "outbound",
                    "channel": "Portal reply",
                    "summary": "Investigating ERP connector logs and pending retry job.",
                    "body": (
                        "Connector logs show authentication failures on April 28. "
                        "Regenerated API credentials and queued a manual sync for review."
                    ),
                    "timestamp_dt": now_utc - timedelta(hours=18),
                },
            ],
            "watchers": ["finance.escalations@tacticaldesk.example"],
        },
    ]
    return seed_tickets


async def fetch_ticket_records(now_utc: datetime) -> list[dict[str, object]]:
    """Retrieve ticket records merged with any runtime overrides."""

    seed_tickets = build_ticket_records(now_utc)
    return await ticket_store.apply_overrides(seed_tickets)
