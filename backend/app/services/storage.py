"""Object storage abstraction and a local-filesystem implementation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStorage(Protocol):
    """Content-addressable blob storage keyed by an opaque string."""

    async def save(self, key: str, data: bytes) -> None: ...
    async def load(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def materialize(self, key: str) -> str:
        """Return a local filesystem path for file-based readers (parsers)."""
        ...


class LocalFileStorage:
    """Stores blobs under a base directory. Suitable for local dev and tests."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self._base / key).resolve()
        if not path.is_relative_to(self._base):
            raise ValueError("Invalid storage key (path traversal detected).")
        return path

    async def save(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def load(self, key: str) -> bytes:
        return await asyncio.to_thread(self._resolve(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(path.unlink, True)

    async def materialize(self, key: str) -> str:
        return str(self._resolve(key))
