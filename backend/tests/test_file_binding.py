import io
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.core.database import engine

@pytest.mark.asyncio
async def test_file_binding_and_ownership_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "vlm_enabled", False)
    monkeypatch.setattr(settings, "overseas_api_enabled", False)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Log in to get access token for User A
            login_response = await ac.post(
                "/api/v1/auth/login",
                json={"email": "christest@sibionics.com", "password": "password123"},
            )
            assert login_response.status_code == 200
            token_a = login_response.json()["data"]["access_token"]
            headers_a = {"Authorization": f"Bearer {token_a}"}

            # 2. Upload a file for User A
            file_content = b"fake image content data"
            file_io = io.BytesIO(file_content)
            upload_response = await ac.post(
                "/api/v1/files/upload",
                files={"file": ("test_image.png", file_io, "image/png")},
                headers=headers_a,
            )
            assert upload_response.status_code == 200, upload_response.text
            file_data = upload_response.json()["data"]
            assert file_data["filename"] == "test_image.png"
            assert file_data["mime_type"] == "image/png"
            file_id = file_data["id"]

            # 3. Retrieve the uploaded file metadata and content
            get_response = await ac.get(f"/api/v1/files/{file_id}", headers=headers_a)
            assert get_response.status_code == 200
            assert get_response.content == file_content

            # 4. Try retrieving without auth or with invalid token
            get_fail_response = await ac.get(f"/api/v1/files/{file_id}")
            assert get_fail_response.status_code == 401

            # 5. Submit a single detection with the uploaded file
            # We need a valid device SN. Let's use P2251212806JND44 which is a mock device SN.
            detect_response = await ac.post(
                "/api/v1/detections",
                json={
                    "serialNo": "P2251212806JND44",
                    "faultCategory": "Application failure",
                    "fileIds": [file_id],
                },
                headers=headers_a,
            )
            assert detect_response.status_code == 200, detect_response.text
            record = detect_response.json()["data"]
            
            # Verify status is complete or processing
            assert record["status"] in ("completed", "processing")
            
            # Get detection details and verify enriched evidence has files_metadata
            record_id = record["id"]
            get_detect_response = await ac.get(
                f"/api/v1/detections/{record_id}",
                headers=headers_a,
            )
            assert get_detect_response.status_code == 200
            enriched_record = get_detect_response.json()["data"]
            
            # Check files_metadata is present in evidence
            evidence = enriched_record.get("evidence") or {}
            assert "files_metadata" in evidence
            files_metadata = evidence["files_metadata"]
            assert len(files_metadata) == 1
            assert files_metadata[0]["file_id"] == file_id
            assert files_metadata[0]["filename"] == "test_image.png"

            # 6. Try to use a non-existent file ID in detection
            detect_fail_response = await ac.post(
                "/api/v1/detections",
                json={
                    "serialNo": "P2251212806JND44",
                    "faultCategory": "Application failure",
                    "fileIds": ["12345678-1234-5678-1234-567812345678"],
                },
                headers=headers_a,
            )
            # BusinessValidationError maps to 422 Unprocessable Entity
            assert detect_fail_response.status_code == 422
            assert "does not exist" in detect_fail_response.json()["message"]

            # 7. Submit a batch detection with uploaded file IDs bound per device.
            batch_upload_response = await ac.post(
                "/api/v1/files/upload",
                files={"file": ("batch_image.png", io.BytesIO(file_content), "image/png")},
                headers=headers_a,
            )
            assert batch_upload_response.status_code == 200, batch_upload_response.text
            batch_file_id = batch_upload_response.json()["data"]["id"]

            batch_response = await ac.post(
                "/api/v1/detections/batch",
                json={
                    "serialNos": ["P2251212806JND44", "P2251212813RVK19"],
                    "faultCategory": "Application failure",
                    "deviceFiles": {
                        "P2251212806JND44": [batch_file_id],
                        "P2251212813RVK19": [],
                    },
                },
                headers=headers_a,
            )
            assert batch_response.status_code == 200, batch_response.text
            batch = batch_response.json()["data"]
            first_record = next(record for record in batch["records"] if record["sn"] == "P2251212806JND44")
            assert first_record["evidence"]["file_ids"] == [batch_file_id]
    finally:
        await engine.dispose()
