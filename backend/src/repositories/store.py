from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import get_settings
from src.models.tables import BatchTask, DetectRecord, Distributor, Threshold, User
from src.repositories.scopes import apply_user_scope


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.distributor))
        .where(User.username == email.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User).options(selectinload(User.distributor)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_distributor_by_id(
    db: AsyncSession, distributor_id: int
) -> Distributor | None:
    result = await db.execute(
        select(Distributor).where(Distributor.id == distributor_id)
    )
    return result.scalar_one_or_none()


async def get_active_threshold(db: AsyncSession, user_id: int) -> Threshold | None:
    result = await db.execute(
        select(Threshold)
        .where(Threshold.user_id == user_id, Threshold.is_active.is_(True))
        .order_by(Threshold.version.desc())
    )
    return result.scalars().first()


async def get_next_threshold_version(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.max(Threshold.version)).where(Threshold.user_id == user_id)
    )
    current = result.scalar_one_or_none() or 0
    return int(current) + 1


async def get_threshold_history(db: AsyncSession, user_id: int) -> Sequence[Threshold]:
    result = await db.execute(
        select(Threshold)
        .where(Threshold.user_id == user_id, Threshold.is_deleted.is_(False))
        .order_by(Threshold.version.desc())
    )
    return result.scalars().all()


async def get_threshold_by_version(
    db: AsyncSession, user_id: int, version: int
) -> Threshold | None:
    result = await db.execute(
        select(Threshold).where(
            Threshold.user_id == user_id, Threshold.version == version
        )
    )
    return result.scalar_one_or_none()


def _build_records_query(
    user_id: int,
    *,
    select_target: Select | None = None,
    source: str | None = None,
    fault_category: str | None = None,
    verdict: str | None = None,
    serial_no: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    conclusion: str | None = None,
) -> Select:
    """Build a base query for detect records with all supported filters."""
    if select_target is None:
        select_target = select(DetectRecord)
    query = apply_user_scope(select_target, DetectRecord, user_id).where(
        DetectRecord.is_visible_in_workbench.is_(True),
    )
    if source:
        query = query.where(DetectRecord.source == source)
    if fault_category:
        query = query.where(DetectRecord.fault_category == fault_category)
    if verdict:
        query = query.where(DetectRecord.verdict == verdict)
    if serial_no:
        query = query.where(DetectRecord.serial_no.ilike(f"%{serial_no}%"))
    if date_from:
        query = query.where(DetectRecord.created_at >= date_from)
    if date_to:
        query = query.where(DetectRecord.created_at <= date_to)
    if conclusion:
        if conclusion == "Issue Detected":
            query = query.where(DetectRecord.issue_detected == "Issue Detected")
        else:
            query = query.where(
                or_(
                    DetectRecord.issue_detected != "Issue Detected",
                    DetectRecord.issue_detected.is_(None),
                )
            )
    return query


async def list_records(
    db: AsyncSession,
    user_id: int,
    *,
    source: str | None = None,
    fault_category: str | None = None,
    verdict: str | None = None,
    serial_no: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    conclusion: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[DetectRecord], int]:
    """List records with pagination.

    Uses COUNT(*) OVER() to return total matching row count and the page data
    in a single database round-trip, avoiding a separate count query.
    """
    query = _build_records_query(
        user_id,
        select_target=select(DetectRecord, func.count().over().label("total")),
        source=source,
        fault_category=fault_category,
        verdict=verdict,
        serial_no=serial_no,
        date_from=date_from,
        date_to=date_to,
        conclusion=conclusion,
    )
    result = await db.execute(
        query.order_by(DetectRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    if not rows:
        return [], 0
    total = int(rows[0].total)
    records = [row[0] for row in rows]
    return records, total


async def iter_records_for_export(
    db: AsyncSession,
    user_id: int,
    *,
    source: str | None = None,
    fault_category: str | None = None,
    verdict: str | None = None,
    serial_no: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    conclusion: str | None = None,
    batch_size: int = 1000,
) -> AsyncIterator[list[DetectRecord]]:
    """Yield filtered records in stable batches for memory-bounded exports."""
    last_created_at: datetime | None = None
    last_id: int | None = None

    while True:
        query = _build_records_query(
            user_id,
            select_target=select(DetectRecord),
            source=source,
            fault_category=fault_category,
            verdict=verdict,
            serial_no=serial_no,
            date_from=date_from,
            date_to=date_to,
            conclusion=conclusion,
        )
        if last_created_at is not None and last_id is not None:
            query = query.where(
                or_(
                    DetectRecord.created_at < last_created_at,
                    and_(
                        DetectRecord.created_at == last_created_at,
                        DetectRecord.id < last_id,
                    ),
                )
            )

        result = await db.execute(
            query.order_by(
                DetectRecord.created_at.desc(), DetectRecord.id.desc()
            ).limit(batch_size)
        )
        records = list(result.scalars().all())
        if not records:
            break

        yield records

        last = records[-1]
        last_created_at = last.created_at
        last_id = last.id
        if len(records) < batch_size:
            break


async def get_record(
    db: AsyncSession, user_id: int, record_id: int, *, source: str | None = None
) -> DetectRecord | None:
    query = apply_user_scope(select(DetectRecord), DetectRecord, user_id).where(
        DetectRecord.id == record_id, DetectRecord.is_visible_in_workbench.is_(True)
    )
    if source:
        query = query.where(DetectRecord.source == source)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_batch_task(
    db: AsyncSession, user_id: int, task_id: int
) -> BatchTask | None:
    query = apply_user_scope(select(BatchTask), BatchTask, user_id)
    result = await db.execute(
        query.options(selectinload(BatchTask.records)).where(BatchTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def get_batch_records(
    db: AsyncSession, batch_task_id: int
) -> Sequence[DetectRecord]:
    result = await db.execute(
        select(DetectRecord).where(DetectRecord.batch_task_id == batch_task_id)
    )
    return result.scalars().all()


async def stats(
    db: AsyncSession, user_id: int, *, source: str | None = None
) -> dict[str, int]:
    stmt = select(
        func.count(DetectRecord.id).label("total"),
        func.sum(
            case((DetectRecord.verdict == "Replacement Eligible", 1), else_=0)
        ).label("allowed"),
        func.sum(case((DetectRecord.verdict == "Not Eligible", 1), else_=0)).label(
            "not_allowed"
        ),
        func.sum(
            case(
                (
                    or_(
                        DetectRecord.verdict == "Under Review",
                        DetectRecord.status.in_(["pending", "processing"]),
                    ),
                    1,
                ),
                else_=0,
            )
        ).label("pending"),
    ).where(
        DetectRecord.user_id == user_id,
        DetectRecord.is_visible_in_workbench.is_(True),
    )
    if source:
        stmt = stmt.where(DetectRecord.source == source)
    result = await db.execute(stmt)
    row = result.fetchone()
    if not row:
        return {"total": 0, "allowed": 0, "not_allowed": 0, "pending": 0}
    return {
        "total": int(row.total or 0),
        "allowed": int(row.allowed or 0),
        "not_allowed": int(row.not_allowed or 0),
        "pending": int(row.pending or 0),
    }


async def mark_stale_processing_failed(db: AsyncSession) -> None:
    cutoff = datetime.now(UTC) - timedelta(minutes=get_settings().task_stale_minutes)
    await db.execute(
        update(DetectRecord)
        .where(
            DetectRecord.status.in_(["pending", "processing"]),
            DetectRecord.updated_at < cutoff,
        )
        .values(
            status="failed",
            error_message="Task timed out and can be retried.",
            updated_at=datetime.now(UTC),
        )
    )
