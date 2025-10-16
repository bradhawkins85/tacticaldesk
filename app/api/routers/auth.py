from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import PasswordTooLongError, hash_password, verify_password
from app.models import User
from app.schemas import LoginRequest, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, session: AsyncSession = Depends(get_session)) -> UserRead:
    result = await session.execute(select(func.count()).select_from(User))
    user_count = result.scalar_one()

    if user_count > 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is closed")

    try:
        hashed = hash_password(user_in.password)
    except PasswordTooLongError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    user = User(email=user_in.email, hashed_password=hashed, is_super_admin=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserRead.from_orm(user)


@router.post("/login", response_model=UserRead)
async def login_user(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> UserRead:
    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return UserRead.from_orm(user)
