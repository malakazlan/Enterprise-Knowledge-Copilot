"""User persistence and authentication logic."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate


class UserService:
    """Data-access and auth operations for :class:`User`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def list_users(self, *, limit: int = 50, offset: int = 0) -> Sequence[User]:
        result = await self.db.execute(
            select(User).order_by(User.created_at).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def create(self, data: UserCreate, *, role: UserRole | None = None) -> User:
        email = data.email.lower()
        if await self.get_by_email(email) is not None:
            raise ConflictError("A user with this email already exists.")

        if role is None:
            # Self-hosted bootstrap: the first account administers the deployment.
            count = (await self.db.execute(select(func.count(User.id)))).scalar_one()
            role = UserRole.ADMIN if count == 0 else UserRole.USER

        user = User(
            email=email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            role=role,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_by_email(email)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
