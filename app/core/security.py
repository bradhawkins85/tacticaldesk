from __future__ import annotations

from secrets import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException, status
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(password, hashed_password)


async def require_maintenance_token(
    maintenance_token: Annotated[str, Header(alias="X-Maintenance-Token")],
) -> None:
    settings = get_settings()
    if not settings.maintenance_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Maintenance token is not configured",
        )

    if not compare_digest(maintenance_token, settings.maintenance_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid maintenance token")

    return None
