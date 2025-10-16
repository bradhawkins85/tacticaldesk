from __future__ import annotations

from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs
import re

from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.routers import auth as auth_router
from app.api.routers import automations as automations_router
from app.api.routers import integrations as integrations_router
from app.api.routers import maintenance as maintenance_router
from app.api.routers import organizations as organizations_router
from app.api.routers import webhooks as webhooks_router
from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine, get_session
from app.core.tickets import ticket_store
from app.models import (
    Automation,
    Contact,
    IntegrationModule,
    Organization,
    User,
    WebhookDelivery,
    utcnow,
)
from app.schemas import OrganizationCreate, OrganizationUpdate, TicketUpdate, WebhookStatus
from pydantic import ValidationError

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "web" / "templates"
STATIC_DIR = BASE_DIR / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_engine()
    yield
    await dispose_engine()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
app.include_router(auth_router.router)
app.include_router(automations_router.router)
app.include_router(integrations_router.router)
app.include_router(maintenance_router.router)
app.include_router(organizations_router.router)
app.include_router(webhooks_router.router)


def slugify(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return "-".join(tokens) or "general"


DEFAULT_AUTOMATION_OUTPUT_SELECTOR = "#automation-update-output"


TICKET_FORM_FIELDS = (
    "subject",
    "customer",
    "customer_email",
    "status",
    "priority",
    "team",
    "assignment",
    "queue",
    "category",
    "summary",
)


def _automation_datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _automation_to_view_model(automation: Automation) -> dict[str, object]:
    action = None
    if automation.action_label and automation.action_endpoint:
        action = {
            "label": automation.action_label,
            "endpoint": automation.action_endpoint,
            "output_selector": automation.action_output_selector
            or DEFAULT_AUTOMATION_OUTPUT_SELECTOR,
        }

    return {
        "id": automation.id,
        "name": automation.name,
        "description": automation.description or "",
        "playbook": automation.playbook,
        "kind": automation.kind,
        "cadence": automation.cadence,
        "trigger": automation.trigger,
        "status": automation.status,
        "next_run_iso": _automation_datetime_to_iso(automation.next_run_at),
        "last_run_iso": _automation_datetime_to_iso(automation.last_run_at),
        "last_trigger_iso": _automation_datetime_to_iso(automation.last_trigger_at),
        "action": action,
        "action_label": automation.action_label,
        "action_endpoint": automation.action_endpoint,
        "action_output_selector": automation.action_output_selector
        or DEFAULT_AUTOMATION_OUTPUT_SELECTOR,
    }


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


def _format_field_label(field_name: str) -> str:
    return field_name.replace("_", " ").capitalize()


def _format_ticket_validation_errors(error: ValidationError) -> list[str]:
    messages: list[str] = []
    for entry in error.errors():
        field = str(entry.get("loc", [""])[-1])
        label = _format_field_label(field)
        error_type = entry.get("type", "")
        if error_type == "value_error.email":
            messages.append(f"{label} must be a valid email address.")
            continue
        if error_type == "value_error.any_str.min_length":
            messages.append(f"{label} cannot be empty.")
            continue
        if error_type == "value_error.any_str.max_length":
            limit = entry.get("ctx", {}).get("limit_value")
            if limit is not None:
                messages.append(f"{label} must be at most {limit} characters.")
            else:
                messages.append(f"{label} is too long.")
            continue
        messages.append(f"{label}: {entry.get('msg', 'Invalid value')}")
    return messages


async def _extract_ticket_form_data(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    media_type = content_type.split(";")[0].strip().lower()
    if media_type == "application/x-www-form-urlencoded":
        body = await request.body()
        charset = "utf-8"
        if "charset=" in content_type.lower():
            charset = content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            decoded_body = body.decode(charset)
        except LookupError:
            decoded_body = body.decode("utf-8", errors="ignore")
        parsed = parse_qs(decoded_body, keep_blank_values=True)
        return {field: parsed.get(field, [""])[0] for field in TICKET_FORM_FIELDS}

    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported form submission type.",
        ) from exc
    return {field: (form.get(field) or "") for field in TICKET_FORM_FIELDS}


async def _prepare_ticket_detail_context(
    request: Request,
    now_utc: datetime,
    *,
    ticket_id: str,
    form_data: dict[str, str] | None = None,
    form_errors: list[str] | None = None,
    saved: bool = False,
) -> dict[str, object]:
    seed_tickets = build_ticket_records(now_utc)
    seed_tickets = await ticket_store.apply_overrides(seed_tickets)

    ticket_lookup = {ticket["id"]: ticket for ticket in seed_tickets}
    ticket = ticket_lookup.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    display_ticket = dict(ticket)
    if form_data:
        for field in TICKET_FORM_FIELDS:
            if field in form_data:
                display_ticket[field] = form_data[field]

    created_at_dt = display_ticket["created_at_dt"]
    if created_at_dt.tzinfo is None:
        created_at_dt = created_at_dt.replace(tzinfo=timezone.utc)
    created_at_iso = created_at_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    updated_source = display_ticket.get("metadata_updated_at_dt") or display_ticket["last_reply_dt"]
    if updated_source.tzinfo is None:
        updated_source = updated_source.replace(tzinfo=timezone.utc)
    updated_at_iso = (
        updated_source.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    due_at_iso = None
    due_at_dt = display_ticket.get("due_at_dt")
    if isinstance(due_at_dt, datetime):
        if due_at_dt.tzinfo is None:
            due_at_dt = due_at_dt.replace(tzinfo=timezone.utc)
        due_at_iso = due_at_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    history_entries: list[dict[str, object]] = []
    for entry in display_ticket.get("history", []):
        entry_copy = dict(entry)
        timestamp_dt = entry_copy.get("timestamp_dt")
        if isinstance(timestamp_dt, datetime):
            if timestamp_dt.tzinfo is None:
                timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
            entry_copy["timestamp_iso"] = (
                timestamp_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        history_entries.append(entry_copy)

    display_ticket.update(
        {
            "created_at_iso": created_at_iso,
            "updated_at_iso": updated_at_iso,
            "due_at_iso": due_at_iso,
            "history": history_entries,
        }
    )

    status_options = sorted({record["status"] for record in seed_tickets})
    priority_options = sorted({record["priority"] for record in seed_tickets})
    team_options = sorted({record["team"] for record in seed_tickets})
    assignment_options = sorted({record["assignment"] for record in seed_tickets})
    queue_options = sorted({record["queue"] for record in seed_tickets})

    return {
        "request": request,
        "page_title": f"{display_ticket['id']} · {display_ticket['subject']}",
        "page_subtitle": (
            "Review ticket context, conversation history, and craft a secure reply."
        ),
        "ticket": display_ticket,
        "ticket_status_options": status_options,
        "ticket_priority_options": priority_options,
        "ticket_team_options": team_options,
        "ticket_assignment_options": assignment_options,
        "ticket_queue_options": queue_options,
        "active_nav": "tickets",
        "form_errors": form_errors or [],
        "form_saved": saved,
    }


def build_ticket_records(now_utc: datetime) -> list[dict[str, object]]:
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
            "summary": "Coordinating the onboarding playbook and provisioning initial workspace access.",
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
                        "Thanks Maria! We'll import the agent roster today and target SSO testing by Friday. "
                        "You'll receive calendar invites for the onboarding workshops shortly."
                    ),
                    "timestamp_dt": now_utc - timedelta(days=2, hours=20),
                },
            ],
            "watchers": ["onboarding@tacticaldesk.example"],
        },
        {
            "id": "TD-4819",
            "subject": "MFA reset follow-up",
            "customer": "Northwind IT",
            "customer_email": "support@northwind.example",
            "status": "Answered",
            "priority": "Low",
            "team": "Tier 2",
            "category": "Security",
            "assignment": "My tickets",
            "queue": "Critical response",
            "channel": "Chat",
            "last_reply_dt": now_utc - timedelta(hours=5, minutes=30),
            "labels": ["Security"],
            "is_starred": False,
            "assets_visible": True,
            "created_at_dt": now_utc - timedelta(days=1, hours=2),
            "due_at_dt": now_utc + timedelta(hours=10),
            "summary": "Verifying conditional access baseline after forced MFA reset for executive accounts.",
            "history": [
                {
                    "actor": "Northwind IT · Calvin Shaw",
                    "direction": "inbound",
                    "channel": "Chat",
                    "summary": "Requested confirmation the emergency access accounts were disabled post-incident.",
                    "body": (
                        "We reset 14 exec accounts last night. Can you double-check the emergency accounts are disabled "
                        "again and provide an audit extract?"
                    ),
                    "timestamp_dt": now_utc - timedelta(hours=5, minutes=30),
                },
                {
                    "actor": "Tier 2 · Priya Desai",
                    "direction": "outbound",
                    "channel": "Chat",
                    "summary": "Shared Azure AD audit log confirming emergency access removal.",
                    "body": "Export attached and emergency accounts back to disabled state.",
                    "timestamp_dt": now_utc - timedelta(hours=4, minutes=55),
                },
            ],
            "watchers": ["security@tacticaldesk.example"],
        },
        {
            "id": "TD-4818",
            "subject": "Quarterly backup validation",
            "customer": "Axcelerate",
            "customer_email": "ops@axcelerate.example",
            "status": "Resolved",
            "priority": "Medium",
            "team": "Automation",
            "category": "Infrastructure",
            "assignment": "Shared",
            "queue": "Automation handoff",
            "channel": "Workflow",
            "last_reply_dt": now_utc - timedelta(days=1, hours=1),
            "labels": ["Automation"],
            "is_starred": False,
            "assets_visible": True,
            "created_at_dt": now_utc - timedelta(days=8),
            "due_at_dt": now_utc - timedelta(hours=2),
            "summary": "Completed validation cycle for Axcelerate production backups across regions.",
            "history": [
                {
                    "actor": "Automation Bot",
                    "direction": "system",
                    "channel": "Workflow",
                    "summary": "Validation workflow executed across 12 backup sets.",
                    "body": "All restore drills completed successfully. Reports archived in /reports/q1.",
                    "timestamp_dt": now_utc - timedelta(days=1, hours=1),
                },
            ],
            "watchers": ["automation@tacticaldesk.example"],
        },
        {
            "id": "TD-4817",
            "subject": "Password spray detected",
            "customer": "SyncroRMM",
            "customer_email": "soc@syncro.example",
            "status": "Closed",
            "priority": "High",
            "team": "Incident response",
            "category": "Security",
            "assignment": "Shared",
            "queue": "Critical response",
            "channel": "Automation",
            "last_reply_dt": now_utc - timedelta(days=6, hours=2),
            "labels": ["Post incident"],
            "is_starred": False,
            "assets_visible": False,
            "created_at_dt": now_utc - timedelta(days=6, hours=18),
            "due_at_dt": now_utc - timedelta(days=4),
            "summary": "Closed major incident after coordinated response to global password spray alerts.",
            "history": [
                {
                    "actor": "Automation Bot",
                    "direction": "system",
                    "channel": "Automation",
                    "summary": "Webhook alert from SIEM acknowledging containment.",
                    "body": "Incident runbook completed. Accounts rotated and IP ranges blocked.",
                    "timestamp_dt": now_utc - timedelta(days=6, hours=2),
                },
            ],
            "watchers": ["soc@syncro.example", "irlead@tacticaldesk.example"],
        },
        {
            "id": "TD-4816",
            "subject": "Spam newsletter opt-out",
            "customer": "Marketing",
            "customer_email": "noreply@marketing.example",
            "status": "Spam",
            "priority": "Low",
            "team": "Triage",
            "category": "Spam",
            "assignment": "Trashed",
            "queue": "Inbox cleanup",
            "channel": "Email",
            "last_reply_dt": now_utc - timedelta(days=14, hours=5),
            "labels": [],
            "is_starred": False,
            "assets_visible": False,
            "created_at_dt": now_utc - timedelta(days=14, hours=6),
            "due_at_dt": None,
            "summary": "Junk marketing request automatically classified and suppressed.",
            "history": [
                {
                    "actor": "Filter Engine",
                    "direction": "system",
                    "channel": "Email",
                    "summary": "Message quarantined as spam per policy.",
                    "body": "No analyst action required.",
                    "timestamp_dt": now_utc - timedelta(days=14, hours=5),
                },
            ],
            "watchers": [],
        },
    ]
    return seed_tickets


