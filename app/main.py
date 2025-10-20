from __future__ import annotations

from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs
import re

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.routers import auth as auth_router
from app.api.routers import automations as automations_router
from app.api.routers import integrations as integrations_router
from app.api.routers import knowledge as knowledge_router
from app.api.routers import maintenance as maintenance_router
from app.api.routers import mcp as mcp_router
from app.api.routers import organizations as organizations_router
from app.api.routers import tickets as tickets_router
from app.api.routers import webhooks as webhooks_router
from app.core.automations import (
    EVENT_AUTOMATION_ACTIONS,
    EVENT_AUTOMATION_ACTION_CHOICES,
    EVENT_TRIGGER_OPTIONS,
    TRIGGER_OPERATOR_OPTIONS,
    VALUE_REQUIRED_TRIGGER_OPTIONS,
)
from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine, get_session
from app.core.automation_dispatcher import automation_dispatcher
from app.core.tickets import ticket_store
from app.core.http_post_webhook import HTTP_POST_TEMPLATE_VARIABLES
from app.core.template_variables import AUTOMATION_TEMPLATE_VARIABLES
from app.models import (
    Automation,
    Contact,
    IntegrationModule,
    Organization,
    User,
    WebhookDelivery,
    utcnow,
)
from app.schemas import (
    AutomationTicketAction,
    AutomationTriggerFilter,
    OrganizationCreate,
    OrganizationUpdate,
    TicketCreate,
    TicketReply,
    TicketUpdate,
    WebhookStatus,
)
from app.services import dispatch_ticket_event
from app.services.knowledge_base import (
    build_document_tree as build_knowledge_tree,
    list_documents as list_space_documents,
    list_revisions as list_document_revisions,
    list_spaces_with_counts as list_space_summaries,
)
from app.services.ticket_data import (
    build_ticket_records,
    enrich_ticket_record,
    fetch_ticket_records,
    slugify_label,
)
from app.services.ticket_summary import refresh_ticket_summary
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
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
app.include_router(auth_router.router)
app.include_router(automations_router.router)
app.include_router(integrations_router.router)
app.include_router(knowledge_router.router)
app.include_router(maintenance_router.router)
app.include_router(organizations_router.router)
app.include_router(webhooks_router.router)
app.include_router(mcp_router.router)
app.include_router(tickets_router.router)


@app.get("/api/docs", include_in_schema=False, name="api_docs_swagger_ui")
async def api_docs_swagger_ui(request: Request) -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{settings.app_name} API Docs",
        oauth2_redirect_url=request.url_for("swagger_ui_redirect"),
        swagger_favicon_url=str(request.url_for("static", path="img/favicon.svg")),
    )


@app.get(
    "/api/docs/oauth2-redirect",
    include_in_schema=False,
    name="swagger_ui_redirect",
)
async def swagger_ui_redirect() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()


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

REPLY_FORM_FIELDS = (
    "to",
    "cc",
    "template",
    "message",
    "public_reply",
    "add_signature",
)

REPLY_FIELD_LABELS = {
    "to": "Recipient",
    "cc": "CC",
    "template": "Reply template",
    "message": "Message",
    "public_reply": "Public reply",
    "add_signature": "Append signature",
}

DEFAULT_REPLY_ACTOR = "Super Admin"
DEFAULT_REPLY_CHANNEL = "Portal reply"


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

    manual_run_endpoint: str | None = None
    if automation.kind == "scheduled":
        manual_run_endpoint = app.url_path_for(
            "run_automation", automation_id=str(automation.id)
        )

    delete_endpoint = app.url_path_for(
        "delete_automation", automation_id=str(automation.id)
    )

    filters_dict: dict[str, object] | None = None
    filters_model: AutomationTriggerFilter | None = None
    action_models: list[AutomationTicketAction] = []
    if automation.ticket_actions:
        for entry in automation.ticket_actions:
            try:
                model = AutomationTicketAction.parse_obj(entry)
            except ValidationError:
                continue
            action_models.append(model)

    if automation.trigger_filters:
        try:
            filters_model = AutomationTriggerFilter.parse_obj(automation.trigger_filters)
            filters_dict = filters_model.dict()
        except ValidationError:
            filters_dict = None
            filters_model = None

    trigger_display = automation.trigger or ""
    trigger_sort_value = automation.trigger or ""
    if filters_model and filters_model.conditions:
        display_conditions = [
            condition.display_text() for condition in filters_model.conditions
        ]
        sort_values = [condition.sort_key() for condition in filters_model.conditions]
        if len(display_conditions) == 1:
            trigger_display = display_conditions[0]
            trigger_sort_value = sort_values[0]
        else:
            prefix = "ALL" if filters_model.match == "all" else "ANY"
            trigger_display = f"{prefix}: {', '.join(display_conditions)}"
            trigger_sort_value = " ".join(sort_values)
    if not trigger_display:
        trigger_display = "—"

    return {
        "id": automation.id,
        "name": automation.name,
        "description": automation.description or "",
        "playbook": automation.playbook,
        "kind": automation.kind,
        "cron_expression": automation.cron_expression,
        "trigger": automation.trigger,
        "trigger_display": trigger_display,
        "trigger_sort": trigger_sort_value,
        "trigger_filters": filters_dict,
        "status": automation.status,
        "next_run_iso": _automation_datetime_to_iso(automation.next_run_at),
        "last_run_iso": _automation_datetime_to_iso(automation.last_run_at),
        "last_trigger_iso": _automation_datetime_to_iso(automation.last_trigger_at),
        "ticket_actions": [model.dict() for model in action_models],
        "action": action,
        "action_label": automation.action_label,
        "action_endpoint": automation.action_endpoint,
        "action_output_selector": automation.action_output_selector
        or DEFAULT_AUTOMATION_OUTPUT_SELECTOR,
        "manual_run_endpoint": manual_run_endpoint,
        "delete_endpoint": delete_endpoint,
        "supports_manual_run": automation.kind == "scheduled",
    }


