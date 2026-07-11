"""Tests for the folder-sync connector."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from httpx import AsyncClient

from app.models.user import User, UserRole

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

SYNC = "/api/v1/connectors/folder/sync"


async def test_folder_sync_is_idempotent(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders, tmp_path: Path
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")

    drop = tmp_path / "drop"
    (drop / "nested").mkdir(parents=True)
    (drop / "policy.md").write_bytes(b"# Policy\n\nHelmets are mandatory on site.")
    (drop / "nested" / "notes.txt").write_bytes(b"Visitors must sign in at the gate.")
    (drop / "ignore.xyz").write_bytes(b"binary junk")

    first = await client.post(SYNC, headers=admin, json={"path": str(drop)})
    assert first.status_code == 200, first.text
    report = first.json()
    assert report["scanned"] == 3
    assert sorted(report["ingested"]) == ["notes.txt", "policy.md"]
    assert report["skipped_unsupported"] == 1
    assert report["failed"] == []

    # Re-sync: nothing new, nothing duplicated.
    second = (await client.post(SYNC, headers=admin, json={"path": str(drop)})).json()
    assert second["ingested"] == []
    assert second["skipped_existing"] == 2

    docs = (await client.get("/api/v1/documents", headers=admin)).json()
    assert len(docs) == 2

    # Synced content is immediately answerable.
    answer = await client.post(
        "/api/v1/query", headers=admin, json={"query": "Where must visitors sign in?"}
    )
    assert answer.json()["answered"] is True


async def test_folder_sync_rejects_bad_path_and_non_admin(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders, tmp_path: Path
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    await make_user("member@example.com", role=UserRole.USER)
    admin = await auth_headers("admin@example.com")
    member = await auth_headers("member@example.com")

    missing = await client.post(SYNC, headers=admin, json={"path": str(tmp_path / "nope")})
    assert missing.status_code == 422

    forbidden = await client.post(SYNC, headers=member, json={"path": str(tmp_path)})
    assert forbidden.status_code == 403
