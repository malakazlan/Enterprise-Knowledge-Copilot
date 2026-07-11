"""API key lifecycle: generation, verification, listing, revocation.

Key format: ``ekc_<43 urlsafe chars>``. The full secret is returned exactly
once at creation; only its SHA-256 hash is persisted. Lookup goes through the
indexed prefix, then the hash is compared in constant time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.apikey import ApiKey
from app.models.user import UserRole

KEY_SCHEME = "ekc"
PREFIX_LENGTH = 12
# last_used_at is refreshed at most this often to avoid a write per request.
_LAST_USED_REFRESH = timedelta(seconds=60)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; values are always stored as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class ApiKeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        name: str,
        role: UserRole = UserRole.USER,
        expires_in_days: int | None = None,
        created_by: uuid.UUID | None = None,
    ) -> tuple[ApiKey, str]:
        """Create a key; returns the model and the full secret (shown once)."""
        raw_key = f"{KEY_SCHEME}_{secrets.token_urlsafe(32)}"
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            if expires_in_days is not None
            else None
        )
        api_key = ApiKey(
            id=uuid.uuid4(),
            name=name,
            key_prefix=raw_key[:PREFIX_LENGTH],
            key_hash=_hash_key(raw_key),
            role=role,
            created_by=created_by,
            expires_at=expires_at,
        )
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)
        return api_key, raw_key

    async def authenticate(self, presented: str) -> ApiKey | None:
        """Return the active key matching ``presented``, or ``None``."""
        if not presented.startswith(f"{KEY_SCHEME}_") or len(presented) < PREFIX_LENGTH + 8:
            return None

        result = await self.db.execute(
            select(ApiKey).where(
                ApiKey.key_prefix == presented[:PREFIX_LENGTH],
                ApiKey.revoked_at.is_(None),
            )
        )
        presented_hash = _hash_key(presented)
        now = datetime.now(timezone.utc)

        for api_key in result.scalars():
            if not hmac.compare_digest(api_key.key_hash, presented_hash):
                continue
            if api_key.expires_at is not None and _as_utc(api_key.expires_at) <= now:
                return None
            if (
                api_key.last_used_at is None
                or now - _as_utc(api_key.last_used_at) > _LAST_USED_REFRESH
            ):
                api_key.last_used_at = now
                await self.db.commit()
            return api_key
        return None

    async def list_keys(self) -> Sequence[ApiKey]:
        result = await self.db.execute(select(ApiKey).order_by(desc(ApiKey.created_at)))
        return result.scalars().all()

    async def revoke(self, key_id: uuid.UUID) -> ApiKey | None:
        """Soft-revoke; idempotent. Returns ``None`` for unknown ids."""
        api_key = await self.db.get(ApiKey, key_id)
        if api_key is None:
            return None
        if api_key.revoked_at is None:
            api_key.revoked_at = datetime.now(timezone.utc)
            await self.db.commit()
        return api_key
