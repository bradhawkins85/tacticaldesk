"""Helpers for processing Discord webhook payloads and exposing template variables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Sequence
import json

from app.schemas import DiscordWebhookMessage


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


def _as_dict(value: Any) -> MutableMapping[str, Any]:
    if isinstance(value, MutableMapping):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def build_discord_variable_context(
    payload: DiscordWebhookMessage | Mapping[str, Any]
) -> dict[str, str]:
    """Flatten a Discord webhook payload into template-friendly variables."""

    if isinstance(payload, DiscordWebhookMessage):
        data = payload.dict(by_alias=False)
    else:
        data = dict(payload)

    context: dict[str, str] = {}

    def add(key: str, value: Any) -> None:
        context[key] = _serialize_value(value)

    add("discord.id", data.get("id"))
    add("discord.type", data.get("type"))
    add("discord.content", data.get("content"))
    add("discord.channel_id", data.get("channel_id"))
    add("discord.guild_id", data.get("guild_id"))
    add("discord.webhook_id", data.get("webhook_id"))
    add("discord.application_id", data.get("application_id"))
    add("discord.timestamp", data.get("timestamp"))
    add("discord.edited_timestamp", data.get("edited_timestamp"))
    add("discord.mention_everyone", data.get("mention_everyone", False))
    add("discord.tts", data.get("tts", False))
    add("discord.pinned", data.get("pinned", False))
    add("discord.flags", data.get("flags"))

    attachments = list(data.get("attachments") or [])
    embeds = list(data.get("embeds") or [])
    mentions = list(data.get("mentions") or [])
    mention_roles = list(data.get("mention_roles") or [])

    add("discord.attachments_count", len(attachments))
    add("discord.attachments", attachments)
    add("discord.embeds_count", len(embeds))
    add("discord.embeds", embeds)
    add("discord.mentions_count", len(mentions))
    add("discord.mentions", mentions)
    add("discord.mention_roles_count", len(mention_roles))
    add("discord.mention_roles", mention_roles)

    author = _as_dict(data.get("author"))
    add("discord.author.id", author.get("id"))
    add("discord.author.username", author.get("username"))
    add("discord.author.discriminator", author.get("discriminator"))
    add("discord.author.global_name", author.get("global_name"))
    add("discord.author.avatar", author.get("avatar"))
    add("discord.author.bot", author.get("bot"))

    thread = _as_dict(data.get("thread"))
    add("discord.thread.id", thread.get("id"))
    add("discord.thread.name", thread.get("name"))
    add("discord.thread.archived", thread.get("archived"))
    add("discord.thread.auto_archive_duration", thread.get("auto_archive_duration"))

    interaction = _as_dict(data.get("interaction"))
    add("discord.interaction.id", interaction.get("id"))
    add("discord.interaction.name", interaction.get("name"))
    add("discord.interaction.type", interaction.get("type"))
    add("discord.interaction.user_id", _as_dict(interaction.get("user")).get("id"))

    message_reference = _as_dict(data.get("message_reference"))
    add("discord.message_reference.id", message_reference.get("message_id"))
    add("discord.message_reference.channel_id", message_reference.get("channel_id"))
    add("discord.message_reference.guild_id", message_reference.get("guild_id"))

    referenced_message = _as_dict(data.get("referenced_message"))
    add("discord.referenced_message", referenced_message)

    member = _as_dict(data.get("member"))
    add("discord.member", member)

    add("discord.raw", data)

    return context


DISCORD_WEBHOOK_VARIABLES: tuple[dict[str, str], ...] = (
    {
        "key": "discord.id",
        "label": "Message ID",
        "description": "Unique identifier of the Discord message received via the webhook.",
    },
    {
        "key": "discord.type",
        "label": "Message type",
        "description": "Numeric Discord type for the message payload (0 = default message).",
    },
    {
        "key": "discord.content",
        "label": "Message content",
        "description": "Text body of the incoming Discord message after markdown formatting.",
    },
    {
        "key": "discord.channel_id",
        "label": "Channel ID",
        "description": "Identifier of the Discord channel that published the webhook event.",
    },
    {
        "key": "discord.guild_id",
        "label": "Guild ID",
        "description": "Identifier of the Discord guild/server associated with the event, if any.",
    },
    {
        "key": "discord.webhook_id",
        "label": "Webhook ID",
        "description": "Identifier of the webhook configuration that emitted the message.",
    },
    {
        "key": "discord.timestamp",
        "label": "Created timestamp",
        "description": "ISO 8601 timestamp (UTC) when Discord created the message.",
    },
    {
        "key": "discord.edited_timestamp",
        "label": "Edited timestamp",
        "description": "ISO 8601 timestamp (UTC) when the message was last edited, if ever.",
    },
    {
        "key": "discord.author.username",
        "label": "Author username",
        "description": "Discord username of the author who created the message.",
    },
    {
        "key": "discord.author.id",
        "label": "Author ID",
        "description": "Unique identifier for the Discord user that posted the webhook message.",
    },
    {
        "key": "discord.author.discriminator",
        "label": "Author discriminator",
        "description": "Four-digit discriminator tag associated with the user (legacy accounts).",
    },
    {
        "key": "discord.author.global_name",
        "label": "Author display name",
        "description": "Global display name for the Discord user when provided.",
    },
    {
        "key": "discord.author.bot",
        "label": "Author is bot",
        "description": "Indicates whether the message author is a bot user (\"true\" or \"false\").",
    },
    {
        "key": "discord.attachments_count",
        "label": "Attachments count",
        "description": "Number of attachments included with the message.",
    },
    {
        "key": "discord.attachments",
        "label": "Attachments JSON",
        "description": "Serialized JSON representation of attachment metadata provided by Discord.",
    },
    {
        "key": "discord.embeds_count",
        "label": "Embeds count",
        "description": "Number of embed objects delivered with the message payload.",
    },
    {
        "key": "discord.embeds",
        "label": "Embeds JSON",
        "description": "Serialized JSON representation of embed payloads for the message.",
    },
    {
        "key": "discord.mentions_count",
        "label": "Mentions count",
        "description": "Number of Discord users mentioned in the message.",
    },
    {
        "key": "discord.mentions",
        "label": "Mentions JSON",
        "description": "Serialized JSON representation of mentioned user records.",
    },
    {
        "key": "discord.mention_roles_count",
        "label": "Mention roles count",
        "description": "Number of role identifiers referenced in the message.",
    },
    {
        "key": "discord.mention_roles",
        "label": "Mention roles",
        "description": "List of Discord role identifiers mentioned in the message.",
    },
    {
        "key": "discord.thread.id",
        "label": "Thread ID",
        "description": "Identifier of the thread attached to the message, if the webhook posted to one.",
    },
    {
        "key": "discord.thread.name",
        "label": "Thread name",
        "description": "Display name of the referenced thread.",
    },
    {
        "key": "discord.interaction.id",
        "label": "Interaction ID",
        "description": "Identifier for the interaction that generated the message, when available.",
    },
    {
        "key": "discord.message_reference.id",
        "label": "Referenced message ID",
        "description": "Identifier of the original message that this payload replies to.",
    },
    {
        "key": "discord.member",
        "label": "Member JSON",
        "description": "Serialized JSON metadata for the guild member resolved with the webhook author.",
    },
    {
        "key": "discord.raw",
        "label": "Raw payload JSON",
        "description": "Complete serialized JSON payload received from Discord.",
    },
)

