from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import auth as auth_router
from app.api.routers import maintenance as maintenance_router
from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine, get_session
from app.models import User

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
app.include_router(maintenance_router.router)


def _template_context(**extra: object) -> dict[str, object]:
    current_settings = get_settings()
    context: dict[str, object] = {
        "app_name": current_settings.app_name,
        "current_year": datetime.now(timezone.utc).year,
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

    context = _template_context(
        request=request,
        page_title=page_title,
        page_subtitle=page_subtitle,
        user_count=user_count,
    )
    return templates.TemplateResponse(template_name, context)


@app.get("/dashboard", response_class=HTMLResponse, name="dashboard")
async def dashboard(request: Request) -> HTMLResponse:
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

    context = _template_context(
        request=request,
        page_title="Operations Command Center",
        page_subtitle="Unify omnichannel tickets, automation, and Tactical RMM telemetry.",
        tickets=tickets,
        webhook_metrics=webhook_metrics,
        active_nav="dashboard",
    )
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/tickets", response_class=HTMLResponse, name="tickets")
async def tickets_view(request: Request) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    queue_health = [
        {
            "queue": "Critical response",
            "open": 7,
            "waiting": 2,
            "sla_breaches": 1,
            "oldest_iso": (now_utc - timedelta(hours=3, minutes=41)).isoformat().replace("+00:00", "Z"),
        },
        {
            "queue": "Service requests",
            "open": 18,
            "waiting": 6,
            "sla_breaches": 0,
            "oldest_iso": (now_utc - timedelta(hours=1, minutes=5)).isoformat().replace("+00:00", "Z"),
        },
        {
            "queue": "Automation handoff",
            "open": 5,
            "waiting": 1,
            "sla_breaches": 0,
            "oldest_iso": (now_utc - timedelta(minutes=47)).isoformat().replace("+00:00", "Z"),
        },
    ]

    escalation_pipeline = [
        {
            "ticket": "INC-4821",
            "owner": "Tier 2",
            "next_step": "Vendor engagement",
            "eta_iso": (now_utc + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        },
        {
            "ticket": "SR-1954",
            "owner": "Automation",
            "next_step": "Awaiting customer MFA reset",
            "eta_iso": (now_utc + timedelta(hours=5, minutes=30)).isoformat().replace("+00:00", "Z"),
        },
        {
            "ticket": "CHG-2240",
            "owner": "Change advisory",
            "next_step": "CAB approval window",
            "eta_iso": (now_utc + timedelta(days=1, hours=3)).isoformat().replace("+00:00", "Z"),
        },
    ]

    context = _template_context(
        request=request,
        page_title="Unified Ticket Workspace",
        page_subtitle="Track queues, escalations, and SLA risk across every service channel.",
        queue_health=queue_health,
        escalation_pipeline=escalation_pipeline,
        active_nav="tickets",
    )
    return templates.TemplateResponse("tickets.html", context)


@app.get("/analytics", response_class=HTMLResponse, name="analytics")
async def analytics_view(request: Request) -> HTMLResponse:
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

    context = _template_context(
        request=request,
        page_title="Analytics Observatory",
        page_subtitle="Surface operational insights, response trends, and automation ROI.",
        monthly_summary=monthly_summary,
        automation_roi=automation_roi,
        active_nav="analytics",
    )
    return templates.TemplateResponse("analytics.html", context)


@app.get("/automation", response_class=HTMLResponse, name="automation")
async def automation_view(request: Request) -> HTMLResponse:
    now_utc = datetime.now(timezone.utc)
    orchestration_runs = [
        {
            "workflow": "Critical patch rollup",
            "status": "Completed",
            "duration_minutes": 18,
            "finished_iso": (now_utc - timedelta(minutes=22)).isoformat().replace("+00:00", "Z"),
        },
        {
            "workflow": "Endpoint isolation",
            "status": "Running",
            "duration_minutes": 7,
            "finished_iso": "",
        },
        {
            "workflow": "Axcelerate sync",
            "status": "Queued",
            "duration_minutes": 0,
            "finished_iso": "",
        },
    ]

    module_toggles = [
        {"module": "SyncroRMM", "enabled": True},
        {"module": "Axcelerate", "enabled": False},
        {"module": "TacticalRMM", "enabled": True},
        {"module": "Xero", "enabled": False},
    ]

    context = _template_context(
        request=request,
        page_title="Automation Control Tower",
        page_subtitle="Launch workflows, monitor orchestration, and govern integration access.",
        orchestration_runs=orchestration_runs,
        module_toggles=module_toggles,
        active_nav="automation",
    )
    return templates.TemplateResponse("automation.html", context)


@app.get("/admin/maintenance", response_class=HTMLResponse, name="maintenance")
async def maintenance(request: Request) -> HTMLResponse:
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
    now_utc = datetime.now(timezone.utc)
    webhook_failures = [
        {
            "id": "whk-512",
            "endpoint": "https://hooks.tacticalrmm.local/notify",
            "status": "retrying",
            "last_attempt": (now_utc - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            "next_retry": (now_utc + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        },
        {
            "id": "whk-511",
            "endpoint": "https://hooks.syncro.local/tickets",
            "status": "paused",
            "last_attempt": (now_utc - timedelta(hours=1, minutes=12)).isoformat().replace("+00:00", "Z"),
            "next_retry": (now_utc + timedelta(minutes=3)).isoformat().replace("+00:00", "Z"),
        },
    ]
    current_settings = get_settings()
    context = _template_context(
        request=request,
        page_title="Automation & Deployment",
        page_subtitle="Trigger provisioning workflows and monitor maintenance automation.",
        maintenance_scripts=scripts,
        installers_enabled=current_settings.enable_installers,
        webhook_failures=webhook_failures,
        active_nav="admin",
    )
    return templates.TemplateResponse("maintenance.html", context)


@app.get("/health", tags=["System"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
