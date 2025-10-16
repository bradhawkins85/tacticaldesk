from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.ext.mutable import MutableDict
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
    status: str = Column(String(32), nullable=False, default="retrying")
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
