from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation_dispatcher import automation_dispatcher
from app.core.db import get_session
from app.core.tickets import ticket_store
from app.schemas import TicketCreate, TicketCreateResponse
from app.services import dispatch_ticket_event
from app.services.ticket_data import enrich_ticket_record, fetch_ticket_records

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])


@router.post("/", response_model=TicketCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TicketCreateResponse:
    now_utc = datetime.now(timezone.utc)
    seed_tickets = await fetch_ticket_records(now_utc)
    existing_ids = [ticket["id"] for ticket in seed_tickets]

    created_ticket = await ticket_store.create_ticket(
        **payload.dict(),
        existing_ids=existing_ids,
    )
    enriched_ticket = enrich_ticket_record(created_ticket, now_utc)

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
    ticket_payload = {
        **{key: enriched_ticket.get(key) for key in (
            "id",
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
            "channel",
            "labels",
            "filter_tokens",
            "status_token",
            "priority_token",
            "assignment_token",
            "last_reply_iso",
            "age_display",
        )},
        "detail_url": redirect_url,
    }

    response = TicketCreateResponse(
        detail="Ticket created successfully.",
        ticket_id=enriched_ticket["id"],
        ticket=ticket_payload,
        redirect_url=redirect_url,
    )
    return response
