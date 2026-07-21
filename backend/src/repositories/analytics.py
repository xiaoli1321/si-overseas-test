from typing import Any

from sqlalchemy import Integer, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tables import AuditLog, DetectRecord, User
from src.repositories.audit_logs import create_audit_log
from src.repositories.scopes import AccountActor, apply_scope_for_user, apply_user_scope


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


async def query_usage_summary(
    db: AsyncSession, actor: AccountActor
) -> dict[str, Any]:
    """Aggregate device-query telemetry by query type.

    Answers "how often is (batch) query used" from the ``device.query`` events
    that land in ``audit_logs``. ``queries`` counts events; ``devices`` sums the
    ``batch_count`` metadata (number of SNs per query). Scoped via
    ``apply_scope_for_user`` so a manager sees org-wide usage while any other
    role would only see their own.
    """
    query_type = AuditLog.event_metadata["query_type"].astext
    batch_count = cast(AuditLog.event_metadata["batch_count"].astext, Integer)

    base = select(
        query_type.label("query_type"),
        func.count().label("queries"),
        func.coalesce(func.sum(batch_count), 0).label("devices"),
    ).where(AuditLog.action == "device.query")
    scoped = apply_scope_for_user(base, AuditLog, actor).group_by(query_type)

    rows = (await db.execute(scoped)).all()

    by_type: dict[str, dict[str, int]] = {}
    total_queries = 0
    for qtype, queries, devices in rows:
        key = qtype or "unknown"
        by_type[key] = {"queries": int(queries), "devices": int(devices or 0)}
        total_queries += int(queries)

    batch = by_type.get("batch", {"queries": 0, "devices": 0})
    return {
        "total_queries": total_queries,
        "batch_queries": batch["queries"],
        "batch_devices": batch["devices"],
        "by_type": by_type,
    }


