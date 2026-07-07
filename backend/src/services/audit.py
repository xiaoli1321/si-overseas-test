from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tables import AuditLog
from src.repositories.audit_logs import create_audit_log


async def record_audit_event(
    db: AsyncSession,
    *,
    user_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    status: str = "success",
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    return await create_audit_log(
        db,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        status=status,
        metadata=metadata,
    )
