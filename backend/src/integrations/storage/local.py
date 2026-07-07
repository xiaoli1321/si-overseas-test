from __future__ import annotations

import asyncio
import os
from pathlib import Path

from src.core.exceptions import NotFoundError
from src.integrations.storage.types import StoredObject


class LocalStorageBackend:
    name = "local"

    def __init__(self, upload_dir: str) -> None:
        self.upload_dir = upload_dir

    async def save_bytes(
        self, *, key: str, data: bytes, content_type: str | None = None
    ) -> StoredObject:
        path = Path(self.upload_dir) / key
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return StoredObject(
            storage_backend=self.name, object_key=str(path), file_size=len(data)
        )

    async def get_bytes(self, object_key: str) -> bytes:
        path = Path(object_key)
        if not path.is_file():
            raise NotFoundError("Physical file was not found on disk.")
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, object_key: str) -> bool:
        return await asyncio.to_thread(os.path.exists, object_key)

    async def get_download_url(self, object_key: str) -> str | None:
        return None
