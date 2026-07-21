from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import get_settings
from src.models.tables import BatchTask, DetectRecord, Distributor, Threshold, User
from src.repositories.scopes import apply_scope_for_user


def _is_manager(actor: User | None) -> bool:
    return bool(actor is not None and getattr(actor, "role", None) == "manager")


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


async def get_users_by_ids(
    db: AsyncSession, user_ids: Sequence[int]
) -> dict[int, User]:
    """Resolve a set of user ids to their User rows in one query.

    Used to attribute detection records to the account that submitted them
    without N+1 lookups when a manager views cross-account history.
    """
    ids = {uid for uid in user_ids if uid is not None}
    if not ids:
        return {}
    result = await db.execute(
        select(User).options(selectinload(User.distributor)).where(User.id.in_(ids))
    )
    return {user.id: user for user in result.scalars().all()}


async def list_managed_users(
    db: AsyncSession, manager_id: int
) -> Sequence[User]:
    """List accounts provisioned by a given manager (newest first)."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.distributor))
        .where(User.created_by == manager_id)
        .order_by(User.created_at.desc())
    )
    return result.scalars().all()


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
    actor: User,
    *,
    select_target: Select | None = None,
    source: str | None = None,
    fault_category: str | None = None,
    verdict: str | None = None,
    serial_no: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    conclusion: str | None = None,
    account_id: int | None = None,
) -> Select:
    """Build a base query for detect records with all supported filters.

    Scope follows the acting account: managers see every account's records
    (and may narrow to one via ``account_id``), while dealers stay restricted
    to their own rows.
    """
    if select_target is None:
        select_target = select(DetectRecord)
    query = apply_scope_for_user(select_target, DetectRecord, actor).where(
        DetectRecord.is_visible_in_workbench.is_(True),
    )
    if account_id is not None:
        query = query.where(DetectRecord.user_id == account_id)
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
    actor: User,
    *,
    source: str | None = None,
    fault_category: str | None = None,
    verdict: str | None = None,
    serial_no: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    conclusion: str | None = None,
    account_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[DetectRecord], int]:
    """List records with pagination.

    Uses COUNT(*) OVER() to return total matching row count and the page data
    in a single database round-trip, avoiding a separate count query.
    """
    query = _build_records_query(
        actor,
        select_target=select(DetectRecord, func.count().over().label("total")),
        source=source,
        fault_category=fault_category,
        verdict=verdict,
        serial_no=serial_no,
        date_from=date_from,
        date_to=date_to,
        conclusion=conclusion,
        account_id=account_id,
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
    actor: User,
    *,
    source: str | None = None,
    fault_category: str | None = None,
    verdict: str | None = None,
    serial_no: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    conclusion: str | None = None,
    account_id: int | None = None,
    batch_size: int = 1000,
) -> AsyncIterator[list[DetectRecord]]:
    """Yield filtered records in stable batches for memory-bounded exports."""
    last_created_at: datetime | None = None
    last_id: int | None = None

    while True:
        query = _build_records_query(
            actor,
            select_target=select(DetectRecord),
            source=source,
            fault_category=fault_category,
            verdict=verdict,
            serial_no=serial_no,
            date_from=date_from,
            date_to=date_to,
            conclusion=conclusion,
            account_id=account_id,
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
    db: AsyncSession,
    user_id: int,
    record_id: int,
    *,
    source: str | None = None,
    viewer: User | None = None,
) -> DetectRecord | None:
    # Managers (passed via ``viewer``) may open any account's record; every
    # other caller stays strictly scoped to ``user_id``.
    query = select(DetectRecord).where(
        DetectRecord.id == record_id, DetectRecord.is_visible_in_workbench.is_(True)
    )
    if not _is_manager(viewer):
        query = query.where(DetectRecord.user_id == user_id)
    if source:
        query = query.where(DetectRecord.source == source)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_batch_task(
    db: AsyncSession, user_id: int, task_id: int, *, viewer: User | None = None
) -> BatchTask | None:
    query = select(BatchTask)
    if not _is_manager(viewer):
        query = query.where(BatchTask.user_id == user_id)
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
    db: AsyncSession, actor: User, *, source: str | None = None
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
        DetectRecord.is_visible_in_workbench.is_(True),
    )
    stmt = apply_scope_for_user(stmt, DetectRecord, actor)
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
