from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, constr, root_validator, validator

from app.core.automations import (
    EVENT_AUTOMATION_ACTION_LOOKUP,
    TRIGGER_OPERATOR_LABELS,
    VALUE_REQUIRED_TRIGGER_OPTIONS,
)

TicketShortText = constr(strip_whitespace=True, min_length=1, max_length=255)
TicketSummaryText = constr(strip_whitespace=True, min_length=1, max_length=2048)
TicketMessageText = constr(strip_whitespace=True, min_length=1, max_length=4096)
TicketTemplateKey = constr(strip_whitespace=True, min_length=1, max_length=64)


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
    topic: Optional[str] = Field(default=None, max_length=255)
    token: Optional[str] = Field(default=None, max_length=512)

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


class RunbookLabelSummary(BaseModel):
    label: str
    automation_count: int


class RunbookLabelRename(BaseModel):
    new_label: str = Field(max_length=255, min_length=1)


class AutomationTriggerCondition(BaseModel):
    type: str = Field(max_length=255)
    operator: Optional[Literal["equals", "not_equals", "contains"]] = None
    value: Optional[str] = Field(default=None, max_length=255)

    @classmethod
    def __get_validators__(cls):
        yield cls._coerce_root
        yield from super().__get_validators__()

    @staticmethod
    def _coerce_root(value):
        if isinstance(value, str):
            return {"type": value}
        if value is None:
            return {}
        return value

    @validator("type", pre=True)
    def _coerce_type(cls, value) -> str:
        if isinstance(value, dict):
            for key in ("type", "trigger", "label"):
                if value.get(key):
                    return str(value[key])
            if "value" in value and "operator" in value and len(value) == 2:
                # Unexpected structure but ensure string return to trigger validation error later.
                return ""
        if value is None:
            return ""
        return str(value)

    @validator("operator", pre=True)
    def _normalize_operator(cls, value):
        if value is None or value == "":
            return None
        return str(value).strip().lower()

    @validator("value", pre=True)
    def _coerce_value(cls, value):
        if value is None:
            return None
        return str(value)

    @validator("type")
    def _validate_type(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Condition type cannot be empty")
        return cleaned

    @validator("operator")
    def _validate_operator(cls, operator: str | None, values: dict[str, Any]) -> str | None:
        condition_type = values.get("type", "")
        requires_value = condition_type in VALUE_REQUIRED_TRIGGER_OPTIONS
        if not requires_value:
            return None
        if not operator:
            raise ValueError("Operator is required for this trigger")
        if operator not in TRIGGER_OPERATOR_LABELS:
            raise ValueError("Unsupported operator")
        return operator

    @validator("value")
    def _validate_value(cls, raw_value: str | None, values: dict[str, Any]) -> str | None:
        condition_type = values.get("type", "")
        requires_value = condition_type in VALUE_REQUIRED_TRIGGER_OPTIONS
        if not requires_value:
            return None
        if raw_value is None:
            raise ValueError("A value is required for this trigger")
        cleaned = raw_value.strip()
        if not cleaned:
            raise ValueError("A value is required for this trigger")
        return cleaned

    def display_text(self) -> str:
        if self.type in VALUE_REQUIRED_TRIGGER_OPTIONS and self.operator and self.value:
            operator_label = TRIGGER_OPERATOR_LABELS.get(self.operator, self.operator)
            return f"{self.type} {operator_label} \"{self.value}\""
        return self.type

    def sort_key(self) -> str:
        base = self.type
        if self.operator:
            base += f" {self.operator}"
        if self.value:
            base += f" {self.value}"
        return base.lower()

    def dict(self, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("exclude_none", True)
        return super().dict(*args, **kwargs)


class AutomationTriggerFilter(BaseModel):
    match: Literal["any", "all"] = Field(
        default="any",
        description="Trigger match behavior: 'any' for OR, 'all' for AND.",
    )
    conditions: list[AutomationTriggerCondition] = Field(
        min_items=1,
        description="List of trigger condition definitions.",
    )

    @validator("match", pre=True)
    def _normalize_match(cls, value: str | None) -> str:
        if value is None:
            return "any"
        return str(value).strip().lower() or "any"

    @validator("conditions", pre=True)
    def _ensure_sequence(cls, value):
        if value is None:
            return []
        if isinstance(value, (str, bytes)):
            return [value]
        return list(value)

    @validator("conditions")
    def _deduplicate_conditions(
        cls, value: list[AutomationTriggerCondition]
    ) -> list[AutomationTriggerCondition]:
        unique: dict[str, AutomationTriggerCondition] = {}
        for item in value:
            key = (
                f"{item.type}|{item.operator or ''}|{item.value or ''}"
            )
            if key not in unique:
                unique[key] = item
        cleaned = list(unique.values())
        if not cleaned:
            raise ValueError("At least one trigger condition is required.")
        return cleaned

    def dict(self, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("exclude_none", True)
        return super().dict(*args, **kwargs)


class AutomationTicketAction(BaseModel):
    action: str = Field(
        max_length=128,
        description="Ticket action identifier (slug).",
    )
    value: str = Field(
        max_length=4096,
        description="Action payload such as comment text or status update.",
    )

    @root_validator(pre=True)
    def _coerce_aliases(cls, values: dict[str, object]) -> dict[str, object]:
        data = dict(values or {})
        if "action" not in data or data.get("action") in {None, ""}:
            for candidate_key in ("slug", "name", "label", "type"):
                candidate = data.get(candidate_key)
                if isinstance(candidate, str) and candidate.strip():
                    data["action"] = candidate
                    break
        if "value" not in data or data.get("value") in {None, ""}:
            for candidate_key in ("details", "text", "body"):
                candidate = data.get(candidate_key)
                if candidate is None:
                    continue
                if isinstance(candidate, str):
                    if candidate.strip():
                        data["value"] = candidate
                        break
                    continue
                data["value"] = str(candidate)
                break
        return data

    @validator("action")
    def _validate_action(cls, raw_action: str | None) -> str:
        if raw_action is None:
            raise ValueError("Action identifier is required.")
        candidate = raw_action.strip()
        slug = candidate.lower()
        if slug in EVENT_AUTOMATION_ACTION_LOOKUP:
            return slug
        normalized_label = candidate.casefold()
        for key, label in EVENT_AUTOMATION_ACTION_LOOKUP.items():
            if label.casefold() == normalized_label:
                return key
        raise ValueError("Unsupported automation action.")

    @validator("value")
    def _validate_value(cls, raw_value: str | None) -> str:
        if raw_value is None:
            raise ValueError("Action value is required.")
        cleaned = raw_value.strip()
        if not cleaned:
            raise ValueError("Action value is required.")
        return cleaned

    def dict(self, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("exclude_none", True)
        return super().dict(*args, **kwargs)


class AutomationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255, min_length=1)
    description: Optional[str] = Field(default=None, max_length=2048)
    playbook: Optional[str] = Field(default=None, max_length=255, min_length=1)
    cron_expression: Optional[str] = Field(default=None, max_length=255)
    trigger: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Primary trigger value used when only a single condition is required.",
    )
    status: Optional[str] = Field(default=None, max_length=64)
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_trigger_at: Optional[datetime] = None
    trigger_filters: Optional[AutomationTriggerFilter] = Field(
        default=None,
        description=(
            "Logical trigger definition for event automations. Allows combining"
            " multiple trigger conditions using match 'any' (OR) or 'all' (AND)."
        ),
    )
    ticket_actions: Optional[list[Any]] = Field(
        default=None,
        description=(
            "Ordered list of ticket actions to perform when an automation executes."
        ),
    )


class AutomationRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    playbook: str
    kind: str
    cron_expression: Optional[str]
    trigger: Optional[str]
    status: Optional[str]
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    last_trigger_at: Optional[datetime]
    action_label: Optional[str]
    action_endpoint: Optional[str]
    action_output_selector: Optional[str]
    trigger_filters: Optional[AutomationTriggerFilter]
    ticket_actions: Optional[list[AutomationTicketAction]]

    class Config:
        orm_mode = True


class TicketUpdate(BaseModel):
    subject: TicketShortText
    customer: TicketShortText
    customer_email: EmailStr
    status: TicketShortText
    priority: TicketShortText
    team: TicketShortText
    assignment: TicketShortText
    queue: TicketShortText
    category: TicketShortText
    summary: TicketSummaryText


class TicketReply(BaseModel):
    to: EmailStr
    cc: Optional[str] = Field(default="", max_length=1024)
    template: TicketTemplateKey
    message: TicketMessageText
    public_reply: bool = True
    add_signature: bool = True
class ContactBase(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255, min_length=1)
    job_title: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2048)


class ContactCreate(ContactBase):
    name: str = Field(max_length=255, min_length=1)


class ContactUpdate(ContactBase):
    pass


class ContactRead(BaseModel):
    id: int
    organization_id: int
    name: str
    job_title: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    notes: Optional[str]
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
