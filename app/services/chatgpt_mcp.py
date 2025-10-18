from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable

from fastapi import status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models import (
    Automation,
    Contact,
    IntegrationModule,
    Organization,
    WebhookDelivery,
    utcnow,
)
from app.schemas import (
    AutomationRead,
    AutomationUpdate,
    ContactCreate,
    ContactRead,
    ContactUpdate,
    IntegrationModuleCreate,
    IntegrationModuleRead,
    IntegrationModuleUpdate,
    MCPExecutionRequest,
    MCPExecutionResponse,
    MCPResourceDescriptor,
    MCPOperation,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    WebhookDeliveryRead,
    WebhookStatus,
)
from app.services.ticket_data import fetch_ticket_records
from app.core.tickets import ticket_store

TICKET_MUTABLE_FIELDS = (
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
)

REPLY_FIELDS = ("actor", "channel", "summary", "message")


class MCPConnectorError(Exception):
    """Raised when an MCP interaction cannot be completed."""

    def __init__(self, message: str, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(message)
        self.status_code = status_code


class ChatGPTMCPConnector:
    """Service exposing Tactical Desk resources to the ChatGPT MCP."""

    def __init__(self) -> None:
        self._descriptors: dict[str, MCPResourceDescriptor] = {
            "integration-modules": MCPResourceDescriptor(
                slug="integration-modules",
                name="Integration Modules",
                description="Manage third-party integration modules and connector settings.",
                operations=[
                    MCPOperation.LIST.value,
                    MCPOperation.RETRIEVE.value,
                    MCPOperation.CREATE.value,
                    MCPOperation.UPDATE.value,
                    MCPOperation.DELETE.value,
                ],
            ),
            "organizations": MCPResourceDescriptor(
                slug="organizations",
                name="Organizations",
                description="Create, update, and archive customer organizations.",
                operations=[
                    MCPOperation.LIST.value,
                    MCPOperation.RETRIEVE.value,
                    MCPOperation.CREATE.value,
                    MCPOperation.UPDATE.value,
                    MCPOperation.DELETE.value,
                ],
            ),
            "contacts": MCPResourceDescriptor(
                slug="contacts",
                name="Contacts",
                description="Maintain organization contacts and their metadata.",
                operations=[
                    MCPOperation.LIST.value,
                    MCPOperation.RETRIEVE.value,
                    MCPOperation.CREATE.value,
                    MCPOperation.UPDATE.value,
                    MCPOperation.DELETE.value,
                ],
            ),
            "automations": MCPResourceDescriptor(
                slug="automations",
                name="Automations",
                description="Inspect and tune automation definitions and schedules.",
                operations=[
                    MCPOperation.LIST.value,
                    MCPOperation.RETRIEVE.value,
                    MCPOperation.UPDATE.value,
                ],
            ),
            "webhook-deliveries": MCPResourceDescriptor(
                slug="webhook-deliveries",
                name="Webhook Deliveries",
                description="Review webhook deliveries and adjust retry schedules.",
                operations=[
                    MCPOperation.LIST.value,
                    MCPOperation.RETRIEVE.value,
                    MCPOperation.UPDATE.value,
                ],
            ),
            "tickets": MCPResourceDescriptor(
                slug="tickets",
                name="Tickets",
                description="List, create, and update support tickets and replies.",
                operations=[
                    MCPOperation.LIST.value,
                    MCPOperation.RETRIEVE.value,
                    MCPOperation.CREATE.value,
                    MCPOperation.UPDATE.value,
                    MCPOperation.APPEND_REPLY.value,
                ],
            ),
        }
        self._handlers: dict[str, Callable[[MCPExecutionRequest], Awaitable[MCPExecutionResponse]]] = {
            "integration-modules": self._execute_integration_modules,
            "organizations": self._execute_organizations,
            "contacts": self._execute_contacts,
            "automations": self._execute_automations,
            "webhook-deliveries": self._execute_webhooks,
            "tickets": self._execute_tickets,
        }

    async def list_resources(self) -> list[MCPResourceDescriptor]:
        return [descriptor.copy(deep=True) for descriptor in self._descriptors.values()]

    async def get_resource_descriptor(self, slug: str) -> MCPResourceDescriptor:
        descriptor = self._descriptors.get(slug)
        if descriptor is None:
            raise MCPConnectorError("Resource not found", status_code=status.HTTP_404_NOT_FOUND)
        return descriptor.copy(deep=True)

    async def execute(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        handler = self._handlers.get(request.resource)
        if handler is None:
            raise MCPConnectorError("Unsupported resource", status_code=status.HTTP_404_NOT_FOUND)
        return await handler(request)

    async def _with_session(self, callback: Callable[[AsyncSession], Awaitable[MCPExecutionResponse]]) -> MCPExecutionResponse:
        factory = await get_session_factory()
        async with factory() as session:
            return await callback(session)

    async def _execute_integration_modules(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.operation == MCPOperation.LIST:
            return await self._with_session(lambda session: self._list_integration_modules(session, request))
        if request.operation == MCPOperation.RETRIEVE:
            return await self._with_session(lambda session: self._get_integration_module(session, request))
        if request.operation == MCPOperation.CREATE:
            return await self._with_session(lambda session: self._create_integration_module(session, request))
        if request.operation == MCPOperation.UPDATE:
            return await self._with_session(lambda session: self._update_integration_module(session, request))
        if request.operation == MCPOperation.DELETE:
            return await self._with_session(lambda session: self._delete_integration_module(session, request))
        raise MCPConnectorError("Operation not supported for integration modules")

    async def _list_integration_modules(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        filters = request.filters or {}
        query = select(IntegrationModule).order_by(IntegrationModule.name.asc())
        if "enabled" in filters:
            enabled_raw = filters.get("enabled")
            enabled_value = self._to_bool(enabled_raw)
            query = query.where(IntegrationModule.enabled.is_(enabled_value))
        if request.limit:
            query = query.limit(request.limit)
        if request.offset:
            query = query.offset(request.offset)
        result = await session.execute(query)
        modules = result.scalars().all()
        payload = [IntegrationModuleRead.from_orm(module).dict() for module in modules]
        return MCPExecutionResponse(
            resource="integration-modules",
            operation=request.operation,
            data=jsonable_encoder(payload),
            meta={"count": len(payload)},
        )

    async def _get_integration_module(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        module = await self._require_integration_module(session, request.identifier)
        return MCPExecutionResponse(
            resource="integration-modules",
            operation=request.operation,
            data=jsonable_encoder(IntegrationModuleRead.from_orm(module).dict()),
            meta={"id": module.id, "slug": module.slug},
        )

    async def _create_integration_module(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        payload = request.payload or {}
        try:
            module_in = IntegrationModuleCreate(**payload)
        except ValidationError as exc:  # pydantic validation
            raise MCPConnectorError(str(exc)) from exc
        existing = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == module_in.slug)
        )
        if existing.scalar_one_or_none():
            raise MCPConnectorError(
                "An integration module with this slug already exists",
                status_code=status.HTTP_409_CONFLICT,
            )
        settings_payload = module_in.settings.dict(exclude_unset=True) if module_in.settings else {}
        module = IntegrationModule(
            name=module_in.name,
            slug=module_in.slug,
            description=module_in.description,
            icon=module_in.icon,
            enabled=module_in.enabled,
            settings=settings_payload,
        )
        session.add(module)
        await session.commit()
        await session.refresh(module)
        return MCPExecutionResponse(
            resource="integration-modules",
            operation=request.operation,
            data=jsonable_encoder(IntegrationModuleRead.from_orm(module).dict()),
            meta={"id": module.id, "slug": module.slug},
        )

    async def _update_integration_module(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        module = await self._require_integration_module(session, request.identifier)
        if not request.payload:
            raise MCPConnectorError("Update payload is required")
        try:
            update_payload = IntegrationModuleUpdate(**request.payload)
        except ValidationError as exc:
            raise MCPConnectorError(str(exc)) from exc
        data = update_payload.dict(exclude_unset=True)
        updated = False
        if "name" in data and data["name"] and data["name"] != module.name:
            module.name = data["name"]
            updated = True
        if "description" in data and data["description"] != module.description:
            module.description = data["description"]
            updated = True
        if "icon" in data and data["icon"] != module.icon:
            module.icon = data["icon"]
            updated = True
        if "enabled" in data and data["enabled"] is not None and bool(data["enabled"]) != module.enabled:
            module.enabled = bool(data["enabled"])
            updated = True
        if "settings" in data and data["settings"] is not None:
            raw_settings = data["settings"]
            settings_payload = raw_settings
            if hasattr(raw_settings, "dict"):
                settings_payload = raw_settings.dict(exclude_unset=True)
            cleaned_settings = {k: v for k, v in settings_payload.items() if v is not None}
            if module.settings is None:
                module.settings = {}
            module.settings.update(cleaned_settings)
            for key in [key for key, value in settings_payload.items() if value is None]:
                module.settings.pop(key, None)
            updated = True
        if updated:
            module.updated_at = utcnow()
            await session.commit()
            await session.refresh(module)
        return MCPExecutionResponse(
            resource="integration-modules",
            operation=request.operation,
            data=jsonable_encoder(IntegrationModuleRead.from_orm(module).dict()),
            meta={"id": module.id, "slug": module.slug, "updated": updated},
        )

    async def _delete_integration_module(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        module = await self._require_integration_module(session, request.identifier)
        await session.delete(module)
        await session.commit()
        return MCPExecutionResponse(
            resource="integration-modules",
            operation=request.operation,
            data=None,
            meta={"id": module.id, "slug": module.slug, "deleted": True},
        )

    async def _require_integration_module(
        self, session: AsyncSession, identifier: Any | None
    ) -> IntegrationModule:
        if identifier is None:
            raise MCPConnectorError("Integration module identifier is required")
        query = select(IntegrationModule)
        if self._looks_like_int(identifier):
            query = query.where(IntegrationModule.id == int(identifier))
        else:
            slug_value = str(identifier).strip().lower()
            query = query.where(IntegrationModule.slug == slug_value)
        result = await session.execute(query)
        module = result.scalar_one_or_none()
        if module is None:
            raise MCPConnectorError("Integration module not found", status_code=status.HTTP_404_NOT_FOUND)
        return module

    async def _execute_organizations(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.operation == MCPOperation.LIST:
            return await self._with_session(lambda session: self._list_organizations(session, request))
        if request.operation == MCPOperation.RETRIEVE:
            return await self._with_session(lambda session: self._get_organization(session, request))
        if request.operation == MCPOperation.CREATE:
            return await self._with_session(lambda session: self._create_organization(session, request))
        if request.operation == MCPOperation.UPDATE:
            return await self._with_session(lambda session: self._update_organization(session, request))
        if request.operation == MCPOperation.DELETE:
            return await self._with_session(lambda session: self._delete_organization(session, request))
        raise MCPConnectorError("Operation not supported for organizations")

    async def _list_organizations(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        filters = request.filters or {}
        include_archived = self._to_bool(filters.get("include_archived", False))
        query = select(Organization).order_by(Organization.name.asc())
        if not include_archived:
            query = query.where(Organization.is_archived.is_(False))
        if request.limit:
            query = query.limit(request.limit)
        if request.offset:
            query = query.offset(request.offset)
        result = await session.execute(query)
        organizations = result.scalars().all()
        payload = [OrganizationRead.from_orm(org).dict() for org in organizations]
        return MCPExecutionResponse(
            resource="organizations",
            operation=request.operation,
            data=jsonable_encoder(payload),
            meta={"count": len(payload)},
        )

    async def _get_organization(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        organization = await self._require_organization(session, request.identifier)
        return MCPExecutionResponse(
            resource="organizations",
            operation=request.operation,
            data=jsonable_encoder(OrganizationRead.from_orm(organization).dict()),
            meta={"id": organization.id, "slug": organization.slug},
        )

    async def _create_organization(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        payload = request.payload or {}
        try:
            organization_in = OrganizationCreate(**payload)
        except ValidationError as exc:
            raise MCPConnectorError(str(exc)) from exc
        slug = organization_in.slug.strip().lower()
        existing = await session.execute(
            select(Organization).where(Organization.slug == slug)
        )
        if existing.scalar_one_or_none():
            raise MCPConnectorError(
                "An organization with this slug already exists",
                status_code=status.HTTP_409_CONFLICT,
            )
        organization = Organization(
            name=organization_in.name.strip(),
            slug=slug,
            description=self._clean_optional(organization_in.description),
            contact_email=self._clean_optional(organization_in.contact_email),
            is_archived=False,
        )
        session.add(organization)
        await session.commit()
        await session.refresh(organization)
        return MCPExecutionResponse(
            resource="organizations",
            operation=request.operation,
            data=jsonable_encoder(OrganizationRead.from_orm(organization).dict()),
            meta={"id": organization.id, "slug": organization.slug},
        )

    async def _update_organization(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        organization = await self._require_organization(session, request.identifier)
        if not request.payload:
            raise MCPConnectorError("Update payload is required")
        try:
            organization_update = OrganizationUpdate(**request.payload)
        except ValidationError as exc:
            raise MCPConnectorError(str(exc)) from exc
        data = organization_update.dict(exclude_unset=True)
        updated = False
        if "name" in data and data["name"]:
            cleaned = data["name"].strip()
            if cleaned and cleaned != organization.name:
                organization.name = cleaned
                updated = True
        if "slug" in data and data["slug"]:
            cleaned_slug = data["slug"].strip().lower()
            if cleaned_slug != organization.slug:
                existing = await session.execute(
                    select(Organization).where(Organization.slug == cleaned_slug)
                )
                if existing.scalar_one_or_none():
                    raise MCPConnectorError(
                        "An organization with this slug already exists",
                        status_code=status.HTTP_409_CONFLICT,
                    )
                organization.slug = cleaned_slug
                updated = True
        if "description" in data:
            cleaned_description = self._clean_optional(data["description"])
            if cleaned_description != organization.description:
                organization.description = cleaned_description
                updated = True
        if "contact_email" in data:
            cleaned_email = self._clean_optional(data["contact_email"])
            if cleaned_email != organization.contact_email:
                organization.contact_email = cleaned_email
                updated = True
        if "is_archived" in data and data["is_archived"] is not None:
            desired = bool(data["is_archived"])
            if desired != organization.is_archived:
                organization.is_archived = desired
                updated = True
        if updated:
            organization.updated_at = utcnow()
            await session.commit()
            await session.refresh(organization)
        return MCPExecutionResponse(
            resource="organizations",
            operation=request.operation,
            data=jsonable_encoder(OrganizationRead.from_orm(organization).dict()),
            meta={"id": organization.id, "slug": organization.slug, "updated": updated},
        )

    async def _delete_organization(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        organization = await self._require_organization(session, request.identifier)
        await session.delete(organization)
        await session.commit()
        return MCPExecutionResponse(
            resource="organizations",
            operation=request.operation,
            data=None,
            meta={"id": organization.id, "slug": organization.slug, "deleted": True},
        )

    async def _require_organization(self, session: AsyncSession, identifier: Any | None) -> Organization:
        if identifier is None:
            raise MCPConnectorError("Organization identifier is required")
        query = select(Organization)
        if self._looks_like_int(identifier):
            query = query.where(Organization.id == int(identifier))
        else:
            query = query.where(Organization.slug == str(identifier).strip().lower())
        result = await session.execute(query)
        organization = result.scalar_one_or_none()
        if organization is None:
            raise MCPConnectorError("Organization not found", status_code=status.HTTP_404_NOT_FOUND)
        return organization

    async def _execute_contacts(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.operation == MCPOperation.LIST:
            return await self._with_session(lambda session: self._list_contacts(session, request))
        if request.operation == MCPOperation.RETRIEVE:
            return await self._with_session(lambda session: self._get_contact(session, request))
        if request.operation == MCPOperation.CREATE:
            return await self._with_session(lambda session: self._create_contact(session, request))
        if request.operation == MCPOperation.UPDATE:
            return await self._with_session(lambda session: self._update_contact(session, request))
        if request.operation == MCPOperation.DELETE:
            return await self._with_session(lambda session: self._delete_contact(session, request))
        raise MCPConnectorError("Operation not supported for contacts")

    async def _list_contacts(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        filters = request.filters or {}
        organization_id_raw = filters.get("organization_id")
        if organization_id_raw is None:
            raise MCPConnectorError("organization_id filter is required to list contacts")
        try:
            organization_id = int(organization_id_raw)
        except (TypeError, ValueError) as exc:
            raise MCPConnectorError("organization_id must be an integer") from exc
        await self._require_organization(session, organization_id)
        query = select(Contact).where(Contact.organization_id == organization_id).order_by(Contact.name.asc())
        if request.limit:
            query = query.limit(request.limit)
        if request.offset:
            query = query.offset(request.offset)
        result = await session.execute(query)
        contacts = result.scalars().all()
        payload = [ContactRead.from_orm(contact).dict() for contact in contacts]
        return MCPExecutionResponse(
            resource="contacts",
            operation=request.operation,
            data=jsonable_encoder(payload),
            meta={"count": len(payload), "organization_id": organization_id},
        )

    async def _get_contact(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        contact = await self._require_contact(session, request.identifier)
        return MCPExecutionResponse(
            resource="contacts",
            operation=request.operation,
            data=jsonable_encoder(ContactRead.from_orm(contact).dict()),
            meta={"id": contact.id, "organization_id": contact.organization_id},
        )

    async def _create_contact(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        payload = request.payload or {}
        organization_id_raw = payload.get("organization_id")
        if organization_id_raw is None:
            raise MCPConnectorError("organization_id is required to create a contact")
        try:
            organization_id = int(organization_id_raw)
        except (TypeError, ValueError) as exc:
            raise MCPConnectorError("organization_id must be an integer") from exc
        await self._require_organization(session, organization_id)
        try:
            contact_in = ContactCreate(**payload)
        except ValidationError as exc:
            raise MCPConnectorError(str(exc)) from exc
        contact = Contact(
            organization_id=organization_id,
            name=contact_in.name.strip(),
            job_title=self._clean_optional(contact_in.job_title),
            email=self._clean_optional(contact_in.email),
            phone=self._clean_optional(contact_in.phone),
            notes=self._clean_optional(contact_in.notes),
        )
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return MCPExecutionResponse(
            resource="contacts",
            operation=request.operation,
            data=jsonable_encoder(ContactRead.from_orm(contact).dict()),
            meta={"id": contact.id, "organization_id": contact.organization_id},
        )

    async def _update_contact(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        contact = await self._require_contact(session, request.identifier)
        if not request.payload:
            raise MCPConnectorError("Update payload is required")
        try:
            contact_update = ContactUpdate(**request.payload)
        except ValidationError as exc:
            raise MCPConnectorError(str(exc)) from exc
        data = contact_update.dict(exclude_unset=True)
        updated = False
        if "name" in data and data["name"]:
            cleaned = data["name"].strip()
            if cleaned and cleaned != contact.name:
                contact.name = cleaned
                updated = True
        if "job_title" in data:
            cleaned_job = self._clean_optional(data["job_title"])
            if cleaned_job != contact.job_title:
                contact.job_title = cleaned_job
                updated = True
        if "email" in data:
            cleaned_email = self._clean_optional(data["email"])
            if cleaned_email != contact.email:
                contact.email = cleaned_email
                updated = True
        if "phone" in data:
            cleaned_phone = self._clean_optional(data["phone"])
            if cleaned_phone != contact.phone:
                contact.phone = cleaned_phone
                updated = True
        if "notes" in data:
            cleaned_notes = self._clean_optional(data["notes"])
            if cleaned_notes != contact.notes:
                contact.notes = cleaned_notes
                updated = True
        if updated:
            contact.updated_at = utcnow()
            await session.commit()
            await session.refresh(contact)
        return MCPExecutionResponse(
            resource="contacts",
            operation=request.operation,
            data=jsonable_encoder(ContactRead.from_orm(contact).dict()),
            meta={"id": contact.id, "organization_id": contact.organization_id, "updated": updated},
        )

    async def _delete_contact(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        contact = await self._require_contact(session, request.identifier)
        await session.delete(contact)
        await session.commit()
        return MCPExecutionResponse(
            resource="contacts",
            operation=request.operation,
            data=None,
            meta={"id": contact.id, "organization_id": contact.organization_id, "deleted": True},
        )

    async def _require_contact(self, session: AsyncSession, identifier: Any | None) -> Contact:
        if identifier is None:
            raise MCPConnectorError("Contact identifier is required")
        query = select(Contact)
        if self._looks_like_int(identifier):
            query = query.where(Contact.id == int(identifier))
        else:
            raise MCPConnectorError("Contacts must be looked up by numeric identifier")
        result = await session.execute(query)
        contact = result.scalar_one_or_none()
        if contact is None:
            raise MCPConnectorError("Contact not found", status_code=status.HTTP_404_NOT_FOUND)
        return contact

    async def _execute_automations(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.operation == MCPOperation.LIST:
            return await self._with_session(lambda session: self._list_automations(session, request))
        if request.operation == MCPOperation.RETRIEVE:
            return await self._with_session(lambda session: self._get_automation(session, request))
        if request.operation == MCPOperation.UPDATE:
            return await self._with_session(lambda session: self._update_automation(session, request))
        raise MCPConnectorError("Operation not supported for automations")

    async def _list_automations(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        query = select(Automation).order_by(Automation.name.asc())
        if request.limit:
            query = query.limit(request.limit)
        if request.offset:
            query = query.offset(request.offset)
        result = await session.execute(query)
        automations = result.scalars().all()
        payload = [AutomationRead.from_orm(automation).dict() for automation in automations]
        return MCPExecutionResponse(
            resource="automations",
            operation=request.operation,
            data=jsonable_encoder(payload),
            meta={"count": len(payload)},
        )

    async def _get_automation(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        automation = await self._require_automation(session, request.identifier)
        return MCPExecutionResponse(
            resource="automations",
            operation=request.operation,
            data=jsonable_encoder(AutomationRead.from_orm(automation).dict()),
            meta={"id": automation.id},
        )

    async def _update_automation(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        automation = await self._require_automation(session, request.identifier)
        if not request.payload:
            raise MCPConnectorError("Update payload is required")
        try:
            automation_update = AutomationUpdate(**request.payload)
        except ValidationError as exc:
            raise MCPConnectorError(str(exc)) from exc
        data = automation_update.dict(exclude_unset=True, exclude_none=True)
        if not data:
            return MCPExecutionResponse(
                resource="automations",
                operation=request.operation,
                data=jsonable_encoder(AutomationRead.from_orm(automation).dict()),
                meta={"id": automation.id, "updated": False},
            )
        for field, value in data.items():
            if hasattr(value, "dict"):
                setattr(automation, field, value.dict())
            else:
                setattr(automation, field, value)
        await session.commit()
        await session.refresh(automation)
        return MCPExecutionResponse(
            resource="automations",
            operation=request.operation,
            data=jsonable_encoder(AutomationRead.from_orm(automation).dict()),
            meta={"id": automation.id, "updated": True},
        )

    async def _require_automation(self, session: AsyncSession, identifier: Any | None) -> Automation:
        if identifier is None:
            raise MCPConnectorError("Automation identifier is required")
        query = select(Automation)
        if self._looks_like_int(identifier):
            query = query.where(Automation.id == int(identifier))
        else:
            raise MCPConnectorError("Automations must be looked up by numeric identifier")
        result = await session.execute(query)
        automation = result.scalar_one_or_none()
        if automation is None:
            raise MCPConnectorError("Automation not found", status_code=status.HTTP_404_NOT_FOUND)
        return automation

    async def _execute_webhooks(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.operation == MCPOperation.LIST:
            return await self._with_session(lambda session: self._list_webhooks(session, request))
        if request.operation == MCPOperation.RETRIEVE:
            return await self._with_session(lambda session: self._get_webhook(session, request))
        if request.operation == MCPOperation.UPDATE:
            return await self._with_session(lambda session: self._update_webhook(session, request))
        raise MCPConnectorError("Operation not supported for webhook deliveries")

    async def _list_webhooks(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        filters = request.filters or {}
        query = select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc())
        status_filter = filters.get("status")
        if status_filter:
            try:
                status_value = WebhookStatus(status_filter)
            except ValueError as exc:
                raise MCPConnectorError("Invalid webhook status filter") from exc
            query = query.where(WebhookDelivery.status == status_value.value)
        if request.limit:
            query = query.limit(request.limit)
        if request.offset:
            query = query.offset(request.offset)
        result = await session.execute(query)
        deliveries = result.scalars().all()
        payload = [WebhookDeliveryRead.from_orm(delivery).dict() for delivery in deliveries]
        return MCPExecutionResponse(
            resource="webhook-deliveries",
            operation=request.operation,
            data=jsonable_encoder(payload),
            meta={"count": len(payload)},
        )

    async def _get_webhook(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        delivery = await self._require_webhook(session, request.identifier)
        return MCPExecutionResponse(
            resource="webhook-deliveries",
            operation=request.operation,
            data=jsonable_encoder(WebhookDeliveryRead.from_orm(delivery).dict()),
            meta={"id": delivery.id, "event_id": delivery.event_id},
        )

    async def _update_webhook(self, session: AsyncSession, request: MCPExecutionRequest) -> MCPExecutionResponse:
        delivery = await self._require_webhook(session, request.identifier)
        if not request.payload:
            raise MCPConnectorError("Update payload is required")
        payload = dict(request.payload)
        updated = False
        if "status" in payload:
            try:
                status_value = WebhookStatus(str(payload["status"]))
            except ValueError as exc:
                raise MCPConnectorError("Invalid webhook status") from exc
            delivery.status = status_value.value
            updated = True
        for field in ("last_attempt_at", "next_retry_at"):
            if field in payload and payload[field]:
                timestamp = self._parse_datetime(payload[field])
                setattr(delivery, field, timestamp)
                updated = True
        if updated:
            delivery.updated_at = utcnow()
            await session.commit()
            await session.refresh(delivery)
        return MCPExecutionResponse(
            resource="webhook-deliveries",
            operation=request.operation,
            data=jsonable_encoder(WebhookDeliveryRead.from_orm(delivery).dict()),
            meta={"id": delivery.id, "event_id": delivery.event_id, "updated": updated},
        )

    async def _require_webhook(self, session: AsyncSession, identifier: Any | None) -> WebhookDelivery:
        if identifier is None:
            raise MCPConnectorError("Webhook identifier is required")
        query = select(WebhookDelivery)
        if self._looks_like_int(identifier):
            query = query.where(WebhookDelivery.id == int(identifier))
        else:
            query = query.where(WebhookDelivery.event_id == str(identifier))
        result = await session.execute(query)
        delivery = result.scalar_one_or_none()
        if delivery is None:
            raise MCPConnectorError("Webhook delivery not found", status_code=status.HTTP_404_NOT_FOUND)
        return delivery

    async def _execute_tickets(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.operation == MCPOperation.LIST:
            return await self._list_tickets(request)
        if request.operation == MCPOperation.RETRIEVE:
            return await self._get_ticket(request)
        if request.operation == MCPOperation.CREATE:
            return await self._create_ticket(request)
        if request.operation == MCPOperation.UPDATE:
            return await self._update_ticket(request)
        if request.operation == MCPOperation.APPEND_REPLY:
            return await self._append_ticket_reply(request)
        raise MCPConnectorError("Operation not supported for tickets")

    async def _list_tickets(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        now = utcnow()
        records = await fetch_ticket_records(now)
        filters = request.filters or {}
        filtered = [ticket for ticket in records if self._match_ticket(ticket, filters)]
        start = request.offset or 0
        end = start + (request.limit or len(filtered))
        slice_records = filtered[start:end]
        encoded = [self._serialize_ticket(ticket) for ticket in slice_records]
        return MCPExecutionResponse(
            resource="tickets",
            operation=request.operation,
            data=encoded,
            meta={"count": len(filtered), "returned": len(encoded)},
        )

    async def _get_ticket(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.identifier is None:
            raise MCPConnectorError("Ticket identifier is required")
        records = await fetch_ticket_records(utcnow())
        identifier = str(request.identifier)
        for ticket in records:
            if str(ticket.get("id")) == identifier:
                return MCPExecutionResponse(
                    resource="tickets",
                    operation=request.operation,
                    data=self._serialize_ticket(ticket),
                    meta={"id": identifier},
                )
        override = await ticket_store.get_override(identifier)
        if override is not None:
            return MCPExecutionResponse(
                resource="tickets",
                operation=request.operation,
                data=self._serialize_ticket({"id": identifier, **override}),
                meta={"id": identifier},
            )
        raise MCPConnectorError("Ticket not found", status_code=status.HTTP_404_NOT_FOUND)

    async def _create_ticket(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        payload = request.payload or {}
        missing = [field for field in TICKET_MUTABLE_FIELDS if not payload.get(field)]
        if missing:
            raise MCPConnectorError(f"Missing required fields: {', '.join(missing)}")
        records = await fetch_ticket_records(utcnow())
        existing_ids = [ticket["id"] for ticket in records]
        ticket = await ticket_store.create_ticket(existing_ids=existing_ids, **{field: str(payload[field]).strip() for field in TICKET_MUTABLE_FIELDS})
        return MCPExecutionResponse(
            resource="tickets",
            operation=request.operation,
            data=self._serialize_ticket(ticket),
            meta={"id": ticket.get("id")},
        )

    async def _update_ticket(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.identifier is None:
            raise MCPConnectorError("Ticket identifier is required")
        payload = request.payload or {}
        missing = [field for field in TICKET_MUTABLE_FIELDS if not payload.get(field)]
        if missing:
            raise MCPConnectorError(f"Missing required fields: {', '.join(missing)}")
        ticket = await ticket_store.update_ticket(
            str(request.identifier),
            **{field: str(payload[field]).strip() for field in TICKET_MUTABLE_FIELDS},
        )
        merged = {"id": str(request.identifier), **ticket}
        return MCPExecutionResponse(
            resource="tickets",
            operation=request.operation,
            data=self._serialize_ticket(merged),
            meta={"id": str(request.identifier)},
        )

    async def _append_ticket_reply(self, request: MCPExecutionRequest) -> MCPExecutionResponse:
        if request.identifier is None:
            raise MCPConnectorError("Ticket identifier is required")
        payload = request.payload or {}
        missing = [field for field in REPLY_FIELDS if not payload.get(field)]
        if missing:
            raise MCPConnectorError(f"Missing required fields: {', '.join(missing)}")
        reply = await ticket_store.append_reply(
            str(request.identifier),
            actor=str(payload["actor"]).strip(),
            channel=str(payload["channel"]).strip(),
            summary=str(payload["summary"]).strip(),
            message=str(payload["message"]).strip(),
        )
        return MCPExecutionResponse(
            resource="tickets",
            operation=request.operation,
            data=jsonable_encoder(reply),
            meta={"id": str(request.identifier)},
        )

    def _serialize_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]:
        encoded = jsonable_encoder(ticket)
        if "history" in ticket:
            history: Iterable[dict[str, Any]] = ticket["history"]  # type: ignore[assignment]
            encoded["history"] = []
            for entry in history:
                entry_encoded = jsonable_encoder(entry)
                timestamp = entry.get("timestamp_dt")
                if isinstance(timestamp, datetime):
                    entry_encoded.setdefault(
                        "timestamp_iso",
                        timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    )
                encoded["history"].append(entry_encoded)
        return encoded

    def _match_ticket(self, ticket: dict[str, Any], filters: dict[str, Any]) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            if value is None or value == "":
                continue
            expected = str(value).strip().lower()
            actual = str(ticket.get(key, "")).strip().lower()
            if actual != expected:
                return False
        return True

    @staticmethod
    def _looks_like_int(value: Any) -> bool:
        try:
            int(value)
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _clean_optional(value: Any | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            timestamp = value
        else:
            try:
                timestamp = datetime.fromisoformat(str(value))
            except ValueError as exc:
                raise MCPConnectorError("Invalid datetime format") from exc
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)


connector = ChatGPTMCPConnector()
