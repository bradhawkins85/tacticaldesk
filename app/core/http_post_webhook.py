"""Utilities for processing generic HTTPS POST payloads and exposing template variables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Sequence

import json


def _normalize_structure(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {key: _normalize_structure(val) for key, val in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_structure(item) for item in value]
    return value


def _serialize_value(value: Any) -> str:
    """Normalise values to strings suitable for template rendering."""

    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        normalized = _normalize_structure(value)
        return json.dumps(normalized, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def _as_mapping(value: Any) -> MutableMapping[str, Any]:
    if isinstance(value, MutableMapping):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("Webhook payload must be a mapping of keys to values")


def _flatten_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    def _walk(node: Any, prefix: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_str = str(key)
                path = f"{prefix}.{key_str}" if prefix else key_str
                flattened[path.casefold()] = value
                key_lower = key_str.casefold()
                flattened.setdefault(key_lower, value)
                _walk(value, path)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for index, value in enumerate(node):
                path = f"{prefix}[{index}]" if prefix else f"[{index}]"
                flattened[path.casefold()] = value
                _walk(value, path)

    _walk(payload, "")
    for key, value in payload.items():
        flattened[str(key).casefold()] = value
    return flattened


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value) == 0
    if isinstance(value, Mapping):
        return len(value) == 0
    return False


def _path_matches_suffix(path: str, suffix: str) -> bool:
    if path == suffix:
        return True
    if not path.endswith(suffix):
        return False
    start = len(path) - len(suffix)
    if start == 0:
        return True
    return path[start - 1] in {".", "["}


def _first_match(
    flattened: Mapping[str, Any], candidates: Sequence[str]
) -> Any | None:
    for candidate in candidates:
        candidate_lower = candidate.casefold()
        value = flattened.get(candidate_lower)
        if not _is_empty(value):
            return value
        for path, nested_value in flattened.items():
            if not _path_matches_suffix(path, candidate_lower):
                continue
            if _is_empty(nested_value):
                continue
            return nested_value
    return None


_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "webhook.id": (
        "id",
        "event_id",
        "event.id",
        "payload.id",
        "message_id",
        "data.id",
        "event.uuid",
    ),
    "webhook.type": (
        "type",
        "event_type",
        "event.type",
        "detail-type",
        "headers.x-event-type",
        "kind",
        "action",
    ),
    "webhook.summary": (
        "summary",
        "title",
        "subject",
        "short_description",
        "content",
        "message",
        "alert",
    ),
    "webhook.details": (
        "details",
        "description",
        "body",
        "text",
        "content",
        "payload",
    ),
    "webhook.source": (
        "source",
        "origin",
        "service",
        "application",
        "system",
        "provider",
        "webhook_id",
        "integration",
    ),
    "webhook.actor": (
        "actor.name",
        "actor",
        "user.name",
        "user",
        "author.name",
        "author",
        "sender",
        "initiator",
    ),
    "webhook.severity": (
        "severity",
        "priority",
        "level",
        "urgency",
        "impact",
    ),
    "webhook.status": (
        "status",
        "state",
        "phase",
        "current_state",
    ),
    "webhook.timestamp": (
        "timestamp",
        "time",
        "occurred_at",
        "created_at",
        "updated_at",
        "event_time",
    ),
    "webhook.reference": (
        "url",
        "link",
        "permalink",
        "html_url",
        "web_url",
    ),
    "webhook.tags": (
        "tags",
        "labels",
        "categories",
        "keywords",
    ),
    "webhook.location": (
        "location",
        "site",
        "region",
        "environment",
    ),
}


_ARRAY_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "webhook.attachments_count",
        ("attachments", "files", "documents", "items", "records"),
    ),
)


def _count_items(flattened: Mapping[str, Any], candidates: Sequence[str]) -> int | None:
    for candidate in candidates:
        value = flattened.get(candidate.casefold())
        if isinstance(value, Mapping):
            return len(value)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return len(value)
    return None


def build_http_post_variable_context(payload: Mapping[str, Any]) -> dict[str, str]:
    """Flatten a generic HTTPS POST payload into template-friendly variables."""

    data = _as_mapping(payload)
    flattened = _flatten_payload(data)

    context: dict[str, str] = {}

    for key, candidates in _FIELD_CANDIDATES.items():
        value = _first_match(flattened, candidates)
        if value is None:
            continue
        context[key] = _serialize_value(value)

    for key, candidates in _ARRAY_FIELDS:
        count = _count_items(flattened, candidates)
        if count is None:
            continue
        context[key] = _serialize_value(count)

    # Provide sensible fallbacks when summary/details overlap.
    if not context.get("webhook.summary") and context.get("webhook.details"):
        context["webhook.summary"] = context["webhook.details"]

    if context.get("webhook.details") is None and context.get("webhook.summary"):
        context["webhook.details"] = context["webhook.summary"]

    context["webhook.raw"] = _serialize_value(data)

    return context


HTTP_POST_TEMPLATE_VARIABLES: tuple[dict[str, str], ...] = (
    {
        "key": "webhook.id",
        "label": "Event ID",
        "description": "Identifier supplied by the originating system for this webhook payload.",
    },
    {
        "key": "webhook.type",
        "label": "Event type",
        "description": "Event or notification type reported by the external system.",
    },
    {
        "key": "webhook.summary",
        "label": "Summary",
        "description": "Short headline, title, or subject extracted from the payload.",
    },
    {
        "key": "webhook.details",
        "label": "Details",
        "description": "Full text body or description received with the webhook.",
    },
    {
        "key": "webhook.source",
        "label": "Source system",
        "description": "Name of the service, application, or integration that sent the webhook.",
    },
    {
        "key": "webhook.actor",
        "label": "Actor",
        "description": "User or process reported as triggering the webhook event.",
    },
    {
        "key": "webhook.severity",
        "label": "Severity",
        "description": "Severity, priority, or impact level supplied by the payload.",
    },
    {
        "key": "webhook.status",
        "label": "Status",
        "description": "Current state or lifecycle status communicated by the webhook.",
    },
    {
        "key": "webhook.timestamp",
        "label": "Event timestamp",
        "description": "UTC timestamp indicating when the source recorded the event.",
    },
    {
        "key": "webhook.reference",
        "label": "Reference link",
        "description": "URL linking to the upstream record or detailed view.",
    },
    {
        "key": "webhook.tags",
        "label": "Tags",
        "description": "Labels, categories, or keywords packaged with the payload.",
    },
    {
        "key": "webhook.location",
        "label": "Location",
        "description": "Environment, region, or site associated with the event, when provided.",
    },
    {
        "key": "webhook.attachments_count",
        "label": "Attachments count",
        "description": "Number of attachments, files, or records bundled with the webhook.",
    },
    {
        "key": "webhook.raw",
        "label": "Raw payload",
        "description": "Complete serialized JSON payload received over HTTPS.",
    },
)

