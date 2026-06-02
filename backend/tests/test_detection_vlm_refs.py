import pytest

from src.models.tables import UploadedFile
from src.services.detections import _vlm_refs_from_uploaded_files


@pytest.mark.asyncio
async def test_vlm_refs_from_uploaded_files_should_use_object_keys_in_file_id_order() -> None:
    files = [
        UploadedFile(
            id="file-b",
            user_id=7,
            filename="second.png",
            storage_backend="local",
            object_key="uploads/7/file-b.png",
            file_size=20,
        ),
        UploadedFile(
            id="file-a",
            user_id=7,
            filename="first.png",
            storage_backend="local",
            object_key="uploads/7/file-a.png",
            file_size=10,
        ),
    ]

    refs = await _vlm_refs_from_uploaded_files(["file-a", "file-b"], files)

    assert refs == ["uploads/7/file-a.png", "uploads/7/file-b.png"]
