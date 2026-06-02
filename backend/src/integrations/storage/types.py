from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    storage_backend: str
    object_key: str
    file_size: int


class StorageBackend(Protocol):
    name: str

    async def save_bytes(
        self, *, key: str, data: bytes, content_type: str | None = None
    ) -> StoredObject:
        """Persist bytes and return the stored object pointer."""

    async def get_bytes(self, object_key: str) -> bytes:
        """Read object bytes for backend-only consumers such as VLM encoding."""

    async def exists(self, object_key: str) -> bool:
        """Return whether an object exists."""

    async def get_download_url(self, object_key: str) -> str | None:
        """Return a direct download URL when the backend supports one."""