def _empty_automation_view(kind: str) -> dict[str, object]:
    is_event = kind == "event"
    default_trigger = "Ticket Created" if is_event else None
    default_trigger_display = default_trigger or "—"
    return {
        "id": "",
        "name": "",
        "description": "",
        "playbook": "",
        "kind": kind,
        "cron_expression": "" if kind == "scheduled" else None,
        "trigger": default_trigger,
        "trigger_display": default_trigger_display,
        "trigger_sort": "",
        "trigger_filters": None,
        "status": "",
        "next_run_iso": "",
        "last_run_iso": "",
        "last_trigger_iso": "",
        "ticket_actions": [],
        "action": None,
        "action_label": None,
        "action_endpoint": None,
        "action_output_selector": DEFAULT_AUTOMATION_OUTPUT_SELECTOR,
        "manual_run_endpoint": None,
        "delete_endpoint": None,
        "supports_manual_run": kind == "scheduled",
    }


def _derive_ticket_update_event_type(
    ticket_before: dict[str, object], ticket_after: dict[str, object]
) -> str:
    previous_status = str(ticket_before.get("status", "")) if ticket_before else ""
    new_status = str(ticket_after.get("status", "")) if ticket_after else ""
    previous_normalized = previous_status.strip().casefold()
    new_normalized = new_status.strip().casefold()
    if previous_normalized and new_normalized and previous_normalized != new_normalized:
        if new_normalized in {"resolved", "closed"}:
            return "Ticket Resolved"
        return "Ticket Status Changed"
    return "Ticket Updated by Technician"


