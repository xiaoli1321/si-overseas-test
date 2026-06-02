from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tables import AuditLog
from src.repositories.audit_logs import create_audit_log
from src.repositories.scopes import apply_user_scope


async def create_analytics_event(
    db: AsyncSession,
    *,
    user_id: int,
    event_name: str,
    source: str | None,
    properties: dict[str, Any] | None,
) -> AuditLog:
    # Redirect writing custom analytics events to create_audit_log
    return await create_audit_log(
        db,
        user_id=user_id,
        action=event_name,
        target_type="custom",
        target_id=None,
        status="success",
        metadata=properties,
    )


async def analytics_summary(db: AsyncSession, user_id: int) -> dict[str, Any]:
    telemetry_actions = [
        "auth.login",
        "device.query",
        "diagnosis.completed",
        "verdict.adoption",
    ]
    query = select(AuditLog).where(AuditLog.action.in_(telemetry_actions))
    scoped = apply_user_scope(query, AuditLog, user_id).subquery()

    by_event_result = await db.execute(
        select(scoped.c.action, func.count()).group_by(scoped.c.action)
    )
    by_event = {name: int(count) for name, count in by_event_result.all()}
    total_count = sum(by_event.values())

    return {
        "total": total_count,
        "by_event": by_event,
        "by_source": {"backend": total_count},
    }
