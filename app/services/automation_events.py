"""Automation event dispatcher utilities."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation_dispatcher import automation_dispatcher
from app.core.automations import VALUE_REQUIRED_TRIGGER_OPTIONS
from app.core.template_variables import (
    build_ticket_variable_context,
    render_template_value,
)
from app.models import Automation, utcnow
from app.schemas import (
    AutomationTicketAction,
    AutomationTriggerCondition,
    AutomationTriggerFilter,
)
from app.services.notifications import send_ntfy_notification

EventContext = dict[str, Any]


def _normalize_text(value: Any | None) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


def _compare_values(operator: str | None, actual: Any | None, expected: Any | None) -> bool:
    if actual is None or expected is None:
        return False
    actual_normalized = _normalize_text(actual)
    expected_normalized = _normalize_text(expected)
    if not operator or operator == "equals":
        return actual_normalized == expected_normalized
    if operator == "not_equals":
        return actual_normalized != expected_normalized
    if operator == "contains":
        return expected_normalized in actual_normalized
    return False


def _resolve_ticket_field(context: EventContext, field: str) -> str | None:
    ticket_after = context.get("ticket_after", {})
    value = ticket_after.get(field)
    if value is None:
        return None
    return str(value)


def _evaluate_status_changed(condition: AutomationTriggerCondition, context: EventContext) -> bool:
    ticket_before = context.get("ticket_before", {})
    ticket_after = context.get("ticket_after", {})
    before_status = ticket_before.get("status")
    after_status = ticket_after.get("status")
    if condition.type == "Ticket Status Changed":
        return _normalize_text(before_status) != _normalize_text(after_status)
    if condition.type == "Ticket Status Changed To":
        if _normalize_text(before_status) == _normalize_text(after_status):
            return False
        return _compare_values(condition.operator, after_status, condition.value)
    if condition.type == "Ticket Status Changed From":
        if _normalize_text(before_status) == _normalize_text(after_status):
            return False
        return _compare_values(condition.operator, before_status, condition.value)
    return False


_VALUE_RESOLVERS: dict[str, Callable[[EventContext], str | None]] = {
    "Assigned to": lambda context: _resolve_ticket_field(context, "assignment"),
    "Customer": lambda context: _resolve_ticket_field(context, "customer"),
    "Ticket Priority": lambda context: _resolve_ticket_field(context, "priority"),
    "Ticket Status": lambda context: _resolve_ticket_field(context, "status"),
    "Ticket Subject": lambda context: _resolve_ticket_field(context, "subject"),
    "Ticket Type": lambda context: _resolve_ticket_field(context, "category"),
    "Ticket Status Changed To": lambda context: _resolve_ticket_field(context, "status"),
    "Ticket Status Changed From": lambda context: context.get("ticket_before", {}).get("status"),
}


def _condition_matches(condition: AutomationTriggerCondition, context: EventContext) -> bool:
    if condition.type in {
        "Ticket Status Changed",
        "Ticket Status Changed To",
        "Ticket Status Changed From",
    }:
        return _evaluate_status_changed(condition, context)

    if condition.type in VALUE_REQUIRED_TRIGGER_OPTIONS:
        resolver = _VALUE_RESOLVERS.get(condition.type)
        if resolver is None:
            return False
        actual_value = resolver(context)
        return _compare_values(condition.operator, actual_value, condition.value)

    event_type = context.get("event_type")
    return _normalize_text(condition.type) == _normalize_text(event_type)


def _filter_matches(filters: AutomationTriggerFilter, context: EventContext) -> bool:
    evaluations = [_condition_matches(condition, context) for condition in filters.conditions]
    if not evaluations:
        return False
    if filters.match == "all":
        return all(evaluations)
    return any(evaluations)


def _automation_matches(automation: Automation, context: EventContext) -> bool:
    filters_model: AutomationTriggerFilter | None = None
    if automation.trigger_filters:
        try:
            filters_model = AutomationTriggerFilter.parse_obj(automation.trigger_filters)
        except ValidationError:
            filters_model = None
    if filters_model:
        return _filter_matches(filters_model, context)
    if automation.trigger:
        return _normalize_text(automation.trigger) == _normalize_text(context.get("event_type"))
    return False


async def dispatch_ticket_event(
    session: AsyncSession,
    *,
    event_type: str,
    ticket_before: dict[str, Any] | None = None,
    ticket_after: dict[str, Any] | None = None,
    ticket_payload: dict[str, Any] | None = None,
) -> list[Automation]:
    """Evaluate ticket-driven automations and update trigger metadata."""

    context: EventContext = {
        "event_type": event_type,
        "ticket_before": ticket_before or {},
        "ticket_after": ticket_after or {},
        "ticket_payload": ticket_payload or {},
    }

    result = await session.execute(
        select(Automation).where(Automation.kind == "event")
    )
    automations: Iterable[Automation] = result.scalars().all()

    triggered: list[Automation] = []
    triggered_at = utcnow()
    variable_context = build_ticket_variable_context(
        event_type=event_type,
        triggered_at=triggered_at,
        ticket_before=context.get("ticket_before"),
        ticket_after=context.get("ticket_after"),
        ticket_payload=context.get("ticket_payload"),
    )
    ticket_identifier = str(
        context.get("ticket_after", {}).get("id")
        or context.get("ticket_payload", {}).get("id")
        or context.get("ticket_before", {}).get("id")
        or "unknown"
    )

    for automation in automations:
        if not _automation_matches(automation, context):
            continue
        automation.last_trigger_at = triggered_at
        triggered.append(automation)
        session.add(automation)

        rendered_actions: list[dict[str, str]] = []
        if automation.ticket_actions:
            for entry in automation.ticket_actions:
                try:
                    model = AutomationTicketAction.parse_obj(entry)
                except ValidationError:
                    continue
                rendered_value = render_template_value(
                    model.value, variable_context
                )
                if model.action == "send-ntfy-notification":
                    await send_ntfy_notification(
                        session,
                        message=rendered_value,
                        automation_name=automation.name,
                        event_type=event_type,
                        ticket_identifier=ticket_identifier,
                    )
                rendered_actions.append(
                    {
                        "action": model.action,
                        "value": rendered_value,
                        "template": model.value,
                    }
                )

        await automation_dispatcher.dispatch(
            event_type="Automation Triggered",
            ticket_id=ticket_identifier,
            payload={
                "automation_id": automation.id,
                "automation_name": automation.name,
                "trigger_event": event_type,
                "triggered_at": variable_context.get("event.triggered_at"),
                "variables": dict(variable_context),
                "actions": rendered_actions,
            },
        )

    if triggered:
        await session.commit()

    return triggered
