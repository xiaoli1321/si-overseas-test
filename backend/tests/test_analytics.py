import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from pydantic import ValidationError

from src.core.database import AsyncSessionLocal
from src.main import app
from src.models.tables import AuditLog
from src.repositories.store import get_user_by_email
from src.schemas.analytics import (
    LoginEventProperties,
    DeviceQueryEventProperties,
    DiagnosisCompletedEventProperties,
    VerdictAdoptionEventProperties,
)


async def _analytics_count(*, event_name: str, user_id: int | None = None) -> int:
    async with AsyncSessionLocal() as db:
        query = select(func.count()).select_from(AuditLog).where(AuditLog.action == event_name)
        if user_id is not None:
            query = query.where(AuditLog.user_id == user_id)
        result = await db.execute(query)
        return int(result.scalar_one())


async def _latest_analytics(event_name: str) -> AuditLog | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.action == event_name)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _user_by_email(email: str):
    async with AsyncSessionLocal() as db:
        user = await get_user_by_email(db, email)
        assert user is not None
        return user


# --- Unit Tests: Pydantic Schema Validation ---

def test_pydantic_schema_validation_success():
    # Login schema validation
    props = LoginEventProperties(
        user_id=1,
        username="test@test.com",
        role="dealer",
        distributor_id=10,
        distributor_name="Distributor Name",
        status="success"
    )
    assert props.status == "success"
    assert props.channel == "web"

    openapi_props = LoginEventProperties(
        user_id=1,
        username="partner@test.com",
        role="dealer",
        status="success",
        channel="openapi",
    )
    assert openapi_props.channel == "openapi"

    # Device query validation
    props_query = DeviceQueryEventProperties(
        user_id=1,
        username="test@test.com",
        role="dealer",
        query_type="single",
        serial_no="SN123",
        batch_count=1
    )
    assert props_query.query_type == "single"


def test_pydantic_schema_validation_failures():
    # Invalid Literal value should fail
    with pytest.raises(ValidationError):
        LoginEventProperties(
            user_id=1,
            username="test@test.com",
            role="dealer",
            status="invalid_status"  # Invalid status literal
        )

    # Missing required fields
    with pytest.raises(ValidationError):
        DeviceQueryEventProperties(
            user_id=1,
            username="test@test.com",
            role="dealer"
            # query_type is missing
        )


# --- Integration Tests: API Event Tracking ---

