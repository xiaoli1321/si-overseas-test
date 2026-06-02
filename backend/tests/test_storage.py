from pathlib import Path

import pytest

from src.core.exceptions import BusinessValidationError
from src.integrations.storage import get_storage_backend
from src.integrations.storage.oss import _normalize_endpoint
from src.services.storage import save_bytes_to_storage


@pytest.mark.asyncio
async def test_local_storage_should_save_bytes_under_configured_upload_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "file_storage_backend", "local")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "oss_key_prefix", "diagnostic-images")

    stored = await save_bytes_to_storage(
        user_id=7,
        file_id="file-test",
        filename="photo.png",
        data=b"image-bytes",
        content_type="image/png",
    )

    assert stored.storage_backend == "local"
    assert stored.file_size == len(b"image-bytes")
    assert stored.object_key == str(tmp_path / "diagnostic-images" / "7" / "file-test.png")
    assert (tmp_path / "diagnostic-images" / "7" / "file-test.png").read_bytes() == b"image-bytes"


def test_oss_storage_should_require_endpoint_bucket_and_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "file_storage_backend", "oss")
    monkeypatch.setattr(settings, "oss_endpoint", "")
    monkeypatch.setattr(settings, "oss_bucket", "si-agent-overseas-test")
    monkeypatch.setattr(settings, "oss_access_key_id", "")
    monkeypatch.setattr(settings, "oss_access_key_secret", "")

    with pytest.raises(BusinessValidationError, match="OSS storage is enabled"):
        get_storage_backend(settings)


def test_oss_endpoint_normalization_should_accept_bucket_host_address() -> None:
    endpoint = "https://si-agent-overseas-test.oss-eu-central-1-internal.aliyuncs.com"

    assert _normalize_endpoint(endpoint, "si-agent-overseas-test") == "https://oss-eu-central-1-internal.aliyuncs.com"