async def dashboard_summary(db: AsyncSession, actor: AccountActor) -> dict[str, Any]:
    """Manager-wide operations dashboard aggregated from telemetry + records.

    Mirrors the metrics in ``scripts/generate_report_data.py`` (activity,
    query/batch usage, verdict outcome, adoption, per-account breakdown) but
    exposes them as a live, queryable payload. Scoped via
    ``apply_scope_for_user`` so a manager sees org-wide numbers.
    """
    qtype = AuditLog.event_metadata["query_type"].astext
    bcount = cast(AuditLog.event_metadata["batch_count"].astext, Integer)
    batch_dev_expr = func.coalesce(
        func.sum(case((qtype == "batch", bcount), else_=0)), 0
    )

    async def _audit_count(*conds: Any) -> int:
        query = apply_scope_for_user(
            select(func.count()).select_from(AuditLog), AuditLog, actor
        )
        for cond in conds:
            query = query.where(cond)
        return int(await db.scalar(query) or 0)

    logins = await _audit_count(
        AuditLog.action == "auth.login", AuditLog.status == "success"
    )
    diagnoses = await _audit_count(AuditLog.action == "diagnosis.completed")

    # Device-query usage grouped by type (single/batch/search).
    dq_stmt = (
        apply_scope_for_user(
            select(
                qtype.label("qt"),
                func.count().label("c"),
                func.coalesce(func.sum(bcount), 0).label("dev"),
            ),
            AuditLog,
            actor,
        )
        .where(AuditLog.action == "device.query")
        .group_by(qtype)
    )
    query_by_type = {"single": 0, "batch": 0, "search": 0}
    device_queries = 0
    batch_devices = 0
    for qt, count, dev in (await db.execute(dq_stmt)).all():
        device_queries += int(count)
        if qt in query_by_type:
            query_by_type[qt] = int(count)
        if qt == "batch":
            batch_devices = int(dev or 0)

    # Verdict + adoption rollup over visible records.
    rec_stmt = apply_scope_for_user(
        select(
            func.count(DetectRecord.id).label("total"),
            func.coalesce(
                func.sum(
                    case((DetectRecord.verdict == "Replacement Eligible", 1), else_=0)
                ),
                0,
            ).label("eligible"),
            func.coalesce(
                func.sum(case((DetectRecord.verdict == "Not Eligible", 1), else_=0)),
                0,
            ).label("not_eligible"),
            func.coalesce(
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
                ),
                0,
            ).label("under_review"),
            func.coalesce(
                func.sum(case((DetectRecord.adoption_status == "adopted", 1), else_=0)),
                0,
            ).label("adopted"),
            func.coalesce(
                func.sum(case((DetectRecord.adoption_status == "rejected", 1), else_=0)),
                0,
            ).label("rejected"),
        ).select_from(DetectRecord),
        DetectRecord,
        actor,
    ).where(DetectRecord.is_visible_in_workbench.is_(True))
    rec = (await db.execute(rec_stmt)).one()

    # Records by fault category.
    fc_stmt = (
        apply_scope_for_user(
            select(DetectRecord.fault_category, func.count().label("c")).select_from(
                DetectRecord
            ),
            DetectRecord,
            actor,
        )
        .where(DetectRecord.is_visible_in_workbench.is_(True))
        .group_by(DetectRecord.fault_category)
        .order_by(func.count().desc())
    )
    by_fault_category = [
        {"category": category, "count": int(count)}
        for category, count in (await db.execute(fc_stmt)).all()
    ]

    # ---- Per-account activity (join telemetry + records by user) ----
    accounts: dict[int, dict[str, Any]] = {}

    def _acct(user_id: int) -> dict[str, Any]:
        return accounts.setdefault(
            user_id,
            {
                "logins": 0,
                "queries": 0,
                "batchDevices": 0,
                "diagnoses": 0,
                "adopted": 0,
                "rejected": 0,
            },
        )

    login_rows = (
        await db.execute(
            apply_scope_for_user(
                select(AuditLog.user_id, func.count()), AuditLog, actor
            )
            .where(AuditLog.action == "auth.login", AuditLog.status == "success")
            .group_by(AuditLog.user_id)
        )
    ).all()
    for user_id, count in login_rows:
        _acct(user_id)["logins"] = int(count)

    query_rows = (
        await db.execute(
            apply_scope_for_user(
                select(AuditLog.user_id, func.count(), batch_dev_expr),
                AuditLog,
                actor,
            )
            .where(AuditLog.action == "device.query")
            .group_by(AuditLog.user_id)
        )
    ).all()
    for user_id, count, dev in query_rows:
        entry = _acct(user_id)
        entry["queries"] = int(count)
        entry["batchDevices"] = int(dev or 0)

    rec_rows = (
        await db.execute(
            apply_scope_for_user(
                select(
                    DetectRecord.user_id,
                    func.count(DetectRecord.id),
                    func.coalesce(
                        func.sum(
                            case((DetectRecord.adoption_status == "adopted", 1), else_=0)
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (DetectRecord.adoption_status == "rejected", 1), else_=0
                            )
                        ),
                        0,
                    ),
                ).select_from(DetectRecord),
                DetectRecord,
                actor,
            )
            .where(DetectRecord.is_visible_in_workbench.is_(True))
            .group_by(DetectRecord.user_id)
        )
    ).all()
    for user_id, total, adopted, rejected in rec_rows:
        entry = _acct(user_id)
        entry["diagnoses"] = int(total)
        entry["adopted"] = int(adopted or 0)
        entry["rejected"] = int(rejected or 0)

    user_map: dict[int, tuple[str, str | None]] = {}
    if accounts:
        user_rows = (
            await db.execute(
                select(
                    User.id, User.username, User.distributor_name
                ).where(User.id.in_(list(accounts.keys())))
            )
        ).all()
        user_map = {uid: (email, dealer) for uid, email, dealer in user_rows}

    by_account = []
    for user_id, entry in accounts.items():
        email, dealer = user_map.get(user_id, (f"user#{user_id}", None))
        by_account.append(
            {
                "accountId": str(user_id),
                "email": email,
                "dealerName": dealer or "—",
                **entry,
            }
        )
    by_account.sort(
        key=lambda item: item["queries"] + item["diagnoses"] + item["logins"],
        reverse=True,
    )
    by_account = by_account[:20]

    return {
        "totals": {
            "logins": logins,
            "deviceQueries": device_queries,
            "batchQueries": query_by_type["batch"],
            "batchDevices": batch_devices,
            "diagnoses": diagnoses,
            "records": int(rec.total or 0),
        },
        "verdicts": {
            "eligible": int(rec.eligible or 0),
            "notEligible": int(rec.not_eligible or 0),
            "underReview": int(rec.under_review or 0),
        },
        "adoption": {
            "adopted": int(rec.adopted or 0),
            "rejected": int(rec.rejected or 0),
        },
        "queryUsage": query_by_type,
        "byFaultCategory": by_fault_category,
        "byAccount": by_account,
    }
