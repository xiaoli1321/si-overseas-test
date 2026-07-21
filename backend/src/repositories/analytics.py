from typing import Any

from sqlalchemy import Integer, case, cast, func, select
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


# --- Dashboard (structure per the 数据大盘 Excel; labels use the code's own
# canonical English terms: FaultCategory / Verdict / conclusion / adoption). ---
_FAULT_CATEGORIES = [
    "Data accuracy",
    "Sensor falling off",
    "Sensor Abnormal",
    "Application failure",
]


def _conclusion_label(issue_detected: str | None, status: str | None) -> str:
    """Detection conclusion: Issue Detected / No Issue / Under Review."""
    if status in ("pending", "processing"):
        return "Under Review"
    if issue_detected == "Issue Detected":
        return "Issue Detected"
    return "No Issue"


def _aftersales_label(verdict: str | None) -> str:
    """After-sales verdict: Replacement Eligible / Not Eligible / Under Review."""
    if verdict == "Replacement Eligible":
        return "Replacement Eligible"
    if verdict == "Not Eligible":
        return "Not Eligible"
    return "Under Review"


def _adopted_label(adoption_status: str | None) -> str:
    """Verdict adoption: Yes / No / Not recorded."""
    return {"adopted": "Yes", "rejected": "No"}.get(adoption_status or "", "Not recorded")


def _rule_version(record: DetectRecord) -> str:
    snapshot = record.threshold_snapshot or {}
    version = snapshot.get("version") or record.threshold_id
    return f"Rule profile v{version}" if version else ""