async def _load_automation(
    session: AsyncSession, automation_id: int
) -> Automation:
    result = await session.execute(
        select(Automation).where(Automation.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return automation


def _derive_ticket_form_defaults(
    *,
    tickets_raw: list[dict[str, object]],
    form_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    status_options = sorted(
        {str(ticket.get("status")) for ticket in tickets_raw if ticket.get("status")}
    )
    priority_options = sorted(
        {str(ticket.get("priority")) for ticket in tickets_raw if ticket.get("priority")}
    )
    team_options = sorted(
        {str(ticket.get("team")) for ticket in tickets_raw if ticket.get("team")}
    )
    assignment_options = sorted(
        {str(ticket.get("assignment")) for ticket in tickets_raw if ticket.get("assignment")}
    )
    queue_options = sorted(
        {str(ticket.get("queue")) for ticket in tickets_raw if ticket.get("queue")}
    )

    default_form = {field: "" for field in TICKET_FORM_FIELDS}
    if status_options:
        default_form["status"] = status_options[0]
    if priority_options:
        default_form["priority"] = priority_options[0]
    if team_options:
        default_form["team"] = team_options[0]
    if assignment_options:
        default_form["assignment"] = assignment_options[0]
    if queue_options:
        default_form["queue"] = queue_options[0]

    if form_overrides:
        for key, value in form_overrides.items():
            if key in default_form:
                default_form[key] = value

    return {
        "ticket_form": default_form,
        "ticket_status_options": status_options,
        "ticket_priority_options": priority_options,
        "ticket_team_options": team_options,
        "ticket_assignment_options": assignment_options,
        "ticket_queue_options": queue_options,
    }


def _derive_customer_options(
    organizations: Iterable[dict[str, object]]
) -> list[str]:
    options: set[str] = set()
    for organization in organizations:
        name_raw = organization.get("name", "")
        if not isinstance(name_raw, str):
            continue
        name = name_raw.strip()
        if not name:
            continue
        if organization.get("is_archived"):
            continue
        options.add(name)
    return sorted(options, key=str.casefold)


async def _build_ticket_listing_context(
    *,
    request: Request,
    session: AsyncSession,
    now_utc: datetime,
    tickets_raw: list[dict[str, object]],
) -> dict[str, object]:
    status_counter: Counter[str] = Counter()
    assignment_counter: Counter[str] = Counter()
    queue_counter: Counter[str] = Counter()

    enriched_tickets: list[dict[str, object]] = []
    for ticket in tickets_raw:
        enriched = enrich_ticket_record(ticket, now_utc)
        enriched_tickets.append(enriched)
        status_counter.update([str(enriched.get("status", ""))])
        assignment_counter.update([str(enriched.get("assignment", ""))])
        queue_counter.update([str(enriched.get("queue", ""))])

    ticket_filter_groups = [
        {
            "title": "Tickets",
            "filters": [
                {"key": "all", "label": "All", "icon": "📋", "count": len(enriched_tickets)},
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
                {
                    "key": f"queue-{slugify_label(name)}",
                    "label": name,
                    "icon": "🗂️",
                    "count": queue_counter.get(name, 0),
                }
                for name in sorted(name for name in queue_counter if name)
            ],
        },
    ]

    context = await _template_context(
        request=request,
        session=session,
        page_title="Unified Ticket Workspace",
        page_subtitle="Track queues, escalations, and SLA risk across every service channel.",
        tickets=enriched_tickets,
        ticket_filter_groups=ticket_filter_groups,
        active_nav="tickets",
    )
    return context


async def _build_ticket_create_context(
    *,
    request: Request,
    session: AsyncSession,
    now_utc: datetime,
    tickets_raw: list[dict[str, object]],
    form_data: dict[str, str] | None = None,
    form_errors: list[str] | None = None,
) -> dict[str, object]:
    form_defaults = _derive_ticket_form_defaults(
        tickets_raw=tickets_raw,
        form_overrides=form_data,
    )

    organizations = await _list_organizations(session)
    customer_options = _derive_customer_options(organizations)

    context = await _template_context(
        request=request,
        session=session,
        page_title="Create ticket",
        page_subtitle="Collect routing metadata before the first response.",
        active_nav="tickets",
        ticket_form=form_defaults["ticket_form"],
        ticket_status_options=form_defaults["ticket_status_options"],
        ticket_priority_options=form_defaults["ticket_priority_options"],
        ticket_team_options=form_defaults["ticket_team_options"],
        ticket_assignment_options=form_defaults["ticket_assignment_options"],
        ticket_queue_options=form_defaults["ticket_queue_options"],
        ticket_customer_options=customer_options,
        ticket_form_errors=form_errors or [],
    )
    return context


def _format_field_label(field_name: str) -> str:
    return field_name.replace("_", " ").capitalize()


def _format_validation_errors(
    error: ValidationError, field_labels: dict[str, str] | None = None
) -> list[str]:
    messages: list[str] = []
    for entry in error.errors():
        field = str(entry.get("loc", [""])[-1])
        label = field_labels.get(field, _format_field_label(field)) if field_labels else _format_field_label(field)
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


def _normalize_checkbox(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "on", "yes"}


def _summarize_reply(message: str, limit: int = 160) -> str:
    collapsed = " ".join(message.strip().splitlines())
    if not collapsed:
        return "Reply sent"
    if len(collapsed) > limit:
        return collapsed[: limit - 1].rstrip() + "…"
    return collapsed


async def _extract_form_data(
    request: Request, fields: tuple[str, ...]
) -> dict[str, str]:
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
        return {field: parsed.get(field, [""])[0] for field in fields}

    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported form submission type.",
        ) from exc
    result: dict[str, str] = {}
    for field in fields:
        value = form.get(field)
        if isinstance(value, str):
            result[field] = value
        elif value is None:
            result[field] = ""
        else:
            result[field] = str(value)
    return result


async def _prepare_ticket_detail_context(
    request: Request,
    now_utc: datetime,
    session: AsyncSession,
    *,
    ticket_id: str,
    form_data: dict[str, str] | None = None,
    form_errors: list[str] | None = None,
    saved: bool = False,
    reply_form_data: dict[str, str] | None = None,
    reply_form_errors: list[str] | None = None,
    reply_saved: bool = False,
    created: bool = False,
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
            entry_copy["timestamp_dt"] = timestamp_dt
            entry_copy["timestamp_iso"] = (
                timestamp_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        history_entries.append(entry_copy)

    stored_replies = await ticket_store.list_replies(ticket_id)
    for entry in stored_replies:
        entry_copy = dict(entry)
        timestamp_dt = entry_copy.get("timestamp_dt")
        if isinstance(timestamp_dt, datetime):
            if timestamp_dt.tzinfo is None:
                timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
            entry_copy["timestamp_dt"] = timestamp_dt
            entry_copy["timestamp_iso"] = (
                timestamp_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        history_entries.append(entry_copy)

    history_entries.sort(
        key=lambda entry: entry.get("timestamp_dt") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

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

    default_reply_form = {
        "to": display_ticket.get("customer_email", ""),
        "cc": "",
        "template": "custom",
        "message": "",
        "public_reply": "on",
        "add_signature": "on",
    }
    if reply_form_data:
        default_reply_form.update(reply_form_data)

    organizations = await _list_organizations(session)
    customer_options = _derive_customer_options(organizations)

    summary_record = await ticket_store.get_summary(ticket_id)
    if summary_record is None:
        summary_record = await refresh_ticket_summary(session, display_ticket)

    formatted_summary = {
        "summary": "",
        "provider": "",
        "model": None,
        "updated_at_iso": "",
        "error_message": "",
        "used_fallback": False,
    }
    if summary_record:
        formatted_summary.update(
            {
                key: summary_record.get(key)
                for key in (
                    "summary",
                    "provider",
                    "model",
                    "updated_at_iso",
                    "error_message",
                    "used_fallback",
                )
                if key in summary_record
            }
        )
        updated_at_dt = summary_record.get("updated_at_dt")
        if not formatted_summary.get("updated_at_iso") and isinstance(updated_at_dt, datetime):
            if updated_at_dt.tzinfo is None:
                updated_at_dt = updated_at_dt.replace(tzinfo=timezone.utc)
            formatted_summary["updated_at_iso"] = (
                updated_at_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        if not formatted_summary.get("used_fallback"):
            formatted_summary["used_fallback"] = (
                formatted_summary.get("provider") == "fallback"
            )

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
        "ticket_customer_options": customer_options,
        "active_nav": "tickets",
        "form_errors": form_errors or [],
        "form_saved": saved,
        "reply_form_data": default_reply_form,
        "reply_form_errors": reply_form_errors or [],
        "reply_form_saved": reply_saved,
        "ticket_created": created,
        "ticket_summary": formatted_summary,
    }




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

SYNCRO_SETTINGS_FIELDS = [
    {
        "key": "subdomain",
        "label": "Syncro subdomain",
        "type": "text",
        "placeholder": "your-company",
    },
    {
        "key": "api_key",
        "label": "API Key",
        "type": "password",
        "placeholder": "Enter the secure API key",
    },
]

INTEGRATION_SETTINGS_FIELDS: dict[str, list[dict[str, str]]] = {
    "syncro-rmm": SYNCRO_SETTINGS_FIELDS,
    "tactical-rmm": DEFAULT_SETTINGS_FIELDS,
    "ntfy": [
        {
            "key": "base_url",
            "label": "Base URL",
            "type": "url",
            "placeholder": "https://ntfy.example",
        },
        {
            "key": "topic",
            "label": "Topic",
            "type": "text",
            "placeholder": "operations-alerts",
        },
        {
            "key": "token",
            "label": "Access token",
            "type": "password",
            "placeholder": "Optional bearer token",
        },
    ],
    "smtp-email": [
        {
            "key": "smtp_host",
            "label": "SMTP host",
            "type": "text",
            "placeholder": "smtp.example.com",
        },
        {
            "key": "smtp_port",
            "label": "SMTP port",
            "type": "number",
            "placeholder": "587",
        },
        {
            "key": "smtp_username",
            "label": "SMTP username",
            "type": "text",
            "placeholder": "service-account",
        },
        {
            "key": "smtp_password",
            "label": "SMTP password",
            "type": "password",
            "placeholder": "Secure credential",
        },
        {
            "key": "smtp_sender",
            "label": "From address",
            "type": "email",
            "placeholder": "alerts@example.com",
        },
        {
            "key": "smtp_bcc",
            "label": "BCC recipients",
            "type": "text",
            "placeholder": "hidden@example.com",
        },
        {
            "key": "smtp_use_tls",
            "label": "Use STARTTLS (true/false)",
            "type": "text",
            "placeholder": "true",
        },
        {
            "key": "smtp_use_ssl",
            "label": "Use implicit TLS (true/false)",
            "type": "text",
            "placeholder": "false",
        },
    ],
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
    "https-post-receiver": [],
    "ollama": [
        {
            "key": "base_url",
            "label": "Base URL",
            "type": "url",
            "placeholder": "http://127.0.0.1:11434",
        },
        {
            "key": "model",
            "label": "Model",
            "type": "text",
            "placeholder": "llama3",
        },
        {
            "key": "prompt",
            "label": "Additional prompt guidance",
            "type": "text",
            "placeholder": "Optional instructions appended to the summary prompt",
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


async def _list_runbook_labels(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(
        select(Automation.playbook, func.count(Automation.id))
        .group_by(Automation.playbook)
        .order_by(Automation.playbook.asc())
    )
    return [
        {"label": label, "automation_count": count}
        for label, count in result.all()
    ]


def _format_datetime_for_display(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_space_icon(icon: str | None) -> str:
    return icon or "📘"


def _serialize_knowledge_tree(
    nodes: list[dict[str, object]],
    *,
    request: Request,
    space_slug: str,
    selected_slug: str | None,
) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for node in nodes:
        children_serialized = _serialize_knowledge_tree(
            node["children"],
            request=request,
            space_slug=space_slug,
            selected_slug=selected_slug,
        )
        is_active = selected_slug == node["slug"] if selected_slug else False
        is_expanded = is_active or any(child.get("is_expanded") or child.get("is_active") for child in children_serialized)
        serialized.append(
            {
                "id": node["id"],
                "title": node["title"],
                "slug": node["slug"],
                "is_published": node["is_published"],
                "position": node["position"],
                "status_label": "Published" if node["is_published"] else "Draft",
                "url": f"{request.url_for('knowledge_base')}?space={space_slug}&document={node['slug']}",
                "is_active": is_active,
                "is_expanded": is_expanded,
                "children": children_serialized,
            }
        )
    return serialized


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


@app.get("/knowledge", response_class=HTMLResponse, name="knowledge_base")
async def knowledge_base_view(
    request: Request,
    space: str | None = None,
    document: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    spaces_raw = await list_space_summaries(session)
    selected_space_summary: dict[str, object] | None = None
    if space:
        for item in spaces_raw:
            if item["slug"] == space:
                selected_space_summary = item
                break
    if selected_space_summary is None and spaces_raw:
        selected_space_summary = spaces_raw[0]

    knowledge_spaces: list[dict[str, object]] = []
    for item in spaces_raw:
        knowledge_spaces.append(
            {
                "id": item["id"],
                "name": item["name"],
                "slug": item["slug"],
                "icon": _default_space_icon(item.get("icon")),
                "is_private": bool(item.get("is_private")),
                "document_count": int(item.get("document_count", 0)),
                "description": item.get("description"),
                "is_active": bool(
                    selected_space_summary and item["id"] == selected_space_summary["id"]
                ),
                "url": f"{request.url_for('knowledge_base')}?space={item['slug']}",
            }
        )

    selected_space_context: dict[str, object] | None = None
    document_tree: list[dict[str, object]] = []
    selected_document_context: dict[str, object] | None = None
    document_versions: list[dict[str, object]] = []
    document_breadcrumbs: list[dict[str, object]] = []

    selected_document_slug = document

    if selected_space_summary:
        created_iso = _format_datetime_for_display(selected_space_summary.get("created_at"))
        updated_iso = _format_datetime_for_display(selected_space_summary.get("updated_at"))
        selected_space_context = {
            "id": selected_space_summary["id"],
            "name": selected_space_summary["name"],
            "slug": selected_space_summary["slug"],
            "description": selected_space_summary.get("description"),
            "icon": _default_space_icon(selected_space_summary.get("icon")),
            "is_private": bool(selected_space_summary.get("is_private")),
            "document_count": int(selected_space_summary.get("document_count", 0)),
            "created_at_iso": created_iso,
            "updated_at_iso": updated_iso,
        }

        documents = await list_space_documents(
            session,
            space_id=selected_space_summary["id"],
            include_unpublished=True,
        )
        document_lookup = {doc.id: doc for doc in documents}

        if selected_document_slug:
            selected_doc_obj = next(
                (doc for doc in documents if doc.slug == selected_document_slug),
                None,
            )
        else:
            selected_doc_obj = documents[0] if documents else None
            if selected_doc_obj is not None:
                selected_document_slug = selected_doc_obj.slug

        tree_raw = build_knowledge_tree(documents)
        document_tree = _serialize_knowledge_tree(
            tree_raw,
            request=request,
            space_slug=selected_space_summary["slug"],
            selected_slug=selected_document_slug,
        )

        if selected_doc_obj is not None:
            selected_document_context = {
                "id": selected_doc_obj.id,
                "title": selected_doc_obj.title,
                "slug": selected_doc_obj.slug,
                "summary": selected_doc_obj.summary,
                "content": selected_doc_obj.content,
                "is_published": bool(selected_doc_obj.is_published),
                "status_label": "Published"
                if selected_doc_obj.is_published
                else "Draft",
                "version": selected_doc_obj.version,
                "created_by_id": selected_doc_obj.created_by_id,
                "created_at_iso": _format_datetime_for_display(selected_doc_obj.created_at),
                "updated_at_iso": _format_datetime_for_display(selected_doc_obj.updated_at),
                "published_at_iso": _format_datetime_for_display(selected_doc_obj.published_at),
            }

            revisions = await list_document_revisions(session, selected_doc_obj.id)
            document_versions = [
                {
                    "id": revision.id,
                    "version": revision.version,
                    "title": revision.title,
                    "summary": revision.summary,
                    "created_by_id": revision.created_by_id,
                    "created_at_iso": _format_datetime_for_display(revision.created_at),
                }
                for revision in revisions
            ]

            current = selected_doc_obj
            while current is not None:
                document_breadcrumbs.append(
                    {
                        "title": current.title,
                        "slug": current.slug,
                        "url": f"{request.url_for('knowledge_base')}?space={selected_space_summary['slug']}&document={current.slug}",
                    }
                )
                current = document_lookup.get(current.parent_id)
            document_breadcrumbs.reverse()

    context = await _template_context(
        request=request,
        session=session,
        page_title="Knowledge Base",
        page_subtitle="Organize operational playbooks, SOPs, and automation docs in one collaborative workspace.",
        active_nav="knowledge",
        knowledge_spaces=knowledge_spaces,
        selected_space=selected_space_context,
        document_tree=document_tree,
        selected_document=selected_document_context,
        document_versions=document_versions,
        document_breadcrumbs=document_breadcrumbs,
        has_spaces=bool(spaces_raw),
    )
    return templates.TemplateResponse("knowledge_base.html", context)


@app.get("/tickets", response_class=HTMLResponse, name="tickets")
async def tickets_view(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    seed_tickets = await fetch_ticket_records(now_utc)
    if request.query_params.get("new") == "1":
        redirect_url = request.url_for("ticket_new")
        return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    context = await _build_ticket_listing_context(
        request=request,
        session=session,
        now_utc=now_utc,
        tickets_raw=seed_tickets,
    )
    return templates.TemplateResponse("tickets.html", context)


@app.get("/tickets/new", response_class=HTMLResponse, name="ticket_new")
async def ticket_new_view(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    seed_tickets = await fetch_ticket_records(now_utc)
    context = await _build_ticket_create_context(
        request=request,
        session=session,
        now_utc=now_utc,
        tickets_raw=seed_tickets,
    )
    return templates.TemplateResponse("ticket_create.html", context)


@app.post("/tickets", response_class=HTMLResponse, name="ticket_create")
async def ticket_create_view(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    now_utc = datetime.now(timezone.utc)
    accepts_json = "application/json" in request.headers.get("accept", "").lower()
    content_type = request.headers.get("content-type", "").lower()
    expects_json = accepts_json or content_type.startswith("application/json")

    if content_type.startswith("application/json"):
        try:
            payload_data = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload.",
            ) from exc
        if not isinstance(payload_data, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload.",
            )
        raw_form = {field: str(payload_data.get(field, "")) for field in TICKET_FORM_FIELDS}
    else:
        raw_form = await _extract_form_data(request, TICKET_FORM_FIELDS)

    sanitized_form = {field: raw_form.get(field, "").strip() for field in TICKET_FORM_FIELDS}

    try:
        payload = TicketCreate(**sanitized_form)
    except ValidationError as exc:
        error_messages = _format_validation_errors(exc)
        if expects_json:
            detail_message = " ".join(error_messages) if error_messages else "Invalid ticket submission."
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": detail_message, "errors": error_messages},
            )

        seed_tickets = await fetch_ticket_records(now_utc)
        context = await _build_ticket_create_context(
            request=request,
            session=session,
            now_utc=now_utc,
            tickets_raw=seed_tickets,
            form_data=sanitized_form,
            form_errors=error_messages,
        )
        return templates.TemplateResponse(
            "ticket_create.html",
            context,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    seed_tickets = await fetch_ticket_records(now_utc)
    existing_ids = [ticket["id"] for ticket in seed_tickets]
    created_ticket = await ticket_store.create_ticket(
        **payload.dict(),
        existing_ids=existing_ids,
    )
    enriched_ticket = enrich_ticket_record(created_ticket, now_utc)

    await refresh_ticket_summary(session, enriched_ticket)

    await dispatch_ticket_event(
        session,
        event_type="Ticket Created",
        ticket_after=enriched_ticket,
        ticket_payload=payload.dict(),
    )

    await automation_dispatcher.dispatch(
        event_type="Ticket Created",
        ticket_id=enriched_ticket["id"],
        payload={
            "status": enriched_ticket.get("status"),
            "priority": enriched_ticket.get("priority"),
            "team": enriched_ticket.get("team"),
            "assignment": enriched_ticket.get("assignment"),
        },
    )

    detail_url = request.url_for("ticket_detail", ticket_id=enriched_ticket["id"])
    redirect_url = f"{detail_url}?created=1"

    if expects_json:
        response_payload = {
            "detail": "Ticket created successfully.",
            "ticket_id": enriched_ticket["id"],
            "ticket": {
                "id": enriched_ticket["id"],
                "subject": enriched_ticket.get("subject", ""),
                "customer": enriched_ticket.get("customer", ""),
                "customer_email": enriched_ticket.get("customer_email", ""),
                "status": enriched_ticket.get("status", ""),
                "priority": enriched_ticket.get("priority", ""),
                "team": enriched_ticket.get("team", ""),
                "assignment": enriched_ticket.get("assignment", ""),
                "queue": enriched_ticket.get("queue", ""),
                "category": enriched_ticket.get("category", ""),
                "summary": enriched_ticket.get("summary", ""),
                "channel": enriched_ticket.get("channel", ""),
                "labels": enriched_ticket.get("labels", []),
                "filter_tokens": enriched_ticket.get("filter_tokens", []),
                "status_token": enriched_ticket.get("status_token", ""),
                "priority_token": enriched_ticket.get("priority_token", ""),
                "assignment_token": enriched_ticket.get("assignment_token", ""),
                "last_reply_iso": enriched_ticket.get("last_reply_iso", ""),
                "age_display": enriched_ticket.get("age_display", ""),
                "detail_url": redirect_url,
            },
            "redirect_url": redirect_url,
        }
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_payload,
        )

    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


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
        session,
        ticket_id=ticket_id,
        saved=request.query_params.get("saved") == "1",
        reply_saved=request.query_params.get("reply") == "1",
        created=request.query_params.get("created") == "1",
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

    form_data = await _extract_form_data(request, TICKET_FORM_FIELDS)

    try:
        payload = TicketUpdate(**form_data)
    except ValidationError as exc:
        error_messages = _format_validation_errors(exc)
        sanitized_form_data = {
            key: form_data.get(key, "").strip() for key in TICKET_FORM_FIELDS
        }
        context = await _prepare_ticket_detail_context(
            request,
            now_utc,
            session,
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

    ticket_before = dict(ticket_lookup[ticket_id])
    ticket_update_payload = payload.dict()
    override = await ticket_store.update_ticket(ticket_id, **ticket_update_payload)

    ticket_after = dict(ticket_before)
    ticket_after.update(override)
    ticket_after["id"] = ticket_id
    enriched_after = enrich_ticket_record(ticket_after, now_utc)

    await refresh_ticket_summary(session, enriched_after)

    event_type = _derive_ticket_update_event_type(ticket_before, ticket_after)
    await dispatch_ticket_event(
        session,
        event_type=event_type,
        ticket_before=ticket_before,
        ticket_after=ticket_after,
        ticket_payload=ticket_update_payload,
    )

    redirect_url = request.url_for("ticket_detail", ticket_id=ticket_id)
    redirect_url = f"{redirect_url}?saved=1"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post(
    "/tickets/{ticket_id}/reply", response_class=HTMLResponse, name="ticket_reply"
)
async def ticket_reply_view(
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

    raw_form = await _extract_form_data(request, REPLY_FORM_FIELDS)

    checkbox_public = _normalize_checkbox(raw_form.get("public_reply"))
    checkbox_signature = _normalize_checkbox(raw_form.get("add_signature"))

    reply_payload = {
        "to": raw_form.get("to", "").strip(),
        "cc": raw_form.get("cc", "").strip(),
        "template": raw_form.get("template", "").strip(),
        "message": raw_form.get("message", ""),
        "public_reply": checkbox_public,
        "add_signature": checkbox_signature,
    }

    view_form_data = {
        "to": raw_form.get("to", "").strip(),
        "cc": raw_form.get("cc", "").strip(),
        "template": raw_form.get("template", "").strip(),
        "message": raw_form.get("message", ""),
        "public_reply": "on" if checkbox_public else "",
        "add_signature": "on" if checkbox_signature else "",
    }

    try:
        payload = TicketReply(**reply_payload)
    except ValidationError as exc:
        error_messages = _format_validation_errors(exc, REPLY_FIELD_LABELS)
        context = await _prepare_ticket_detail_context(
            request,
            now_utc,
            session,
            ticket_id=ticket_id,
            reply_form_data=view_form_data,
            reply_form_errors=error_messages,
        )
        context = await _template_context(session=session, **context)
        return templates.TemplateResponse(
            "ticket_detail.html",
            context,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    summary = _summarize_reply(payload.message)
    await ticket_store.append_reply(
        ticket_id,
        actor=DEFAULT_REPLY_ACTOR,
        channel=DEFAULT_REPLY_CHANNEL,
        summary=summary,
        message=payload.message,
    )

    await refresh_ticket_summary(session, ticket_lookup[ticket_id])

    redirect_url = request.url_for("ticket_detail", ticket_id=ticket_id)
    redirect_url = f"{redirect_url}?reply=1"
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
            "runbook_label": "Patch orchestration",
            "saves_hours": 86,
            "last_run_iso": (now_utc - timedelta(hours=6, minutes=12)).isoformat().replace("+00:00", "Z"),
        },
        {
            "runbook_label": "User provisioning",
            "saves_hours": 54,
            "last_run_iso": (now_utc - timedelta(days=1, hours=2)).isoformat().replace("+00:00", "Z"),
        },
        {
            "runbook_label": "Backup validation",
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

    runbook_labels = await _list_runbook_labels(session)

    context = await _template_context(
        request=request,
        session=session,
        page_title="Automation Control Tower",
        page_subtitle="Manage lifecycle automation and run secure platform updates.",
        active_nav="admin",
        active_admin="automation",
        scheduled_automations=scheduled_automations,
        event_automations=event_automations,
        runbook_labels=runbook_labels,
    )
    return templates.TemplateResponse("automation.html", context)


@app.get(
    "/automation/scheduled/new",
    response_class=HTMLResponse,
    name="automation_create_scheduled",
)
async def automation_create_scheduled_view(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    automation_view = _empty_automation_view("scheduled")
    runbook_labels = await _list_runbook_labels(session)

    context = await _template_context(
        request=request,
        session=session,
        page_title="Create scheduled automation",
        page_subtitle="Configure cadence, metadata, and monitoring for a new scheduled runbook.",
        active_nav="admin",
        active_admin="automation",
        automation=automation_view,
        cron_reference_url=CRON_REFERENCE_URL,
        event_trigger_options=EVENT_TRIGGER_OPTIONS,
        trigger_operator_options=TRIGGER_OPERATOR_OPTIONS,
        value_required_trigger_options=sorted(VALUE_REQUIRED_TRIGGER_OPTIONS),
        runbook_labels=runbook_labels,
        is_new=True,
    )
    return templates.TemplateResponse("automation_edit_scheduled.html", context)


@app.get(
    "/automation/event/new",
    response_class=HTMLResponse,
    name="automation_create_event",
)
async def automation_create_event_view(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    automation_view = _empty_automation_view("event")
    runbook_labels = await _list_runbook_labels(session)

    context = await _template_context(
        request=request,
        session=session,
        page_title="Create event automation",
        page_subtitle="Choose platform triggers and response actions for a new event playbook.",
        active_nav="admin",
        active_admin="automation",
        automation=automation_view,
        event_trigger_options=EVENT_TRIGGER_OPTIONS,
        trigger_operator_options=TRIGGER_OPERATOR_OPTIONS,
        value_required_trigger_options=sorted(VALUE_REQUIRED_TRIGGER_OPTIONS),
        automation_actions=[
            {"name": action, "slug": slugify_label(action)}
            for action in EVENT_AUTOMATION_ACTIONS
        ],
        runbook_labels=runbook_labels,
        is_new=True,
    )
    return templates.TemplateResponse("automation_edit_event.html", context)


CRON_REFERENCE_URL = "https://crontab.guru/"


@app.get(
    "/automation/scheduled/{automation_id}",
    response_class=HTMLResponse,
    name="automation_edit_scheduled",
)
async def automation_edit_scheduled_view(
    request: Request,
    automation_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    automation = await _load_automation(session, automation_id)
    if automation.kind != "scheduled":
        raise HTTPException(status_code=404, detail="Automation not found")

    automation_view = _automation_to_view_model(automation)
    runbook_labels = await _list_runbook_labels(session)

    context = await _template_context(
        request=request,
        session=session,
        page_title="Scheduled automation editor",
        page_subtitle=(
            f"Define secure cron scheduling for {automation_view['name']}."
        ),
        active_nav="admin",
        active_admin="automation",
        automation=automation_view,
        cron_reference_url=CRON_REFERENCE_URL,
        event_trigger_options=EVENT_TRIGGER_OPTIONS,
        trigger_operator_options=TRIGGER_OPERATOR_OPTIONS,
        value_required_trigger_options=sorted(VALUE_REQUIRED_TRIGGER_OPTIONS),
        runbook_labels=runbook_labels,
    )
    return templates.TemplateResponse("automation_edit_scheduled.html", context)


@app.get(
    "/automation/event/{automation_id}",
    response_class=HTMLResponse,
    name="automation_edit_event",
)
async def automation_edit_event_view(
    request: Request,
    automation_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    automation = await _load_automation(session, automation_id)
    if automation.kind != "event":
        raise HTTPException(status_code=404, detail="Automation not found")

    automation_view = _automation_to_view_model(automation)
    runbook_labels = await _list_runbook_labels(session)

    context = await _template_context(
        request=request,
        session=session,
        page_title="Event automation editor",
        page_subtitle=(
            f"Map platform signals to responsive actions for {automation_view['name']}."
        ),
        active_nav="admin",
        active_admin="automation",
        automation=automation_view,
        event_trigger_options=EVENT_TRIGGER_OPTIONS,
        trigger_operator_options=TRIGGER_OPERATOR_OPTIONS,
        value_required_trigger_options=sorted(VALUE_REQUIRED_TRIGGER_OPTIONS),
        automation_actions=[
            {"name": action, "slug": slugify_label(action)}
            for action in EVENT_AUTOMATION_ACTIONS
        ],
        runbook_labels=runbook_labels,
    )
    return templates.TemplateResponse("automation_edit_event.html", context)


@app.get("/automation/{automation_id}", response_class=HTMLResponse, name="automation_edit")
async def automation_edit_redirect(
    request: Request,
    automation_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    automation = await _load_automation(session, automation_id)
    if automation.kind == "scheduled":
        target = request.url_for(
            "automation_edit_scheduled", automation_id=str(automation.id)
        )
    elif automation.kind == "event":
        target = request.url_for(
            "automation_edit_event", automation_id=str(automation.id)
        )
    else:
        raise HTTPException(status_code=404, detail="Automation not found")

    return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


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

    https_post_webhook_endpoint = None
    if module.slug == "https-post-receiver":
        https_post_webhook_endpoint = request.url_for("receive_https_post_webhook")

    context = await _template_context(
        request=request,
        session=session,
        page_title=f"{module.name} integration",
        page_subtitle=module.description
        or "Configure secure access, credentials, and automation hooks for this integration.",
        module=module_info,
        settings_fields=settings_fields,
        https_post_webhook_endpoint=https_post_webhook_endpoint,
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


@app.get("/admin/api-docs", response_class=HTMLResponse, name="admin_api_docs")
async def admin_api_docs(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    swagger_url = request.url_for("api_docs_swagger_ui")
    schema_url = request.url_for("openapi")
    context = await _template_context(
        request=request,
        session=session,
        page_title="CURD API Documentation",
        page_subtitle="Explore authenticated endpoints and sample payloads for Tactical Desk.",
        active_nav="docs",
        active_docs="api_docs",
        swagger_url=swagger_url,
        schema_url=schema_url,
    )
    return templates.TemplateResponse("api_docs.html", context)


@app.get(
    "/docs/ticket-variables",
    response_class=HTMLResponse,
    name="docs_ticket_variables",
)
async def docs_ticket_variables(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    context = await _template_context(
        request=request,
        session=session,
        page_title="Ticket template variables",
        page_subtitle=(
            "Review dynamic placeholders that can be merged into ticket actions and notifications, and wrap keys in "
            "double curly braces (for example {{ ticket.subject }}) when composing automation content."
        ),
        active_nav="docs",
        active_docs="ticket_variables",
        automation_template_variables=AUTOMATION_TEMPLATE_VARIABLES,
    )
    return templates.TemplateResponse("docs_ticket_variables.html", context)


@app.get(
    "/docs/https-post-variables",
    response_class=HTMLResponse,
    name="docs_https_post_variables",
)
async def docs_https_post_variables(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    context = await _template_context(
        request=request,
        session=session,
        page_title="HTTPS POST webhook variables",
        page_subtitle=(
            "Reference standardized HTTPS POST payload fields that Tactical Desk exposes to automations "
            "and notifications when external systems post data."
        ),
        active_nav="docs",
        active_docs="https_post_variables",
        http_post_template_variables=HTTP_POST_TEMPLATE_VARIABLES,
    )
    return templates.TemplateResponse("docs_http_post_variables.html", context)


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
        "module_slug": delivery.module_slug,
        "request_method": delivery.request_method,
        "request_url": delivery.request_url,
        "request_payload": delivery.request_payload,
        "status": delivery.status,
        "status_label": status_label,
        "response_status_code": delivery.response_status_code,
        "response_payload": delivery.response_payload,
        "error_message": delivery.error_message,
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
            module_slug="syncro-rmm",
            request_method="POST",
            request_url="https://hooks.tacticalrmm.local/notify",
            request_payload={"sample": True},
            status=WebhookStatus.RETRYING.value,
            response_status_code=503,
            response_payload={"detail": "Upstream maintenance window"},
            error_message="Service unavailable",
            last_attempt_at=now - timedelta(minutes=5),
            next_retry_at=now + timedelta(minutes=5),
        ),
        WebhookDelivery(
            event_id="whk-511",
            endpoint="https://hooks.syncro.local/tickets",
            module_slug="syncro-rmm",
            request_method="POST",
            request_url="https://hooks.syncro.local/tickets",
            request_payload={"ticket": {"id": 42}},
            status=WebhookStatus.PAUSED.value,
            response_status_code=200,
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
    for entry in webhook_failures:
        entry["result_url"] = request.url_for(
            "admin_webhook_result", webhook_id=entry["id"]
        )
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


@app.get(
    "/admin/webhooks/{webhook_id}/result",
    response_class=HTMLResponse,
    name="admin_webhook_result",
)
async def admin_webhook_result(
    request: Request,
    webhook_id: str,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    delivery = await _get_webhook_delivery_or_404(session, webhook_id)
    webhook = _serialize_webhook(delivery)
    context = {
        "request": request,
        "webhook": webhook,
    }
    return templates.TemplateResponse("webhook_result.html", context)


async def _get_webhook_delivery_or_404(
    session: AsyncSession, webhook_id: str
) -> WebhookDelivery:
    result = await session.execute(
        select(WebhookDelivery).where(WebhookDelivery.event_id == webhook_id)
    )
    delivery = result.scalar_one_or_none()
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return delivery


@app.get("/health", tags=["System"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
