"""Shared pytest fixtures.

Tests run against an in-memory SQLite database (StaticPool keeps a single
shared connection) so the suite is fully self-contained — no external services.

The environment overrides below run BEFORE any ``app`` import so the settings
singleton is built with offline providers, regardless of what a developer's
local ``.env`` selects (qdrant, openai, ...). Tests must never touch real
services or spend API credits.
"""

from __future__ import annotations

import os

os.environ.update(
    {
        "ENVIRONMENT": "local",
        "VECTOR_STORE_PROVIDER": "memory",
        "EMBEDDER_PROVIDER": "hashing",
        "LLM_PROVIDER": "extractive",
        "SPARSE_PROVIDER": "local-bm25",
        "RERANKER_PROVIDER": "lexical",
        "PARSER_PROVIDER": "local",
        "OCR_PROVIDER": "rapidocr",
        "EMBEDDING_DIMENSION": "384",
        "AUTO_MIGRATE": "false",
        "RATE_LIMIT_ENABLED": "false",
    }
)

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models
from app.api.deps import get_storage
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.user import User, UserRole
from app.schemas.user import UserCreate
from app.services.ingestion.factory import get_vector_store
from app.services.retrieval.factory import get_sparse_index
from app.services.storage import LocalFileStorage
from app.services.users import UserService


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_retrieval_state() -> None:
    """Isolate process-wide retrieval singletons between tests."""
    get_vector_store().clear()  # type: ignore[attr-defined]
    get_sparse_index().invalidate()


@pytest.fixture
def app(db_session: AsyncSession, tmp_path: Path) -> FastAPI:
    application = create_app()
    storage = LocalFileStorage(str(tmp_path / "storage"))

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_storage] = lambda: storage
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture
def make_user(db_session: AsyncSession) -> Callable[..., Awaitable[User]]:
    async def _make(
        email: str,
        password: str = "supersecret",
        role: UserRole = UserRole.USER,
    ) -> User:
        return await UserService(db_session).create(
            UserCreate(email=email, password=password), role=role
        )

    return _make


@pytest.fixture
def auth_headers(client: AsyncClient) -> Callable[..., Awaitable[dict[str, str]]]:
    async def _headers(email: str, password: str = "supersecret") -> dict[str, str]:
        resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    return _headers