DEFAULT_INTEGRATION_ICON = "🔌"

DEFAULT_SETTINGS_FIELDS = [
    {
        "key": "base_url",
        "label": "Base URL",
        "type": "url",
        "placeholder": "https://example.integration/api",
    },
    {
        "key": "api_key",
        "label": "API Key",
        "type": "password",
        "placeholder": "Enter the secure API key",
    },
    {
        "key": "webhook_url",
        "label": "Webhook URL",
        "type": "url",
        "placeholder": "https://example.integration/webhooks",
    },
]

INTEGRATION_SETTINGS_FIELDS: dict[str, list[dict[str, str]]] = {
    "syncro-rmm": DEFAULT_SETTINGS_FIELDS,
    "tactical-rmm": DEFAULT_SETTINGS_FIELDS,
    "xero": [
        {
            "key": "base_url",
            "label": "Base URL",
            "type": "url",
            "placeholder": "https://api.xero.com",
        },
        {
            "key": "client_id",
            "label": "Client ID",
            "type": "text",
            "placeholder": "OAuth client identifier",
        },
        {
            "key": "client_secret",
            "label": "Client Secret",
            "type": "password",
            "placeholder": "Secure client secret",
        },
        {
            "key": "tenant_id",
            "label": "Tenant ID",
            "type": "text",
            "placeholder": "Organisation tenant identifier",
        },
    ],
}


