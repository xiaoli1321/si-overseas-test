from __future__ import annotations

from src.core.config import Settings
from src.core.exceptions import BusinessValidationError
from src.integrations.storage.local import LocalStorageBackend
from src.integrations.storage.oss import OssStorageBackend
from src.integrations.storage.types import StorageBackend


def get_storage_backend(settings: Settings) -> StorageBackend:
    backend = settings.file_storage_backend.lower()
    if backend == "local":
        return LocalStorageBackend(settings.upload_dir)
    if backend == "oss":
        return OssStorageBackend(
            endpoint=settings.oss_endpoint,
            bucket=settings.oss_bucket,
            access_key_id=settings.oss_access_key_id,
            access_key_secret=settings.oss_access_key_secret,
            public_base_url=settings.oss_public_base_url,
            signed_url_expire_seconds=settings.oss_signed_url_expire_seconds,
            use_signed_url=settings.oss_use_signed_url,
        )
    raise BusinessValidationError(
        f"Unsupported file storage backend: {settings.file_storage_backend}"
    )