@pytest.mark.asyncio
async def test_api_analytics_events_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "overseas_api_enabled", False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        user = await _user_by_email("christest@sibionics.com")

        # 1. Test Login Analytics (Success and Failure)
        login_failed_before = await _analytics_count(event_name="auth.login", user_id=user.id)
        
        # Trigger failed login
        await ac.post(
            "/api/v1/auth/login",
            json={"email": "christest@sibionics.com", "password": "wrong-password"},
        )
        assert await _analytics_count(event_name="auth.login", user_id=user.id) == login_failed_before + 1
        latest_login = await _latest_analytics("auth.login")
        assert latest_login is not None
        assert latest_login.event_metadata["status"] == "failure"
        assert latest_login.event_metadata["fail_reason"] == "invalid_password"
        assert latest_login.event_metadata["distributor_name"] == user.distributor_name

        # Trigger successful login
        login_response = await ac.post(
            "/api/v1/auth/login",
            json={"email": "christest@sibionics.com", "password": "password123"},
        )
        assert login_response.status_code == 200
        headers = {"Authorization": f"Bearer {login_response.json()['data']['access_token']}"}
        latest_login = await _latest_analytics("auth.login")
        assert latest_login is not None
        assert latest_login.event_metadata["status"] == "success"

        # 2. Test Device Query Analytics
        query_before = await _analytics_count(event_name="device.query", user_id=user.id)

        # Verify GET single device does NOT trigger logging
        device_resp = await ac.get("/api/v1/devices/P2251212806JND44", headers=headers)
        assert device_resp.status_code == 200
        assert await _analytics_count(event_name="device.query", user_id=user.id) == query_before

        # Verify POST search devices does NOT trigger logging
        search_resp = await ac.post(
            "/api/v1/devices/search",
            json={"keywords": ["P225"]},
            headers=headers
        )
        assert search_resp.status_code == 200
        assert await _analytics_count(event_name="device.query", user_id=user.id) == query_before

        # Verify POST batch-query does NOT trigger logging
        batch_resp = await ac.post(
            "/api/v1/devices/batch-query",
            json=["P2251212806JND44"],
            headers=headers
        )
        assert batch_resp.status_code == 200
        assert await _analytics_count(event_name="device.query", user_id=user.id) == query_before

        # Test tracking device.query via analytics events endpoint
        query_event_resp = await ac.post(
            "/api/v1/analytics/events",
            json={
                "eventName": "device.query",
                "source": "fault_query",
                "properties": {
                    "entry_source": "recommendation",
                    "fault_category": "Data accuracy",
                    "query_type": "batch",
                    "query_count": 2,
                    "serial_nos": ["P2251212806JND44", "P2251212806JND45"]
                }
            },
            headers=headers
        )
        assert query_event_resp.status_code == 200
        assert await _analytics_count(event_name="device.query", user_id=user.id) == query_before + 1
        
        latest_query = await _latest_analytics("device.query")
        assert latest_query is not None
        assert latest_query.event_metadata["entry_source"] == "recommendation"
        assert latest_query.event_metadata["fault_category"] == "Data accuracy"
        assert latest_query.event_metadata["query_type"] == "batch"
        assert latest_query.event_metadata["query_count"] == 2
        assert latest_query.event_metadata["serial_nos"] == ["P2251212806JND44", "P2251212806JND45"]

        # 3. Test Diagnosis Completed Analytics
        diagnosis_before = await _analytics_count(event_name="diagnosis.completed", user_id=user.id)

        # Upload a file
        upload_response = await ac.post(
            "/api/v1/files/upload",
            files={"file": ("test.png", io.BytesIO(b"bytes"), "image/png")},
            headers=headers,
        )
        assert upload_response.status_code == 200
        file_id = upload_response.json()["data"]["id"]

        # Run diagnosis
        detect_resp = await ac.post(
            "/api/v1/detections",
            json={
                "serialNo": "P2251212806JND44",
                "faultCategory": "Application failure",
                "fileIds": [file_id],
            },
            headers=headers,
        )
        assert detect_resp.status_code == 200
        record_id = detect_resp.json()["data"]["id"]

        # Confirm diagnosis.completed event was logged
        assert await _analytics_count(event_name="diagnosis.completed", user_id=user.id) == diagnosis_before + 1
        latest_diag = await _latest_analytics("diagnosis.completed")
        assert latest_diag is not None
        assert latest_diag.event_metadata["record_id"] == int(record_id)
        assert latest_diag.event_metadata["fault_category"] == "Application failure"
        assert latest_diag.event_metadata["judgment_source"] in ("AI (VLM)", "Rule Engine")

        # 4. Test Verdict Adoption (Feedback) Analytics
        feedback_before = await _analytics_count(event_name="verdict.adoption", user_id=user.id)
        
        feedback_resp = await ac.post(
            f"/api/v1/records/{record_id}/feedback",
            json={"verdictAdoption": "Yes"},
            headers=headers,
        )
        assert feedback_resp.status_code == 200
        assert await _analytics_count(event_name="verdict.adoption", user_id=user.id) == feedback_before + 1
        latest_adopt = await _latest_analytics("verdict.adoption")
        assert latest_adopt is not None
        assert latest_adopt.event_metadata["record_id"] == int(record_id)
        assert latest_adopt.event_metadata["feedback_status"] == "adopted"
        assert latest_adopt.event_metadata["reject_reason"] is None
