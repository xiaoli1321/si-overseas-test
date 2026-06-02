from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse, urlunparse

from src.core.exceptions import BusinessValidationError, NotFoundError
from src.core.logging import log_context
from src.integrations.storage.types import StoredObject

logger = logging.getLogger(__name__)


class OssStorageBackend:
    name = "oss"

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key_id: str,
        access_key_secret: str,
        public_base_url: str,
        signed_url_expire_seconds: int,
        use_signed_url: bool,
    ) -> None:
        if not endpoint or not bucket or not access_key_id or not access_key_secret:
            raise BusinessValidationError(
                "OSS storage is enabled but OSS endpoint, bucket, or credentials are missing."
            )

        try:
            import oss2
        except ImportError as exc:
            raise BusinessValidationError(
                "OSS storage requires the oss2 package to be installed."
            ) from exc

        self._oss2 = oss2
        self._bucket = oss2.Bucket(
            oss2.Auth(access_key_id, access_key_secret),
            _normalize_endpoint(endpoint, bucket),
            bucket,
        )
        self._public_base_url = public_base_url.rstrip("/")
        self._signed_url_expire_seconds = signed_url_expire_seconds
        self._use_signed_url = use_signed_url

    async def save_bytes(
        self, *, key: str, data: bytes, content_type: str | None = None
    ) -> StoredObject:
        headers = {"Content-Type": content_type} if content_type else None
        await asyncio.to_thread(self._bucket.put_object, key, data, headers=headers)
        logger.info(
            "Uploaded object to OSS",
            extra=log_context("storage.oss_upload", object_key=key, size=len(data)),
        )
        return StoredObject(
            storage_backend=self.name, object_key=key, file_size=len(data)
        )

    async def get_bytes(self, object_key: str) -> bytes:
        try:
            result = await asyncio.to_thread(self._bucket.get_object, object_key)
            return await asyncio.to_thread(result.read)
        except self._oss2.exceptions.NoSuchKey as exc:
            raise NotFoundError("Stored OSS object was not found.") from exc

    async def exists(self, object_key: str) -> bool:
        return bool(await asyncio.to_thread(self._bucket.object_exists, object_key))

    async def get_download_url(self, object_key: str) -> str | None:
        if self._public_base_url and not self._use_signed_url:
            return f"{self._public_base_url}/{object_key.lstrip('/')}"
        if self._use_signed_url:
            return await asyncio.to_thread(
                self._bucket.sign_url,
                "GET",
                object_key,
                self._signed_url_expire_seconds,
            )
        return None


def _normalize_endpoint(endpoint: str, bucket: str) -> str:
    parsed = urlparse(endpoint)
    if not parsed.netloc:
        parsed = urlparse(f"https://{endpoint}")

    bucket_prefix = f"{bucket}."
    if parsed.netloc.startswith(bucket_prefix):
        parsed = parsed._replace(netloc=parsed.netloc[len(bucket_prefix) :])

    return urlunparse(parsed)
