from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import declarative_base

from sqlalchemy.types import JSON

Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, index=True)
    email: str = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password: str = Column(String(255), nullable=False)
    is_super_admin: bool = Column(Boolean, default=False, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class IntegrationModule(Base):
    __tablename__ = "integration_modules"

    id: int = Column(Integer, primary_key=True, index=True)
    name: str = Column(String(255), nullable=False)
    slug: str = Column(String(255), nullable=False, unique=True, index=True)
    description: str | None = Column(Text, nullable=True)
    icon: str | None = Column(String(16), nullable=True)
    enabled: bool = Column(Boolean, default=False, nullable=False)
    settings: dict = Column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )



class Organization(Base):
    __tablename__ = "organizations"

    id: int = Column(Integer, primary_key=True, index=True)
    name: str = Column(String(255), nullable=False)
    slug: str = Column(String(255), nullable=False, unique=True, index=True)
    description: str | None = Column(Text, nullable=True)
    contact_email: str | None = Column(String(255), nullable=True)
    is_archived: bool = Column(Boolean, default=False, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class Automation(Base):
    __tablename__ = "automations"

    id: int = Column(Integer, primary_key=True, index=True)
    name: str = Column(String(255), nullable=False)
    description: str | None = Column(Text, nullable=True)
    playbook: str = Column(String(255), nullable=False)
    kind: str = Column(String(32), nullable=False, index=True)
    cadence: str | None = Column(String(255), nullable=True)
    cron_expression: str | None = Column(String(255), nullable=True)
    trigger: str | None = Column(String(255), nullable=True)
    trigger_filters: dict | None = Column(
        MutableDict.as_mutable(JSON),
        nullable=True,
        default=None,
    )
    ticket_actions: list[dict[str, str]] | None = Column(
        MutableList.as_mutable(JSON),
        nullable=True,
        default=None,
    )
    status: str | None = Column(String(64), nullable=True)
    next_run_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    last_run_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    last_trigger_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    action_label: str | None = Column(String(255), nullable=True)
    action_endpoint: str | None = Column(String(1024), nullable=True)
    action_output_selector: str | None = Column(String(255), nullable=True)


class Contact(Base):
    __tablename__ = "contacts"

    id: int = Column(Integer, primary_key=True, index=True)
    organization_id: int = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: str = Column(String(255), nullable=False)
    job_title: str | None = Column(String(255), nullable=True)
    email: str | None = Column(String(255), nullable=True)
    phone: str | None = Column(String(64), nullable=True)
    notes: str | None = Column(Text, nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: int = Column(Integer, primary_key=True, index=True)
    event_id: str = Column(String(128), nullable=False, unique=True, index=True)
    endpoint: str = Column(String(2048), nullable=False)
    module_id: int | None = Column(
        Integer,
        ForeignKey("integration_modules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    module_slug: str | None = Column(String(255), nullable=True, index=True)
    request_method: str = Column(String(16), nullable=False, default="GET")
    request_url: str = Column(String(2048), nullable=False, default="")
    request_payload: dict | list | str | int | float | bool | None = Column(
        JSON, nullable=True
    )
    status: str = Column(String(32), nullable=False, default="retrying")
    response_status_code: int | None = Column(Integer, nullable=True)
    response_payload: dict | list | str | int | float | bool | None = Column(
        JSON, nullable=True
    )
    error_message: str | None = Column(Text, nullable=True)
    last_attempt_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    next_retry_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: str = Column(String(32), primary_key=True)
    subject: str = Column(String(255), nullable=False)
    customer: str = Column(String(255), nullable=False)
    customer_email: str = Column(String(255), nullable=False)
    status: str = Column(String(64), nullable=False)
    priority: str = Column(String(64), nullable=False)
    team: str = Column(String(255), nullable=False)
    assignment: str = Column(String(255), nullable=False)
    queue: str = Column(String(255), nullable=False)
    category: str = Column(String(255), nullable=False)
    summary: str = Column(Text, nullable=False)
    channel: str = Column(String(64), nullable=False, default="Portal")
    created_at_dt: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_reply_dt: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    due_at_dt: datetime | None = Column(DateTime(timezone=True), nullable=True)
    labels: list[str] = Column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    watchers: list[str] = Column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    is_starred: bool = Column(Boolean, nullable=False, default=False)
    assets_visible: bool = Column(Boolean, nullable=False, default=False)
    history: list[dict[str, object]] = Column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    metadata_created_at_dt: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    metadata_updated_at_dt: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class TicketOverride(Base):
    __tablename__ = "ticket_overrides"

    ticket_id: str = Column(String(32), primary_key=True)
    subject: str = Column(String(255), nullable=False)
    customer: str = Column(String(255), nullable=False)
    customer_email: str = Column(String(255), nullable=False)
    status: str = Column(String(64), nullable=False)
    priority: str = Column(String(64), nullable=False)
    team: str = Column(String(255), nullable=False)
    assignment: str = Column(String(255), nullable=False)
    queue: str = Column(String(255), nullable=False)
    category: str = Column(String(255), nullable=False)
    summary: str = Column(Text, nullable=False)
    metadata_updated_at_dt: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class TicketReply(Base):
    __tablename__ = "ticket_replies"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id: str = Column(String(32), index=True, nullable=False)
    actor: str = Column(String(255), nullable=False)
    direction: str = Column(String(32), nullable=False, default="outbound")
    channel: str = Column(String(64), nullable=False)
    summary: str = Column(String(255), nullable=False)
    body: str = Column(Text, nullable=False)
    timestamp_dt: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class TicketDeletion(Base):
    __tablename__ = "ticket_deletions"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_ticket_deletions_kind_value"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    kind: str = Column(String(32), nullable=False, index=True)
    value: str = Column(String(255), nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class KnowledgeSpace(Base):
    __tablename__ = "knowledge_spaces"

    id: int = Column(Integer, primary_key=True, index=True)
    name: str = Column(String(255), nullable=False)
    slug: str = Column(String(255), nullable=False, unique=True, index=True)
    description: str | None = Column(Text, nullable=True)
    icon: str | None = Column(String(16), nullable=True)
    is_private: bool = Column(Boolean, default=False, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("space_id", "slug", name="uq_knowledge_documents_space_slug"),
    )

    id: int = Column(Integer, primary_key=True, index=True)
    space_id: int = Column(
        Integer,
        ForeignKey("knowledge_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: int | None = Column(
        Integer,
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: str = Column(String(255), nullable=False)
    slug: str = Column(String(255), nullable=False)
    summary: str | None = Column(Text, nullable=True)
    content: str = Column(Text, nullable=False)
    is_published: bool = Column(Boolean, default=False, nullable=False)
    position: int = Column(Integer, default=0, nullable=False)
    version: int = Column(Integer, default=1, nullable=False)
    created_by_id: int | None = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class TicketSummary(Base):
    __tablename__ = "ticket_summaries"

    ticket_id: str = Column(String(32), primary_key=True)
    provider: str = Column(String(64), nullable=False, default="ollama")
    model: str | None = Column(String(255), nullable=True)
    summary: str | None = Column(Text, nullable=True)
    error_message: str | None = Column(Text, nullable=True)
    resolution_state: str | None = Column(String(32), nullable=True)
    created_at_dt: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at_dt: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    published_at: datetime | None = Column(DateTime(timezone=True), nullable=True)


class KnowledgeDocumentRevision(Base):
    __tablename__ = "knowledge_document_revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_knowledge_revision_document_version"),
    )

    id: int = Column(Integer, primary_key=True, index=True)
    document_id: int = Column(
        Integer,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: int = Column(Integer, nullable=False)
    title: str = Column(String(255), nullable=False)
    summary: str | None = Column(Text, nullable=True)
    content: str = Column(Text, nullable=False)
    created_by_id: int | None = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
