from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, require_manager
from src.core.database import get_db
from src.core.responses import ok
from src.models.tables import User
from src.repositories.analytics import (
    analytics_summary,
    create_analytics_event,
    dashboard_detail,
    dashboard_overview,
    query_usage_summary,
)
from src.schemas.analytics import (
    AnalyticsEventRequest,
    AnalyticsSummaryResponse,
    DeviceQueryEventProperties,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _parse_from(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_to(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    except ValueError:
        return None


@router.post("/events")
async def create_event_endpoint(
    payload: AnalyticsEventRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    properties = payload.properties
    if payload.event_name == "device.query":
        context = {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "distributor_id": user.distributor_id,
            "distributor_name": user.distributor_name,
        }
        full_props = {**context, **(properties or {})}
        validated = DeviceQueryEventProperties(**full_props)
        properties = validated.model_dump()

    event = await create_analytics_event(
        db,
        user_id=user.id,
        event_name=payload.event_name,
        source=payload.source,
        properties=properties,
    )
    await db.commit()
    return ok({"id": event.id})


@router.get("/summary")
async def summary_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    summary = AnalyticsSummaryResponse.model_validate(
        await analytics_summary(db, user.id)
    )
    return ok(summary.model_dump(by_alias=True))


@router.get("/query-usage")
async def query_usage_endpoint(
    manager: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Manager-only view of device-query usage (validates batch-query demand)."""
    return ok(await query_usage_summary(db, manager))


@router.get("/dashboard/overview")
async def dashboard_overview_endpoint(
    manager: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
    date_from: str | None = None,
    date_to: str | None = None,
    country: str | None = None,
    account_id: int | None = None,
) -> dict:
    """概览: manager-only aggregated dashboard (matches 大盘数据概览 sheet)."""
    return ok(
        await dashboard_overview(
            db,
            manager,
            date_from=_parse_from(date_from),
            date_to=_parse_to(date_to),
            country=country,
            account_id=account_id,
        )
    )


@router.get("/dashboard/detail")
async def dashboard_detail_endpoint(
    manager: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
    date_from: str | None = None,
    date_to: str | None = None,
    country: str | None = None,
    account_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> dict:
    """明细: manager-only detection detail rows (matches 明细数据 sheet)."""
    return ok(
        await dashboard_detail(
            db,
            manager,
            date_from=_parse_from(date_from),
            date_to=_parse_to(date_to),
            country=country,
            account_id=account_id,
            page=page,
            page_size=page_size,
        )
    )
