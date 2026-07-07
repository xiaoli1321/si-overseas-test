import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.core.database import AsyncSessionLocal
from src.main import app
from src.models.tables import AuditLog, DetectRecord, User
from src.repositories.store import get_user_by_email
from src.core.security import hash_password


async def _latest_audit(action: str, *, target_id: str) -> AuditLog | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.action == action, AuditLog.target_id == target_id)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _user_by_email(email: str) -> User:
    async with AsyncSessionLocal() as db:
        user = await get_user_by_email(db, email)
        assert user is not None
        return user


async def _ensure_user_b() -> None:
    async with AsyncSessionLocal() as db:
        user = await get_user_by_email(db, "dealertest@sibionics.com")
        if not user:
            user_b = User(
                distributor_name="Dealer Test",
                username="dealertest@sibionics.com",
                password=hash_password("password123"),
                role="dealer",
            )
            db.add(user_b)
            await db.commit()


@pytest.mark.asyncio
async def test_delete_record_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    # Disable VLM and external APIs to avoid external calls
    from src.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "vlm_enabled", False)
    monkeypatch.setattr(settings, "overseas_api_enabled", False)

    # Ensure User B exists in the database
    await _ensure_user_b()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Log in User A
        login_a = await ac.post(
            "/api/v1/auth/login",
            json={"email": "christest@sibionics.com", "password": "password123"},
        )
        assert login_a.status_code == 200
        token_a = login_a.json()["data"]["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}
        user_a = await _user_by_email("christest@sibionics.com")

        # 2. Log in User B (another dealer)
        login_b = await ac.post(
            "/api/v1/auth/login",
            json={"email": "dealertest@sibionics.com", "password": "password123"},
        )
        assert login_b.status_code == 200
        token_b = login_b.json()["data"]["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 3. User A uploads a file and creates a detection record
        upload_resp = await ac.post(
            "/api/v1/files/upload",
            files={"file": ("test.png", io.BytesIO(b"dummy image content"), "image/png")},
            headers=headers_a,
        )
        assert upload_resp.status_code == 200
        file_id = upload_resp.json()["data"]["id"]

        detect_resp = await ac.post(
            "/api/v1/detections",
            json={
                "serialNo": "P225TESTDELETE001",
                "faultCategory": "Sensor Abnormal",
                "fileIds": [file_id],
            },
            headers=headers_a,
        )
        assert detect_resp.status_code == 200
        record_id = detect_resp.json()["data"]["id"]

        # 4. Verify record is visible in list, stats, and detail for User A
        detail_resp = await ac.get(f"/api/v1/records/{record_id}", headers=headers_a)
        assert detail_resp.status_code == 200
        assert detail_resp.json()["data"]["sn"] == "P225TESTDELETE001"

        list_resp = await ac.get("/api/v1/records", headers=headers_a)
        assert list_resp.status_code == 200
        assert any(item["id"] == record_id for item in list_resp.json()["data"]["items"])

        stats_resp = await ac.get("/api/v1/records/stats", headers=headers_a)
        assert stats_resp.status_code == 200
        stats_before = stats_resp.json()["data"]["total"]

        # 5. Try deleting User A's record using User B's credentials -> expect 404 (due to user isolation)
        delete_fail = await ac.delete(f"/api/v1/records/{record_id}", headers=headers_b)
        assert delete_fail.status_code == 404

        # Verify the record is still visible to User A
        detail_verify = await ac.get(f"/api/v1/records/{record_id}", headers=headers_a)
        assert detail_verify.status_code == 200

        # 6. Delete User A's record using User A's credentials -> expect 200
        delete_success = await ac.delete(f"/api/v1/records/{record_id}", headers=headers_a)
        assert delete_success.status_code == 200
        assert delete_success.json()["data"]["id"] == record_id
        assert delete_success.json()["data"]["isVisibleInWorkbench"] is False

        # 7. Verify record detail returns 404 (Not Found) now
        detail_after = await ac.get(f"/api/v1/records/{record_id}", headers=headers_a)
        assert detail_after.status_code == 404

        # 8. Verify record is excluded from User A's records list
        list_after = await ac.get("/api/v1/records", headers=headers_a)
        assert list_after.status_code == 200
        assert not any(item["id"] == record_id for item in list_after.json()["data"]["items"])

        # 9. Verify record is excluded from User A's stats count
        stats_after_resp = await ac.get("/api/v1/records/stats", headers=headers_a)
        assert stats_after_resp.status_code == 200
        assert stats_after_resp.json()["data"]["total"] == stats_before - 1

        # 10. Verify audit log entry was created
        audit = await _latest_audit("detection.delete", target_id=str(record_id))
        assert audit is not None
        assert audit.user_id == user_a.id
        assert audit.target_type == "detect_record"
        assert audit.event_metadata["serial_no"] == "P225TESTDELETE001"
        assert audit.event_metadata["fault_category"] == "Sensor Abnormal"


@pytest.mark.asyncio
async def test_batch_delete_records_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "vlm_enabled", False)
    monkeypatch.setattr(settings, "overseas_api_enabled", False)

    await _ensure_user_b()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Log in User A
        login_a = await ac.post(
            "/api/v1/auth/login",
            json={"email": "christest@sibionics.com", "password": "password123"},
        )
        token_a = login_a.json()["data"]["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}
        user_a = await _user_by_email("christest@sibionics.com")

        # Create two detection records for User A
        upload_resp = await ac.post(
            "/api/v1/files/upload",
            files={"file": ("test.png", io.BytesIO(b"dummy image content"), "image/png")},
            headers=headers_a,
        )
        file_id = upload_resp.json()["data"]["id"]

        r1_resp = await ac.post(
            "/api/v1/detections",
            json={
                "serialNo": "P225BATCH001",
                "faultCategory": "Sensor Abnormal",
                "fileIds": [file_id],
            },
            headers=headers_a,
        )
        r1_id = r1_resp.json()["data"]["id"]

        r2_resp = await ac.post(
            "/api/v1/detections",
            json={
                "serialNo": "P225BATCH002",
                "faultCategory": "Sensor Abnormal",
                "fileIds": [file_id],
            },
            headers=headers_a,
        )
        r2_id = r2_resp.json()["data"]["id"]

        # Log in User B
        login_b = await ac.post(
            "/api/v1/auth/login",
            json={"email": "dealertest@sibionics.com", "password": "password123"},
        )
        token_b = login_b.json()["data"]["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User B tries to batch delete User A's records -> expect empty deletedIds returned (no matches belong to User B)
        batch_del_fail = await ac.post(
            "/api/v1/records/batch-delete",
            json={"recordIds": [int(r1_id), int(r2_id)]},
            headers=headers_b,
        )
        assert batch_del_fail.status_code == 200
        assert batch_del_fail.json()["data"]["deletedIds"] == []

        # User A batch deletes their own records -> expect both deleted
        batch_del_success = await ac.post(
            "/api/v1/records/batch-delete",
            json={"recordIds": [int(r1_id), int(r2_id)]},
            headers=headers_a,
        )
        assert batch_del_success.status_code == 200
        deleted_ids = batch_del_success.json()["data"]["deletedIds"]
        assert str(r1_id) in deleted_ids
        assert str(r2_id) in deleted_ids

        # Verify records are now hidden
        detail_after_1 = await ac.get(f"/api/v1/records/{r1_id}", headers=headers_a)
        assert detail_after_1.status_code == 404
        detail_after_2 = await ac.get(f"/api/v1/records/{r2_id}", headers=headers_a)
        assert detail_after_2.status_code == 404

        # Verify single batch-delete audit log was written
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AuditLog)
                .where(AuditLog.action == "detection.batch_delete")
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
            audit_log = result.scalar_one_or_none()
            assert audit_log is not None
            assert audit_log.user_id == user_a.id
            assert audit_log.event_metadata["count"] == 2
            assert int(r1_id) in audit_log.event_metadata["deleted_ids"]
            assert int(r2_id) in audit_log.event_metadata["deleted_ids"]
