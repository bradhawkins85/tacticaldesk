from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tickets import StoredTicketRecord, ticket_store
from app.models import IntegrationModule, Organization, utcnow


class SyncroConfigurationError(Exception):
    """Raised when the Syncro integration is not configured for imports."""


class SyncroAPIError(Exception):
    """Raised when a Syncro API request fails."""


@dataclass
class SyncroImportSummary:
    companies_created: int
    companies_updated: int
    tickets_imported: int
    tickets_skipped: int
    last_synced_at: datetime


@dataclass(frozen=True)
class SyncroCompanyRecord:
    external_id: int
    name: str
    slug: str
    description: str | None
    contact_email: str | None


@dataclass(frozen=True)
class SyncroTicketImportOptions:
    mode: str = "all"
    ticket_number: int | None = None
    range_start: int | None = None
    range_end: int | None = None


_DEFAULT_PAGE_SIZE = 100
_MAX_PAGES = 20
_DEFAULT_THROTTLE_SECONDS = 0.25


def _slugify(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return "-".join(tokens)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_email(value: Any) -> str | None:
    candidate = _clean_text(value)
    if not candidate or "@" not in candidate:
        return None
    return candidate


def _parse_datetime(value: Any, *, default: datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = _clean_text(value)
        if not text:
            return default
        if text.isdigit():
            try:
                timestamp = int(text)
            except ValueError:
                return default
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        else:
            normalized = text.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError:
                return default
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_collection(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if key in payload and isinstance(payload[key], list):
            return [item for item in payload[key] if isinstance(item, dict)]
        if "data" in payload and isinstance(payload["data"], list):
            return [item for item in payload["data"] if isinstance(item, dict)]
    return []


async def _throttled_get(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    params: dict[str, Any] | None = None,
    throttle: float = 0.0,
) -> httpx.Response:
    try:
        response = await client.get(endpoint, params=params)
    except httpx.HTTPError as exc:  # pragma: no cover - defensive network guard
        raise SyncroAPIError(f"Syncro request failed: {exc}") from exc
    if throttle > 0:
        await asyncio.sleep(throttle)
    return response


async def _fetch_paginated(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    collection_key: str,
    throttle: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page = 1
    while page <= _MAX_PAGES:
        response = await _throttled_get(
            client,
            endpoint,
            params={"page": page, "per_page": _DEFAULT_PAGE_SIZE},
            throttle=throttle,
        )
        if response.status_code >= 400:
            detail = response.text
            raise SyncroAPIError(
                f"Syncro request to {endpoint} failed with status {response.status_code}: {detail}"
            )
        payload = response.json()
        batch = _extract_collection(payload, collection_key)
        results.extend(batch)
        if len(batch) < _DEFAULT_PAGE_SIZE:
            break
        if isinstance(payload, dict):
            meta = payload.get("meta") or payload.get("pagination") or {}
            next_page = meta.get("next_page") or meta.get("next")
            total_pages = meta.get("total_pages") or meta.get("total_pages_count")
            if next_page in (None, False, 0) and not total_pages:
                break
            if isinstance(total_pages, int) and page >= total_pages:
                break
            if isinstance(next_page, int):
                page = next_page
                continue
        page += 1
    return results


def _coerce_company_id(record: dict[str, Any]) -> int | None:
    for key in ("id", "customer_id", "customerID", "customerId"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _normalize_company(record: dict[str, Any]) -> SyncroCompanyRecord | None:
    external_id = _coerce_company_id(record)
    if external_id is None:
        return None

    name = _clean_text(
        record.get("business_name")
        or record.get("name")
        or record.get("company_name")
    )
    if not name:
        return None

    contact_email = None
    primary_contact = record.get("primary_contact")
    if isinstance(primary_contact, dict):
        contact_email = _clean_email(
            primary_contact.get("email")
            or primary_contact.get("primary_email")
        )
    contact_email = contact_email or _clean_email(record.get("email"))

    description_parts: list[str] = []
    notes = _clean_text(record.get("notes") or record.get("description"))
    if notes:
        description_parts.append(notes)
    address = record.get("address")
    if isinstance(address, dict):
        line_1 = _clean_text(address.get("address1"))
        city = _clean_text(address.get("city"))
        state = _clean_text(address.get("state"))
        postal = _clean_text(address.get("zip"))
        components = [line_1, city, state, postal]
        address_line = ", ".join(part for part in components if part)
        if address_line:
            description_parts.append(address_line)

    description = "\n".join(description_parts) if description_parts else None

    base_slug = _slugify(name) or f"syncro-company-{record.get('id', '')}".strip("-")
    if not base_slug:
        base_slug = "syncro-company"

    slug = base_slug
    if slug:
        slug = slug[:255]

    return SyncroCompanyRecord(
        external_id=external_id,
        name=name,
        slug=slug,
        description=description,
        contact_email=contact_email,
    )


def _normalize_ticket(record: dict[str, Any], *, now: datetime) -> StoredTicketRecord | None:
    ticket_identifier = _clean_text(
        record.get("number")
        or record.get("ticket_number")
        or record.get("ticket_id")
        or record.get("id")
    )
    if not ticket_identifier:
        return None

    normalized_identifier = ticket_identifier.lstrip("#").strip()
    if normalized_identifier.upper().startswith("TD-"):
        normalized_identifier = normalized_identifier[3:]
    if normalized_identifier.upper().startswith("SYNCRO-"):
        normalized_identifier = normalized_identifier[7:]
    normalized_identifier = normalized_identifier.lstrip("-")
    normalized_identifier = normalized_identifier.replace(" ", "")
    normalized_identifier = normalized_identifier or ticket_identifier

    customer_name = ""
    customer_email = _clean_email(record.get("customer_email"))
    customer = record.get("customer") or record.get("company")
    if isinstance(customer, dict):
        customer_name = _clean_text(
            customer.get("business_name")
            or customer.get("name")
            or customer.get("company_name")
        )
        customer_email = customer_email or _clean_email(
            customer.get("email") or customer.get("primary_contact_email")
        )
    customer_name = customer_name or _clean_text(record.get("customer_name"))
    if not customer_name:
        customer_name = "Syncro Customer"
    if not customer_email:
        customer_email = f"support+{ticket_identifier}@syncro.local"

    subject = _clean_text(record.get("subject") or record.get("title"))
    if not subject:
        subject = f"Ticket {ticket_identifier}"

    summary = _clean_text(record.get("description") or record.get("problem")) or subject

    status = _clean_text(record.get("status")) or "Open"
    priority = _clean_text(record.get("priority")) or "Normal"
    assignment = _clean_text(record.get("assigned_tech_name") or record.get("assigned_to"))
    if not assignment:
        assignment = "Unassigned"
    queue = _clean_text(record.get("queue_name") or record.get("board")) or "Syncro"
    team = _clean_text(record.get("team")) or "Syncro Desk"
    category = _clean_text(record.get("type")) or "Syncro"

    created_at = _parse_datetime(record.get("created_at"), default=now)
    last_reply = _parse_datetime(record.get("updated_at"), default=created_at)
    due_at_raw = record.get("due_at") or record.get("due_date")
    due_at = _parse_datetime(due_at_raw, default=last_reply) if due_at_raw else None

    tags: Iterable[Any]
    tags = []
    raw_tags = record.get("tags")
    if isinstance(raw_tags, list):
        tags = raw_tags
    elif isinstance(raw_tags, str):
        tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
    labels = [str(tag) for tag in tags][:10]

    cc_emails = record.get("cc_emails") or record.get("cc")
    watchers: list[str] = []
    if isinstance(cc_emails, list):
        for email in cc_emails:
            cleaned_email = _clean_email(email)
            if cleaned_email:
                watchers.append(cleaned_email)
    if watchers:
        seen = set()
        unique_watchers: list[str] = []
        for email in watchers:
            if email in seen:
                continue
            seen.add(email)
            unique_watchers.append(email)
        watchers = unique_watchers

    note_body = summary
    public = bool(record.get("is_public", True))
    history = [
        {
            "actor": assignment if assignment else "Syncro Technician",
            "direction": "inbound" if public else "internal",
            "channel": "Syncro",
            "summary": subject,
            "body": note_body or subject,
            "timestamp_dt": last_reply,
        }
    ]

    ticket_id_raw = normalized_identifier or ticket_identifier
    ticket_id_clean = re.sub(r"[^0-9A-Za-z_-]", "", ticket_id_raw)
    ticket_id_clean = ticket_id_clean or normalized_identifier or ticket_identifier
    ticket_id = f"SYNCRO-{ticket_id_clean}"[:64]

    return StoredTicketRecord(
        id=ticket_id,
        subject=subject,
        customer=customer_name,
        customer_email=customer_email,
        status=status,
        priority=priority,
        team=team,
        assignment=assignment,
        queue=queue,
        category=category,
        summary=summary,
        channel="Syncro",
        created_at_dt=created_at,
        last_reply_dt=last_reply,
        due_at_dt=due_at,
        labels=labels,
        watchers=watchers,
        is_starred=bool(record.get("starred") or record.get("is_flagged")),
        assets_visible=bool(record.get("has_asset") or record.get("assets_visible")),
        history=history,
        metadata_created_at_dt=now,
        metadata_updated_at_dt=now,
    )


async def _sync_companies(
    session: AsyncSession, companies: Iterable[SyncroCompanyRecord]
) -> tuple[int, int]:
    created = 0
    updated = 0
    seen_slugs: set[str] = set()

    for company in companies:
        slug = company.slug
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        result = await session.execute(
            select(Organization).where(Organization.slug == slug)
        )
        organization = result.scalar_one_or_none()
        if organization is None:
            organization = Organization(
                name=company.name,
                slug=slug,
                description=company.description,
                contact_email=company.contact_email,
                is_archived=False,
            )
            session.add(organization)
            created += 1
            continue

        changed = False
        if company.name and organization.name != company.name:
            organization.name = company.name
            changed = True
        if organization.description != company.description:
            organization.description = company.description
            changed = True
        if organization.contact_email != company.contact_email:
            organization.contact_email = company.contact_email
            changed = True
        if organization.is_archived:
            organization.is_archived = False
            changed = True
        if changed:
            organization.updated_at = utcnow()
            updated += 1

    if created or updated:
        await session.commit()

    return created, updated


async def _load_syncro_client_config(session: AsyncSession) -> tuple[str, dict[str, str], httpx.Timeout]:
    result = await session.execute(
        select(IntegrationModule).where(IntegrationModule.slug == "syncro-rmm")
    )
    module = result.scalar_one_or_none()
    if module is None or not module.enabled:
        raise SyncroConfigurationError(
            "Syncro integration is disabled or not configured. Enable the module to import data."
        )

    settings = dict(module.settings or {})
    base_url = _clean_text(settings.get("base_url"))
    api_key = _clean_text(settings.get("api_key"))
    if not base_url or not api_key:
        raise SyncroConfigurationError(
            "Syncro integration requires a base URL and API key before running an import."
        )

    if base_url.endswith("/"):
        base_url = base_url[:-1]

    headers = {
        "Accept": "application/json",
        "X-API-Key": api_key,
    }

    timeout = httpx.Timeout(30.0, connect=10.0)

    return base_url, headers, timeout


def _sanitize_throttle(throttle_seconds: float | None) -> float:
    if throttle_seconds is None:
        return _DEFAULT_THROTTLE_SECONDS
    return max(0.0, throttle_seconds)


def _determine_ticket_numbers(options: SyncroTicketImportOptions) -> Sequence[str]:
    mode = (options.mode or "all").strip().lower()
    if mode == "single":
        if options.ticket_number is None:
            return []
        return [str(options.ticket_number)]
    if mode == "range":
        if options.range_start is None or options.range_end is None:
            return []
        start = options.range_start
        end = options.range_end
        if end < start:
            start, end = end, start
        return [str(value) for value in range(start, end + 1)]
    return []


async def _collect_tickets(
    client: httpx.AsyncClient,
    options: SyncroTicketImportOptions,
    *,
    throttle: float,
) -> list[dict[str, Any]]:
    mode = (options.mode or "all").strip().lower()
    if mode == "all":
        return await _fetch_paginated(
            client,
            "/api/v1/tickets",
            collection_key="tickets",
            throttle=throttle,
        )

    tickets: list[dict[str, Any]] = []
    seen_identifiers: set[str] = set()
    for ticket_number in _determine_ticket_numbers(options):
        endpoint = f"/api/v1/tickets/{ticket_number}"
        response = await _throttled_get(client, endpoint, throttle=throttle)
        if response.status_code == 404:
            continue
        if response.status_code >= 400:
            detail = response.text
            raise SyncroAPIError(
                f"Syncro request to {endpoint} failed with status {response.status_code}: {detail}"
            )
        payload = response.json()
        record: dict[str, Any] | None = None
        if isinstance(payload, dict):
            if isinstance(payload.get("ticket"), dict):
                record = payload["ticket"]
            elif isinstance(payload.get("data"), dict):
                record = payload["data"]
            elif payload:
                record = payload
        if record is None:
            continue
        identifier = _clean_text(
            record.get("number")
            or record.get("ticket_number")
            or record.get("ticket_id")
            or record.get("id")
            or ticket_number
        )
        if identifier in seen_identifiers:
            continue
        seen_identifiers.add(identifier)
        tickets.append(record)
    return tickets


async def fetch_syncro_companies(
    session: AsyncSession,
    *,
    transport: httpx.BaseTransport | None = None,
    throttle_seconds: float | None = None,
) -> list[SyncroCompanyRecord]:
    base_url, headers, timeout = await _load_syncro_client_config(session)
    throttle = _sanitize_throttle(throttle_seconds)

    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        transport=transport,
    ) as client:
        payload = await _fetch_paginated(
            client,
            "/api/v1/customers",
            collection_key="customers",
            throttle=throttle,
        )

    companies: list[SyncroCompanyRecord] = []
    for record in payload:
        normalized = _normalize_company(record)
        if normalized:
            companies.append(normalized)
    return companies


async def import_syncro_data(
    session: AsyncSession,
    *,
    company_ids: Iterable[int] | None = None,
    ticket_options: SyncroTicketImportOptions | None = None,
    transport: httpx.BaseTransport | None = None,
    throttle_seconds: float | None = None,
) -> SyncroImportSummary:
    base_url, headers, timeout = await _load_syncro_client_config(session)
    throttle = _sanitize_throttle(throttle_seconds)

    selected_company_ids = None
    if company_ids is not None:
        selected_company_ids = {int(value) for value in company_ids}

    ticket_selection = ticket_options or SyncroTicketImportOptions()

    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        transport=transport,
    ) as client:
        companies_payload = await _fetch_paginated(
            client,
            "/api/v1/customers",
            collection_key="customers",
            throttle=throttle,
        )
        tickets_payload = await _collect_tickets(
            client,
            ticket_selection,
            throttle=throttle,
        )

    normalized_companies: list[SyncroCompanyRecord] = []
    for record in companies_payload:
        normalized = _normalize_company(record)
        if not normalized:
            continue
        if selected_company_ids is not None and normalized.external_id not in selected_company_ids:
            continue
        normalized_companies.append(normalized)

    companies_created, companies_updated = await _sync_companies(
        session, normalized_companies
    )

    now = utcnow()
    ticket_records: list[StoredTicketRecord] = []
    skipped = 0
    for ticket in tickets_payload:
        record = _normalize_ticket(ticket, now=now)
        if record is None:
            skipped += 1
            continue
        ticket_records.append(record)

    await ticket_store.sync_external_records("syncro", ticket_records)

    return SyncroImportSummary(
        companies_created=companies_created,
        companies_updated=companies_updated,
        tickets_imported=len(ticket_records),
        tickets_skipped=skipped,
        last_synced_at=now,
    )

