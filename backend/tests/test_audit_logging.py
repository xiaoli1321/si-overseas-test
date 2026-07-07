import io
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.core.database import AsyncSessionLocal
from src.main import app
from src.models.tables import AuditLog
from src.repositories.store import get_user_by_email
from src.schemas.domain import AgentClassifyResponse


async def _audit_count(*, action: str, user_id: int | None = None, status: str | None = None) -> int:
    async with AsyncSessionLocal() as db:
        query = select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        if user_id is not None:
            query = query.where(AuditLog.user_id == user_id)
        if status is not None:
            query = query.where(AuditLog.status == status)
        result = await db.execute(query)
        return int(result.scalar_one())


async def _latest_audit(action: str, *, target_id: str) -> AuditLog | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.action == action, AuditLog.target_id == target_id)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _user_id_by_email(email: str) -> int:
    async with AsyncSessionLocal() as db:
        user = await get_user_by_email(db, email)
        assert user is not None
        return user.id


@pytest.mark.asyncio
async def test_key_operations_should_write_durable_audit_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_classify_fault(_: str) -> AgentClassifyResponse:
        return AgentClassifyResponse(
            fault_category="Application failure",
            confidence=0.91,
            manual_review=False,
            message="Application failure classification.",
            source="unit-test",
            fallback_used=False,
        )

    monkeypatch.setattr("src.services.chat_turns.classify_fault", fake_classify_fault)
    from src.core.config import get_settings
    monkeypatch.setattr(get_settings(), "overseas_api_enabled", False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        failed_before = await _audit_count(action="auth.login", status="failure")
        failed_login = await ac.post(
            "/api/v1/auth/login",
            json={"email": "christest@sibionics.com", "password": "wrong-password"},
        )
        assert failed_login.status_code == 401
        assert await _audit_count(action="auth.login", status="failure") == failed_before + 1

        login_response = await ac.post(
            "/api/v1/auth/login",
            json={"email": "christest@sibionics.com", "password": "password123"},
        )
        assert login_response.status_code == 200, login_response.text
        user_id = await _user_id_by_email("christest@sibionics.com")
        headers = {"Authorization": f"Bearer {login_response.json()['data']['access_token']}"}

        upload_before = await _audit_count(action="file.upload", user_id=user_id)
        upload_response = await ac.post(
            "/api/v1/files/upload",
            files={"file": ("audit-image.png", io.BytesIO(b"image-bytes"), "image/png")},
            headers=headers,
        )
        assert upload_response.status_code == 200, upload_response.text
        uploaded_id = upload_response.json()["data"]["id"]
        assert await _audit_count(action="file.upload", user_id=user_id) == upload_before + 1

        # Create a successful detection to obtain a valid record ID
        detect_response = await ac.post(
            "/api/v1/detections",
            json={
                "serialNo": "P2251212806JND44",
                "faultCategory": "Application failure",
                "fileIds": [uploaded_id],
            },
            headers=headers,
        )
        assert detect_response.status_code == 200, detect_response.text
        record_id = detect_response.json()["data"]["id"]

        detection_failure_before = await _audit_count(action="detection.create", user_id=user_id, status="failure")
        failed_detection = await ac.post(
            "/api/v1/detections",
            json={
                "serialNo": "P2251212806JND44",
                "faultCategory": "Application failure",
                "fileIds": ["file-not-owned-by-this-user"],
            },
            headers=headers,
        )
        assert failed_detection.status_code == 422
        assert (
            await _audit_count(action="detection.create", user_id=user_id, status="failure")
            == detection_failure_before + 1
        )

        session_id = f"CHAT-audit-{uuid4().hex}"
        create_session = await ac.post(
            "/api/v1/agent/chats",
            json={"id": session_id, "title": "New device judgment"},
            headers=headers,
        )
        assert create_session.status_code == 200, create_session.text

        turn_response = await ac.post(
            f"/api/v1/agent/chats/{session_id}/turns",
            json={
                "id": f"MSG-user-{uuid4().hex}",
                "assistantId": f"MSG-assistant-{uuid4().hex}",
                "content": "P2251212806JND44 applicator needle issue",
            },
            headers=headers,
        )
        assert turn_response.status_code == 200, turn_response.text
        turn_audit = await _latest_audit("chat.turn", target_id=session_id)
        assert turn_audit is not None
        assert turn_audit.user_id == user_id
        assert turn_audit.event_metadata["user_message_id"] is not None
        assert turn_audit.event_metadata["assistant_message_id"] is not None

        upload_audit = await _latest_audit("file.upload", target_id=uploaded_id)
        assert upload_audit is not None
        assert upload_audit.user_id == user_id
        assert upload_audit.event_metadata["filename"] == "audit-image.png"

        # Submit adopted feedback
        feedback_response = await ac.post(
            f"/api/v1/records/{record_id}/feedback",
            json={"feedbackStatus": "adopted"},
            headers=headers,
        )
        assert feedback_response.status_code == 200, feedback_response.text
        data = feedback_response.json()["data"]
        assert data["verdictAdoption"] == "Yes"
        assert data["adoptedAt"] is not None

        # Verify database record
        async with AsyncSessionLocal() as db:
            from src.models.tables import DetectRecord
            result = await db.execute(select(DetectRecord).where(DetectRecord.id == int(record_id)))
            record = result.scalar_one()
            assert record.feedback_status == "adopted"
            assert record.adopted_at is not None

        # Verify audit log
        audit = await _latest_audit("detection.feedback", target_id=str(record_id))
        assert audit is not None
        assert audit.user_id == user_id
        assert audit.event_metadata["feedback_status"] == "adopted"
        assert audit.event_metadata["adopted_at"] is not None


