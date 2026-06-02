from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.responses import ok
from src.models.tables import User
from src.repositories.analytics import analytics_summary, create_analytics_event
from src.schemas.analytics import (
    AnalyticsEventRequest,
    AnalyticsSummaryResponse,
    DeviceQueryEventProperties,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
