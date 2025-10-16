from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRead(UserBase):
    id: int
    is_super_admin: bool
    created_at: datetime

    class Config:
        orm_mode = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class IntegrationSettings(BaseModel):
    base_url: Optional[str] = Field(default=None, max_length=2048)
    api_key: Optional[str] = Field(default=None, max_length=512)
    webhook_url: Optional[str] = Field(default=None, max_length=2048)
    client_id: Optional[str] = Field(default=None, max_length=255)
    client_secret: Optional[str] = Field(default=None, max_length=512)
    tenant_id: Optional[str] = Field(default=None, max_length=255)

    class Config:
        extra = "allow"


class IntegrationModuleBase(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1024)
    icon: Optional[str] = Field(default=None, max_length=16)
    enabled: Optional[bool] = None
    settings: Optional[IntegrationSettings] = None


class IntegrationModuleCreate(IntegrationModuleBase):
    name: str = Field(max_length=255)
    slug: str = Field(max_length=255)
    enabled: bool = Field(default=False)


class IntegrationModuleUpdate(IntegrationModuleBase):
    pass


class IntegrationModuleRead(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    icon: Optional[str]
    enabled: bool
    settings: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class OrganizationBase(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255, min_length=1)
    slug: Optional[str] = Field(
        default=None,
        max_length=255,
        min_length=1,
        regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: Optional[str] = Field(default=None, max_length=2048)
    contact_email: Optional[EmailStr] = None


class OrganizationCreate(OrganizationBase):
    name: str = Field(max_length=255, min_length=1)
    slug: str = Field(
        max_length=255,
        min_length=1,
        regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )


class OrganizationUpdate(OrganizationBase):
    is_archived: Optional[bool] = None


class OrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    contact_email: Optional[str]
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
class WebhookStatus(str, Enum):
    RETRYING = "retrying"
    PAUSED = "paused"
    FAILED = "failed"
    DELIVERED = "delivered"


class WebhookDeliveryRead(BaseModel):
    id: int
    event_id: str
    endpoint: str
    status: WebhookStatus
    last_attempt_at: Optional[datetime]
    next_retry_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
