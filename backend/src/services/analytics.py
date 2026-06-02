from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tables import DetectRecord, User
from src.repositories.audit_logs import create_audit_log
from src.schemas.analytics import (
    DeviceQueryEventProperties,
    DiagnosisCompletedEventProperties,
    LoginEventProperties,
    VerdictAdoptionEventProperties,
)


def _get_user_context(user: User) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "distributor_id": user.distributor_id,
        "distributor_name": user.distributor_name,
    }


async def track_login(
    db: AsyncSession,
    *,
    user: User,
    status: Literal["success", "failure"],
    fail_reason: Literal["invalid_password", "user_not_found"] | None = None,
) -> None:
    context = _get_user_context(user)
    properties = LoginEventProperties(
        **context,
        status=status,
        fail_reason=fail_reason,
    )
    await create_audit_log(
        db,
        user_id=user.id,
        action="auth.login",
        target_type="user",
        target_id=user.id,
        status=status,
        metadata=properties.model_dump(),
    )


async def track_device_query(
    db: AsyncSession,
    *,
    user: User,
    query_type: Literal["single", "batch", "search"],
    serial_no: str | None = None,
    batch_count: int = 1,
) -> None:
    context = _get_user_context(user)
    properties = DeviceQueryEventProperties(
        **context,
        query_type=query_type,
        serial_no=serial_no,
        batch_count=batch_count,
    )
    await create_audit_log(
        db,
        user_id=user.id,
        action="device.query",
        target_type="device",
        target_id=serial_no,
        status="success",
        metadata=properties.model_dump(),
    )


async def track_diagnosis_completed(
    db: AsyncSession,
    *,
    user: User,
    record: DetectRecord,
    judgment_source: Literal["AI (VLM)", "Rule Engine"],
    has_images: bool,
) -> None:
    context = _get_user_context(user)
    properties = DiagnosisCompletedEventProperties(
        **context,
        record_id=record.id,
        serial_no=record.serial_no,
        fault_category=record.fault_category,
        fault_subtype=record.fault_subtype,
        verdict=record.verdict or "Under Review",
        judgment_source=judgment_source,
        has_images=has_images,
    )
    await create_audit_log(
        db,
        user_id=user.id,
        action="diagnosis.completed",
        target_type="detect_record",
        target_id=record.id,
        status="success",
        metadata=properties.model_dump(),
    )


async def track_verdict_adoption(
    db: AsyncSession,
    *,
    user: User,
    record: DetectRecord,
    feedback_status: Literal["adopted", "rejected"],
    reject_reason: str | None = None,
) -> None:
    context = _get_user_context(user)
    properties = VerdictAdoptionEventProperties(
        **context,
        record_id=record.id,
        serial_no=record.serial_no,
        fault_category=record.fault_category,
        fault_subtype=record.fault_subtype,
        verdict=record.verdict or "Under Review",
        feedback_status=feedback_status,
        reject_reason=reject_reason,
    )
    await create_audit_log(
        db,
        user_id=user.id,
        action="verdict.adoption",
        target_type="detect_record",
        target_id=record.id,
        status="success",
        metadata=properties.model_dump(),
    )