def _format_iso(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_integration(module: IntegrationModule) -> dict[str, object]:
    settings_data = dict(module.settings) if module.settings else {}
    return {
        "id": module.id,
        "name": module.name,
        "slug": module.slug,
        "description": module.description or "",
        "icon": module.icon or DEFAULT_INTEGRATION_ICON,
        "enabled": bool(module.enabled),
        "settings": settings_data,
        "created_at_iso": _format_iso(module.created_at),
        "updated_at_iso": _format_iso(module.updated_at),
    }


def _serialize_organization(organization: Organization) -> dict[str, object]:
    return {
        "id": organization.id,
        "name": organization.name,
        "slug": organization.slug,
        "description": organization.description or "",
        "contact_email": organization.contact_email or "",
        "is_archived": bool(organization.is_archived),
        "created_at_iso": _format_iso(organization.created_at),
        "updated_at_iso": _format_iso(organization.updated_at),
    }


async def _get_organization_or_404(
    session: AsyncSession, organization_id: int
) -> Organization:
    result = await session.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


async def _organization_form_response(
    *,
    request: Request,
    session: AsyncSession,
    mode: str,
    form_values: dict[str, str],
    form_errors: list[str] | None = None,
    organization_name: str | None = None,
) -> HTMLResponse:
    normalized_values = {
        "name": form_values.get("name", ""),
        "slug": form_values.get("slug", ""),
        "contact_email": form_values.get("contact_email", ""),
        "description": form_values.get("description", ""),
    }
    is_edit = mode == "edit"
    base_name = organization_name or normalized_values["name"]
    if is_edit and base_name:
        page_title = f"Edit {base_name}"
    elif is_edit:
        page_title = "Edit organisation"
    else:
        page_title = "Create organisation"
    page_subtitle = (
        "Update tenant metadata, lifecycle state, and contact details before syncing across the platform."
        if is_edit
        else "Capture the organisation name, assign a slug for API usage, and optionally record the operations contact."
    )
    submit_label = "Save changes" if is_edit else "Create organisation"
    context = await _template_context(
        request=request,
        session=session,
        page_title=page_title,
        page_subtitle=page_subtitle,
        form_mode=mode,
        form_title=page_title,
        form_subtitle=page_subtitle,
        form_values=normalized_values,
        form_errors=form_errors or [],
        submit_label=submit_label,
        active_nav="admin",
        active_admin="organisations",
    )
    return templates.TemplateResponse("organization_form.html", context)


def _serialize_contact(contact: Contact) -> dict[str, object]:
    return {
        "id": contact.id,
        "organization_id": contact.organization_id,
        "name": contact.name,
        "job_title": contact.job_title or "",
        "email": contact.email or "",
        "phone": contact.phone or "",
        "notes": contact.notes or "",
        "created_at_iso": _format_iso(contact.created_at),
        "updated_at_iso": _format_iso(contact.updated_at),
    }


async def _load_enabled_integrations(session: AsyncSession) -> list[dict[str, str]]:
    result = await session.execute(
        select(IntegrationModule)
        .where(IntegrationModule.enabled.is_(True))
        .order_by(IntegrationModule.name.asc())
    )
    return [
        {
            "name": module.name,
            "slug": module.slug,
            "icon": module.icon or DEFAULT_INTEGRATION_ICON,
        }
        for module in result.scalars().all()
    ]


async def _list_integrations(session: AsyncSession) -> list[IntegrationModule]:
    result = await session.execute(
        select(IntegrationModule).order_by(IntegrationModule.name.asc())
    )
    return result.scalars().all()


async def _list_organizations(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(
        select(Organization).order_by(Organization.name.asc())
    )
    return [_serialize_organization(org) for org in result.scalars().all()]


async def _list_contacts_for_organization(
    session: AsyncSession, organization_id: int
) -> list[dict[str, object]]:
    result = await session.execute(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .order_by(Contact.name.asc())
    )
    return [_serialize_contact(contact) for contact in result.scalars().all()]


async def _template_context(
    *,
    request: Request,
    session: AsyncSession,
    integration_nav: list[dict[str, str]] | None = None,
    **extra: object,
) -> dict[str, object]:
    current_settings = get_settings()
    if integration_nav is None:
        integration_nav = await _load_enabled_integrations(session)
    context: dict[str, object] = {
        "request": request,
        "app_name": current_settings.app_name,
        "current_year": datetime.now(timezone.utc).year,
        "integration_nav": integration_nav,
    }
    context.update(extra)
    return context


@app.get("/", response_class=HTMLResponse, name="root_route")
async def root_route(
    request: Request,
    view: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    result = await session.execute(select(func.count()).select_from(User))
    user_count = result.scalar_one()

    if user_count == 0 or view == "register":
        template_name = "register.html"
        page_title = "Initial setup"
        page_subtitle = "Create the Tactical Desk super admin account."
    else:
        template_name = "login.html"
        page_title = "Sign in"
        page_subtitle = "Access Tactical Desk with your secure credentials."

    context = await _template_context(
        request=request,
        session=session,
        page_title=page_title,
        page_subtitle=page_subtitle,
        user_count=user_count,
    )
    return templates.TemplateResponse(template_name, context)


@app.get("/dashboard", response_class=HTMLResponse, name="dashboard")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    tickets = [
        {
            "id": 1821,
            "subject": "VPN tunnel intermittently dropping",
            "status": "Open",
            "priority": "High",
            "updated_at_iso": (now_utc - timedelta(minutes=12)).isoformat().replace("+00:00", "Z"),
            "updated_at_display": (now_utc - timedelta(minutes=12)).isoformat().replace("+00:00", "Z"),
        },
        {
            "id": 1820,
            "subject": "New employee onboarding automation",
            "status": "Waiting",
            "priority": "Medium",
            "updated_at_iso": (now_utc - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "updated_at_display": (now_utc - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        },
        {
            "id": 1819,
            "subject": "Service desk analytics export",
            "status": "Resolved",
            "priority": "Low",
            "updated_at_iso": (now_utc - timedelta(days=1, hours=3)).isoformat().replace("+00:00", "Z"),
            "updated_at_display": (now_utc - timedelta(days=1, hours=3)).isoformat().replace("+00:00", "Z"),
        },
    ]
    webhook_metrics = {
        "active": 5,
        "pending_retries": 1,
        "last_failure": (now_utc - timedelta(minutes=47)).isoformat().replace("+00:00", "Z"),
    }

    context = await _template_context(
        request=request,
        session=session,
        page_title="Operations Command Center",
        page_subtitle="Unify omnichannel tickets, automation, and Tactical RMM telemetry.",
        tickets=tickets,
        webhook_metrics=webhook_metrics,
        active_nav="dashboard",
    )
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/tickets", response_class=HTMLResponse, name="tickets")
async def tickets_view(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    seed_tickets = build_ticket_records(now_utc)
    seed_tickets = await ticket_store.apply_overrides(seed_tickets)

    status_counter: Counter[str] = Counter()
    assignment_counter: Counter[str] = Counter()
    queue_counter: Counter[str] = Counter()

    tickets: list[dict[str, object]] = []
    for ticket in seed_tickets:
        last_reply_iso = ticket["last_reply_dt"].isoformat().replace("+00:00", "Z")
        age_delta = now_utc - ticket["last_reply_dt"]
        filter_tokens = {
            "all",
            f"status-{slugify(ticket['status'])}",
            f"priority-{slugify(ticket['priority'])}",
            f"assignment-{slugify(ticket['assignment'])}",
            f"queue-{slugify(ticket['queue'])}",
            f"team-{slugify(ticket['team'])}",
            f"category-{slugify(ticket['category'])}",
        }
        if ticket.get("is_starred"):
            filter_tokens.add("flagged")
        if ticket.get("assets_visible"):
            filter_tokens.add("assets-visible")

        enriched_ticket = {
            **ticket,
            "last_reply_iso": last_reply_iso,
            "age_display": describe_age(age_delta),
            "filter_tokens": sorted(filter_tokens),
            "status_token": slugify(ticket["status"]),
            "priority_token": slugify(ticket["priority"]),
            "assignment_token": slugify(ticket["assignment"]),
        }
        tickets.append(enriched_ticket)

        status_counter.update([ticket["status"]])
        assignment_counter.update([ticket["assignment"]])
        queue_counter.update([ticket["queue"]])

    ticket_filter_groups = [
        {
            "title": "Tickets",
            "filters": [
                {"key": "all", "label": "All", "icon": "📋", "count": len(tickets)},
                {"key": "status-open", "label": "Open", "icon": "🟢", "count": status_counter.get("Open", 0)},
                {"key": "status-pending", "label": "Pending", "icon": "🕒", "count": status_counter.get("Pending", 0)},
                {"key": "status-answered", "label": "Answered", "icon": "✉️", "count": status_counter.get("Answered", 0)},
                {"key": "status-resolved", "label": "Resolved", "icon": "✅", "count": status_counter.get("Resolved", 0)},
                {"key": "status-closed", "label": "Closed", "icon": "📁", "count": status_counter.get("Closed", 0)},
                {"key": "status-spam", "label": "Spam", "icon": "🚫", "count": status_counter.get("Spam", 0)},
            ],
        },
        {
            "title": "New",
            "filters": [
                {"key": "assignment-unassigned", "label": "Unassigned", "icon": "🆕", "count": assignment_counter.get("Unassigned", 0)},
                {"key": "assignment-my-tickets", "label": "My tickets", "icon": "👤", "count": assignment_counter.get("My tickets", 0)},
                {"key": "assignment-shared", "label": "Shared", "icon": "👥", "count": assignment_counter.get("Shared", 0)},
                {"key": "assignment-trashed", "label": "Trashed", "icon": "🗑️", "count": assignment_counter.get("Trashed", 0)},
            ],
        },
        {
            "title": "Queues",
            "filters": [
                {"key": f"queue-{slugify(name)}", "label": name, "icon": "🗂️", "count": queue_counter.get(name, 0)}
                for name in sorted(queue_counter)
            ],
        },
    ]

    ticket_sort_options = [
        {"value": "last-replied", "label": "Last replied"},
        {"value": "newest", "label": "Newest"},
        {"value": "oldest", "label": "Oldest"},
        {"value": "priority", "label": "Priority"},
    ]

    asset_view_options = [
        {"value": "workspace", "label": "Workspace assets"},
        {"value": "related", "label": "Related assets"},
        {"value": "all", "label": "All assets"},
    ]

    status_options = sorted({ticket["status"] for ticket in seed_tickets})
    priority_options = sorted({ticket["priority"] for ticket in seed_tickets})
    team_options = sorted({ticket["team"] for ticket in seed_tickets})

    context = await _template_context(
        request=request,
        session=session,
        page_title="Unified Ticket Workspace",
        page_subtitle="Track queues, escalations, and SLA risk across every service channel.",
        tickets=tickets,
        ticket_filter_groups=ticket_filter_groups,
        ticket_sort_options=ticket_sort_options,
        asset_view_options=asset_view_options,
        ticket_status_options=status_options,
        ticket_priority_options=priority_options,
        ticket_team_options=team_options,
        active_nav="tickets",
    )
    return templates.TemplateResponse("tickets.html", context)


@app.get("/tickets/{ticket_id}", response_class=HTMLResponse, name="ticket_detail")
async def ticket_detail_view(
    request: Request,
    ticket_id: str,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    context = await _prepare_ticket_detail_context(
        request,
        now_utc,
        ticket_id=ticket_id,
        saved=request.query_params.get("saved") == "1",
    )
    context = await _template_context(session=session, **context)
    return templates.TemplateResponse("ticket_detail.html", context)


@app.post("/tickets/{ticket_id}", response_class=HTMLResponse, name="ticket_update")
async def ticket_update_view(
    request: Request,
    ticket_id: str,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    seed_tickets = build_ticket_records(now_utc)
    seed_tickets = await ticket_store.apply_overrides(seed_tickets)
    ticket_lookup = {ticket["id"]: ticket for ticket in seed_tickets}
    if ticket_id not in ticket_lookup:
        raise HTTPException(status_code=404, detail="Ticket not found")

    form_data = await _extract_ticket_form_data(request)

    try:
        payload = TicketUpdate(**form_data)
    except ValidationError as exc:
        error_messages = _format_ticket_validation_errors(exc)
        sanitized_form_data = {
            key: form_data.get(key, "").strip() for key in TICKET_FORM_FIELDS
        }
        context = await _prepare_ticket_detail_context(
            request,
            now_utc,
            ticket_id=ticket_id,
            form_data=sanitized_form_data,
            form_errors=error_messages,
        )
        context = await _template_context(session=session, **context)
        return templates.TemplateResponse(
            "ticket_detail.html",
            context,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    await ticket_store.update_ticket(ticket_id, **payload.dict())

    redirect_url = request.url_for("ticket_detail", ticket_id=ticket_id)
    redirect_url = f"{redirect_url}?saved=1"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/analytics", response_class=HTMLResponse, name="analytics")
async def analytics_view(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    monthly_summary = [
        {
            "month": "January",
            "tickets_closed": 482,
            "first_response_minutes": 28,
            "customer_sat": 96,
        },
        {
            "month": "February",
            "tickets_closed": 455,
            "first_response_minutes": 31,
            "customer_sat": 94,
        },
        {
            "month": "March",
            "tickets_closed": 501,
            "first_response_minutes": 26,
            "customer_sat": 97,
        },
    ]

    automation_roi = [
        {
            "playbook": "Patch orchestration",
            "saves_hours": 86,
            "last_run_iso": (now_utc - timedelta(hours=6, minutes=12)).isoformat().replace("+00:00", "Z"),
        },
        {
            "playbook": "User provisioning",
            "saves_hours": 54,
            "last_run_iso": (now_utc - timedelta(days=1, hours=2)).isoformat().replace("+00:00", "Z"),
        },
        {
            "playbook": "Backup validation",
            "saves_hours": 39,
            "last_run_iso": (now_utc - timedelta(days=2, hours=5)).isoformat().replace("+00:00", "Z"),
        },
    ]

    context = await _template_context(
        request=request,
        session=session,
        page_title="Analytics Observatory",
        page_subtitle="Surface operational insights, response trends, and automation ROI.",
        monthly_summary=monthly_summary,
        automation_roi=automation_roi,
        active_nav="analytics",
    )
    return templates.TemplateResponse("analytics.html", context)


@app.get("/automation", response_class=HTMLResponse, name="automation")
async def automation_view(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    result = await session.execute(
        select(Automation).order_by(Automation.name.asc())
    )
    automations = result.scalars().all()

    scheduled_automations: list[dict[str, object]] = []
    event_automations: list[dict[str, object]] = []

    for automation in automations:
        view_model = _automation_to_view_model(automation)
        if automation.kind == "scheduled":
            scheduled_automations.append(view_model)
        elif automation.kind == "event":
            event_automations.append(view_model)

    scheduled_automations.sort(key=lambda item: item["name"].lower())
    event_automations.sort(key=lambda item: item["name"].lower())

    context = await _template_context(
        request=request,
        session=session,
        page_title="Automation Control Tower",
        page_subtitle="Manage lifecycle automation and run secure platform updates.",
        active_nav="admin",
        active_admin="automation",
        scheduled_automations=scheduled_automations,
        event_automations=event_automations,
    )
    return templates.TemplateResponse("automation.html", context)


@app.get("/automation/{automation_id}", response_class=HTMLResponse, name="automation_edit")
async def automation_edit_view(
    request: Request,
    automation_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    result = await session.execute(
        select(Automation).where(Automation.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")

    automation_view = _automation_to_view_model(automation)

    context = await _template_context(
        request=request,
        session=session,
        page_title="Automation editor",
        page_subtitle=(
            f"Review and adjust configuration for {automation_view['name']}."
        ),
        active_nav="admin",
        active_admin="automation",
        automation=automation_view,
    )
    return templates.TemplateResponse("automation_edit.html", context)


@app.get("/integrations", response_class=HTMLResponse, name="integrations_index")
async def integrations_index(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    modules = await _list_integrations(session)
    serialized = [_serialize_integration(module) for module in modules]
    context = await _template_context(
        request=request,
        session=session,
        page_title="Integration hub",
        page_subtitle="Enable connectors, enforce least privilege, and manage credentials in one place.",
        integrations=serialized,
        active_nav="admin",
        active_admin="integrations",
    )
    return templates.TemplateResponse("integrations.html", context)


@app.get(
    "/integrations/{slug}",
    response_class=HTMLResponse,
    name="integration_detail",
)
async def integration_detail(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    result = await session.execute(
        select(IntegrationModule).where(IntegrationModule.slug == slug)
    )
    module = result.scalar_one_or_none()
    if module is None:
        raise HTTPException(status_code=404, detail="Integration module not found")

    module_info = _serialize_integration(module)
    settings_fields = [
        dict(field)
        for field in INTEGRATION_SETTINGS_FIELDS.get(
            module.slug,
            DEFAULT_SETTINGS_FIELDS,
        )
    ]

    context = await _template_context(
        request=request,
        session=session,
        page_title=f"{module.name} integration",
        page_subtitle=module.description
        or "Configure secure access, credentials, and automation hooks for this integration.",
        module=module_info,
        settings_fields=settings_fields,
        active_nav="admin",
        active_admin="integrations",
        active_integration=module.slug,
    )
    return templates.TemplateResponse("integration_detail.html", context)


@app.get("/admin/maintenance", response_class=HTMLResponse, name="maintenance")
async def maintenance(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    scripts = [
        {
            "name": "Production install",
            "slug": "install",
            "description": "Provision Tactical Desk with a production-ready systemd service.",
        },
        {
            "name": "Production update",
            "slug": "update",
            "description": "Pull new commits, refresh dependencies, and restart the live service.",
        },
        {
            "name": "Development install",
            "slug": "install-dev",
            "description": "Deploy an isolated testing stack backed by a dedicated SQLite database.",
        },
    ]
    current_settings = get_settings()
    context = await _template_context(
        request=request,
        session=session,
        page_title="Maintenance controls",
        page_subtitle="Review installer guardrails and reference approved deployment runbooks.",
        maintenance_scripts=scripts,
        installers_enabled=current_settings.enable_installers,
        active_nav="admin",
        active_admin="maintenance",
    )
    return templates.TemplateResponse("maintenance.html", context)


@app.get(
    "/admin/organisations",
    response_class=HTMLResponse,
    name="admin_organisations",
)
async def admin_organisations(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    organizations = await _list_organizations(session)
    context = await _template_context(
        request=request,
        session=session,
        page_title="Organisation directory",
        page_subtitle="Catalogue tenant accounts, update details, and manage archival state.",
        organizations=organizations,
        active_nav="admin",
        active_admin="organisations",
    )
    return templates.TemplateResponse("organisations.html", context)


@app.get(
    "/admin/organisations/new",
    response_class=HTMLResponse,
    name="admin_organization_create",
)
async def admin_organization_create(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    form_values = {"name": "", "slug": "", "contact_email": "", "description": ""}
    return await _organization_form_response(
        request=request,
        session=session,
        mode="create",
        form_values=form_values,
    )


@app.post(
    "/admin/organisations/new",
    response_class=HTMLResponse,
    name="admin_organization_create_submit",
)
async def admin_organization_create_submit(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    form = await request.form()
    form_values = {
        "name": (form.get("name") or "").strip(),
        "slug": (form.get("slug") or "").strip().lower(),
        "contact_email": (form.get("contact_email") or "").strip(),
        "description": (form.get("description") or "").strip(),
    }
    try:
        payload = OrganizationCreate(
            name=form_values["name"],
            slug=form_values["slug"],
            contact_email=form_values["contact_email"] or None,
            description=form_values["description"] or None,
        )
    except ValidationError as exc:
        errors = [error["msg"] for error in exc.errors()]
        return await _organization_form_response(
            request=request,
            session=session,
            mode="create",
            form_values=form_values,
            form_errors=errors,
        )

    try:
        await organizations_router.create_organization(payload, session)
    except HTTPException as exc:
        if exc.status_code in {status.HTTP_409_CONFLICT, status.HTTP_422_UNPROCESSABLE_ENTITY}:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            return await _organization_form_response(
                request=request,
                session=session,
                mode="create",
                form_values=form_values,
                form_errors=[detail],
            )
        raise

    return RedirectResponse(
        request.url_for("admin_organisations"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get(
    "/admin/organisations/{organization_id}/edit",
    response_class=HTMLResponse,
    name="admin_organization_edit",
)
async def admin_organization_edit(
    request: Request,
    organization_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    organization = await _get_organization_or_404(session, organization_id)
    form_values = {
        "name": organization.name,
        "slug": organization.slug,
        "contact_email": organization.contact_email or "",
        "description": organization.description or "",
    }
    return await _organization_form_response(
        request=request,
        session=session,
        mode="edit",
        form_values=form_values,
        organization_name=organization.name,
    )


@app.post(
    "/admin/organisations/{organization_id}/edit",
    response_class=HTMLResponse,
    name="admin_organization_update",
)
async def admin_organization_update(
    request: Request,
    organization_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    organization = await _get_organization_or_404(session, organization_id)
    form = await request.form()
    form_values = {
        "name": (form.get("name") or "").strip(),
        "slug": (form.get("slug") or "").strip().lower(),
        "contact_email": (form.get("contact_email") or "").strip(),
        "description": (form.get("description") or "").strip(),
    }
    try:
        payload = OrganizationUpdate(
            name=form_values["name"],
            slug=form_values["slug"],
            contact_email=form_values["contact_email"] or None,
            description=form_values["description"] or None,
        )
    except ValidationError as exc:
        errors = [error["msg"] for error in exc.errors()]
        return await _organization_form_response(
            request=request,
            session=session,
            mode="edit",
            form_values=form_values,
            form_errors=errors,
            organization_name=form_values["name"] or organization.name,
        )

    try:
        await organizations_router.update_organization(organization_id, payload, session)
    except HTTPException as exc:
        if exc.status_code in {status.HTTP_409_CONFLICT, status.HTTP_422_UNPROCESSABLE_ENTITY}:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            return await _organization_form_response(
                request=request,
                session=session,
                mode="edit",
                form_values=form_values,
                form_errors=[detail],
                organization_name=form_values["name"] or organization.name,
            )
        raise

    return RedirectResponse(
        request.url_for("admin_organisations"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get(
    "/admin/organisations/{organization_id}/contacts",
    response_class=HTMLResponse,
    name="admin_organization_contacts",
)
async def admin_organization_contacts(
    request: Request,
    organization_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    organization = await _get_organization_or_404(session, organization_id)
    contacts = await _list_contacts_for_organization(session, organization_id)
    organization_payload = _serialize_organization(organization)
    context = await _template_context(
        request=request,
        session=session,
        page_title=f"{organization.name} contacts",
        page_subtitle="Keep your stakeholder roster accurate with job titles and escalation paths.",
        organization=organization_payload,
        contacts=contacts,
        contact_count=len(contacts),
        active_nav="admin",
        active_admin="organisations",
    )
    return templates.TemplateResponse("organization_contacts.html", context)
def _format_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_webhook(delivery: WebhookDelivery) -> dict[str, object]:
    status_label = delivery.status.replace("_", " ").title()
    return {
        "id": delivery.event_id,
        "event_id": delivery.event_id,
        "endpoint": delivery.endpoint,
        "status": delivery.status,
        "status_label": status_label,
        "last_attempt": _format_iso(delivery.last_attempt_at),
        "next_retry": _format_iso(delivery.next_retry_at),
    }


async def _ensure_demo_webhooks(session: AsyncSession) -> list[WebhookDelivery]:
    result = await session.execute(select(WebhookDelivery))
    existing = result.scalars().all()
    if existing:
        return existing

    now = utcnow()
    deliveries = [
        WebhookDelivery(
            event_id="whk-512",
            endpoint="https://hooks.tacticalrmm.local/notify",
            status=WebhookStatus.RETRYING.value,
            last_attempt_at=now - timedelta(minutes=5),
            next_retry_at=now + timedelta(minutes=5),
        ),
        WebhookDelivery(
            event_id="whk-511",
            endpoint="https://hooks.syncro.local/tickets",
            status=WebhookStatus.PAUSED.value,
            last_attempt_at=now - timedelta(hours=1, minutes=12),
            next_retry_at=None,
        ),
    ]
    session.add_all(deliveries)
    await session.commit()
    for delivery in deliveries:
        await session.refresh(delivery)
    return deliveries


@app.get("/admin/webhooks", response_class=HTMLResponse, name="admin_webhooks")
async def admin_webhooks(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    deliveries = await _ensure_demo_webhooks(session)
    webhook_failures = [_serialize_webhook(delivery) for delivery in deliveries]
    context = await _template_context(
        request=request,
        session=session,
        page_title="Webhook operations",
        page_subtitle="Monitor outbound delivery failures and adjust retry cadence as needed.",
        webhook_failures=webhook_failures,
        active_nav="admin",
        active_admin="webhooks",
    )
    return templates.TemplateResponse("admin_webhooks.html", context)


@app.get("/health", tags=["System"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
