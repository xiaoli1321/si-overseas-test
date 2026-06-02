from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tables import AuditLog
from src.repositories.scopes import apply_user_scope


async def create_audit_log(
    db: AsyncSession,
    *,
    user_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    status: str = "success",
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    event = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        status=status,
        event_metadata=metadata,
    )
    db.add(event)
    await db.flush()
    return event


async def list_audit_logs(db: AsyncSession, user_id: int) -> Sequence[AuditLog]:
    query = apply_user_scope(select(AuditLog), AuditLog, user_id).order_by(
        AuditLog.created_at.desc()
    )
    result = await db.execute(query)
    return result.scalars().all()