def _ratio(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


async def dashboard_overview(
    db: AsyncSession,
    actor: AccountActor,
    *,
    date_from: Any = None,
    date_to: Any = None,
    country: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    """概览 (sheet1 大盘数据概览): core metrics + scenario table + conclusion/
    after-sales distribution + daily trend, filtered by date/country/account.

    Scope: counts only system detections (source='web'); country is derived from
    the account's distributor_name. Manager-scoped via ``apply_scope_for_user``.
    """

    def rbase(*cols: Any):
        q = (
            select(*cols)
            .select_from(DetectRecord)
            .join(User, DetectRecord.user_id == User.id)
        )
        q = apply_scope_for_user(q, DetectRecord, actor).where(
            DetectRecord.is_visible_in_workbench.is_(True),
            DetectRecord.source == "web",
        )
        if account_id is not None:
            q = q.where(DetectRecord.user_id == account_id)
        if date_from is not None:
            q = q.where(DetectRecord.created_at >= date_from)
        if date_to is not None:
            q = q.where(DetectRecord.created_at <= date_to)
        if country:
            q = q.where(User.distributor_name == country)
        return q

    def dqbase(*cols: Any):
        q = (
            select(*cols)
            .select_from(AuditLog)
            .join(User, AuditLog.user_id == User.id)
        )
        q = apply_scope_for_user(q, AuditLog, actor).where(
            AuditLog.action == "device.query"
        )
        if account_id is not None:
            q = q.where(AuditLog.user_id == account_id)
        if date_from is not None:
            q = q.where(AuditLog.created_at >= date_from)
        if date_to is not None:
            q = q.where(AuditLog.created_at <= date_to)
        if country:
            q = q.where(User.distributor_name == country)
        return q

    # reusable record aggregate expressions
    def _sum(cond: Any):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

    c_total = func.count(DetectRecord.id)
    c_elig = _sum(DetectRecord.verdict == "Replacement Eligible")
    c_not = _sum(DetectRecord.verdict == "Not Eligible")
    c_adopt = _sum(DetectRecord.adoption_status == "adopted")
    c_reject = _sum(DetectRecord.adoption_status == "rejected")
    c_found = _sum(DetectRecord.issue_detected == "Issue Detected")
    c_review = _sum(DetectRecord.status.in_(["pending", "processing"]))

    # ---- core metrics ----
    row = (
        await db.execute(rbase(c_total, c_elig, c_not, c_adopt, c_reject, c_found, c_review))
    ).one()
    total = int(row[0] or 0)
    elig = int(row[1] or 0)
    not_elig = int(row[2] or 0)
    adopted = int(row[3] or 0)
    rejected = int(row[4] or 0)
    found = int(row[5] or 0)
    review = int(row[6] or 0)
    detecting = max(total - elig - not_elig, 0)
    problem_entries = int(await db.scalar(dqbase(func.count())) or 0)

    core = {
        "problemEntries": problem_entries,
        "deviceDetections": total,
        "eligible": elig,
        "notEligible": not_elig,
        "detecting": detecting,
        "adopted": adopted,
        "rejected": rejected,
        "adoptionRate": _ratio(adopted, adopted + rejected),
    }

    # ---- 问题场景表现 (by fault category) ----
    scen_rows = (
        await db.execute(
            rbase(
                DetectRecord.fault_category,
                c_total,
                c_elig,
                c_not,
                c_adopt,
                c_reject,
            ).group_by(DetectRecord.fault_category)
        )
    ).all()
    scen_map = {r[0]: r for r in scen_rows}

    fault_meta = AuditLog.event_metadata["fault_category"].astext
    pe_rows = (
        await db.execute(dqbase(fault_meta, func.count()).group_by(fault_meta))
    ).all()
    pe_by_scenario = {k: int(v) for k, v in pe_rows}

    by_scenario = []
    for en in _FAULT_CATEGORIES:
        r = scen_map.get(en)
        s_total = int(r[1]) if r else 0
        s_elig = int(r[2]) if r else 0
        s_not = int(r[3]) if r else 0
        s_adopt = int(r[4]) if r else 0
        s_reject = int(r[5]) if r else 0
        by_scenario.append(
            {
                "scenario": en,
                "problemEntries": pe_by_scenario.get(en, 0),
                "deviceDetections": s_total,
                "eligible": s_elig,
                "notEligible": s_not,
                "detecting": max(s_total - s_elig - s_not, 0),
                "adopted": s_adopt,
                "rejected": s_reject,
                "adoptionRate": _ratio(s_adopt, s_adopt + s_reject),
            }
        )

    # ---- 检测结论 / 售后状态 distribution ----
    no_issue = max(total - found - review, 0)
    conclusion_dist = [
        {"label": "Issue Detected", "count": found, "ratio": _ratio(found, total)},
        {"label": "No Issue", "count": no_issue, "ratio": _ratio(no_issue, total)},
        {"label": "Under Review", "count": review, "ratio": _ratio(review, total)},
    ]
    aftersales_dist = [
        {"label": "Replacement Eligible", "count": elig, "ratio": _ratio(elig, total)},
        {"label": "Not Eligible", "count": not_elig, "ratio": _ratio(not_elig, total)},
        {"label": "Under Review", "count": detecting, "ratio": _ratio(detecting, total)},
    ]

    # ---- 每日跟进视图 ----
    r_day = func.date(DetectRecord.created_at)
    daily_rec = (
        await db.execute(
            rbase(r_day, c_total, c_elig, c_not, c_adopt).group_by(r_day).order_by(r_day)
        )
    ).all()
    q_day = func.date(AuditLog.created_at)
    daily_q = (
        await db.execute(dqbase(q_day, func.count()).group_by(q_day))
    ).all()
    pe_by_day = {str(d): int(c) for d, c in daily_q}
    daily = []
    for d, dt, de, dn, da in daily_rec:
        key = str(d)
        d_total = int(dt)
        d_elig = int(de)
        d_not = int(dn)
        daily.append(
            {
                "date": key,
                "problemEntries": pe_by_day.get(key, 0),
                "deviceDetections": d_total,
                "eligible": d_elig,
                "notEligible": d_not,
                "detecting": max(d_total - d_elig - d_not, 0),
                "adopted": int(da),
            }
        )

    # ---- filter options (distinct countries in scope) ----
    country_rows = (
        await db.execute(
            apply_scope_for_user(
                select(User.distributor_name)
                .select_from(DetectRecord)
                .join(User, DetectRecord.user_id == User.id),
                DetectRecord,
                actor,
            )
            .where(
                DetectRecord.is_visible_in_workbench.is_(True),
                DetectRecord.source == "web",
            )
            .distinct()
        )
    ).all()
    countries = sorted({r[0] for r in country_rows if r[0]})

    return {
        "core": core,
        "byScenario": by_scenario,
        "conclusionDist": conclusion_dist,
        "afterSalesDist": aftersales_dist,
        "daily": daily,
        "countries": countries,
    }


async def dashboard_detail(
    db: AsyncSession,
    actor: AccountActor,
    *,
    date_from: Any = None,
    date_to: Any = None,
    country: str | None = None,
    account_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """明细 (sheet2 检测明细数据): per-record rows with Excel columns, paginated
    and filtered by date/country/account. Manager-scoped."""
    base = (
        select(DetectRecord, User.username, User.distributor_name)
        .select_from(DetectRecord)
        .join(User, DetectRecord.user_id == User.id)
    )
    base = apply_scope_for_user(base, DetectRecord, actor).where(
        DetectRecord.is_visible_in_workbench.is_(True),
        DetectRecord.source == "web",
    )
    if account_id is not None:
        base = base.where(DetectRecord.user_id == account_id)
    if date_from is not None:
        base = base.where(DetectRecord.created_at >= date_from)
    if date_to is not None:
        base = base.where(DetectRecord.created_at <= date_to)
    if country:
        base = base.where(User.distributor_name == country)

    total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = (
        await db.execute(
            base.order_by(DetectRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = []
    for record, username, dealer in rows:
        created = record.created_at
        items.append(
            {
                "recordType": "System Detection",
                "date": created.date().isoformat() if created else None,
                "country": dealer or "—",
                "account": username,
                "sn": record.serial_no,
                "deviceType": record.device_type,
                "scenario": record.fault_category,
                "conclusion": _conclusion_label(record.issue_detected, record.status),
                "afterSales": _aftersales_label(record.verdict),
                "adopted": _adopted_label(record.adoption_status),
                "rejectReason": record.reject_reason or "",
                "ruleVersion": _rule_version(record),
                "detectTime": created.strftime("%H:%M") if created else "",
            }
        )

    return {"items": items, "total": total, "page": page, "page_size": page_size}
