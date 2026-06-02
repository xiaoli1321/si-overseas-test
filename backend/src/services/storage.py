from __future__ import annotations

import base64
import mimetypes
import posixpath
from pathlib import PurePosixPath
import uuid

from src.core.config import get_settings
from src.integrations.storage import StoredObject, get_storage_backend
from src.models.tables import UploadedFile


def build_object_key(*, user_id: int, file_id: str, filename: str) -> str:
    _, ext = posixpath.splitext(filename or "")
    safe_ext = ext if len(ext) <= 16 else ""
    prefix = get_settings().oss_key_prefix.strip("/")
    parts = [part for part in (prefix, str(user_id), f"{file_id}{safe_ext}") if part]
    return str(PurePosixPath(*parts))


def new_file_id(prefix: str = "file") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


async def save_bytes_to_storage(
    *,
    user_id: int,
    file_id: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> StoredObject:
    object_key = build_object_key(user_id=user_id, file_id=file_id, filename=filename)
    storage = get_storage_backend(get_settings())
    return await storage.save_bytes(
        key=object_key, data=data, content_type=content_type
    )


async def stored_file_exists(file: UploadedFile) -> bool:
    storage = get_storage_backend(get_settings())
    return await storage.exists(file.object_key)


async def get_stored_file_bytes(file: UploadedFile) -> bytes:
    storage = get_storage_backend(get_settings())
    return await storage.get_bytes(file.object_key)


async def get_stored_file_download_url(file: UploadedFile) -> str | None:
    storage = get_storage_backend(get_settings())
    return await storage.get_download_url(file.object_key)


async def get_vlm_reference(file: UploadedFile) -> str:
    if file.storage_backend == "local":
        return file.object_key

    data = await get_stored_file_bytes(file)
    mime_type = (
        file.mime_type
        or mimetypes.guess_type(file.filename)[0]
        or "application/octet-stream"
    )
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
