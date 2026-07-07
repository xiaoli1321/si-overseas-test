import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.logging import log_context
from src.core.responses import ok
from src.models.tables import User
from src.schemas.domain import (
    ThresholdResponse,
    ThresholdSaveRequest,
    ThresholdRollbackRequest,
    UpdateRemarkRequest,
)
from src.schemas.frontend import threshold_to_frontend
from src.services.audit import record_audit_event
from src.services.thresholds import (
    current_threshold,
    get_threshold_history,
    reset_threshold,
    rollback_threshold,
    save_threshold,
    hide_threshold,
    update_threshold_remark,
)

router = APIRouter(prefix="/thresholds", tags=["thresholds"])
logger = logging.getLogger(__name__)


@router.get("/current")
async def current_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    threshold = await current_threshold(db, user.id)
    logger.info(
        "Current threshold loaded",
        extra=log_context(
            "threshold.current_loaded", user_id=user.id, version=threshold.version
        ),
    )
    return ok(threshold_to_frontend(threshold))


@router.post("")
async def save_endpoint(
    payload: ThresholdSaveRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    threshold = await save_threshold(db, user.id, payload.config, remark=payload.remark)
    await record_audit_event(
        db,
        user_id=user.id,
        action="threshold.save",
        target_type="threshold",
        target_id=threshold.id,
        metadata={"version": threshold.version, "remark": payload.remark},
    )
    await db.commit()
    logger.info(
        "Threshold saved",
        extra=log_context(
            "threshold.saved",
            user_id=user.id,
            threshold_id=threshold.id,
            version=threshold.version,
        ),
    )
    return ok(threshold_to_frontend(threshold))


@router.post("/reset")
async def reset_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    threshold = await reset_threshold(db, user.id)
    await record_audit_event(
        db,
        user_id=user.id,
        action="threshold.reset",
        target_type="threshold",
        target_id=threshold.id,
        metadata={"version": threshold.version},
    )
    await db.commit()
    logger.info(
        "Threshold reset",
        extra=log_context(
            "threshold.reset",
            user_id=user.id,
            threshold_id=threshold.id,
            version=threshold.version,
        ),
    )
    return ok(threshold_to_frontend(threshold))


@router.get("/history")
async def history_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    history = await get_threshold_history(db, user.id)
    logger.info(
        "Threshold history listed",
        extra=log_context(
            "threshold.history_listed", user_id=user.id, history_count=len(history)
        ),
    )
    return ok([threshold_to_frontend(t) for t in history])


@router.post("/rollback/{version}")
async def rollback_endpoint(
    version: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: ThresholdRollbackRequest | None = None,
) -> dict:
    remark = payload.remark if payload else None
    threshold = await rollback_threshold(db, user.id, version, remark=remark)
    await record_audit_event(
        db,
        user_id=user.id,
        action="threshold.rollback",
        target_type="threshold",
        target_id=threshold.id,
        metadata={
            "version": threshold.version,
            "rolled_back_to": version,
            "remark": remark,
        },
    )
    await db.commit()
    logger.info(
        "Threshold rolled back",
        extra=log_context(
            "threshold.rolled_back",
            user_id=user.id,
            threshold_id=threshold.id,
            version=threshold.version,
            rolled_back_to=version,
        ),
    )
    return ok(threshold_to_frontend(threshold))


@router.delete("/history/{version}")
async def hide_endpoint(
    version: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    threshold = await hide_threshold(db, user.id, version)
    await record_audit_event(
        db,
        user_id=user.id,
        action="threshold.hide",
        target_type="threshold",
        target_id=threshold.id,
        metadata={"version": version},
    )
    await db.commit()
    logger.info(
        "Threshold hidden",
        extra=log_context(
            "threshold.hidden",
            user_id=user.id,
            threshold_id=threshold.id,
            version=version,
        ),
    )
    return ok(threshold_to_frontend(threshold))


@router.put("/history/{version}/remark")
async def update_remark_endpoint(
    version: int,
    payload: UpdateRemarkRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    threshold = await update_threshold_remark(db, user.id, version, payload.remark)
    await record_audit_event(
        db,
        user_id=user.id,
        action="threshold.update_remark",
        target_type="threshold",
        target_id=threshold.id,
        metadata={"version": version, "remark": payload.remark},
    )
    await db.commit()
    logger.info(
        "Threshold remark updated",
        extra=log_context(
            "threshold.remark_updated",
            user_id=user.id,
            threshold_id=threshold.id,
            version=version,
        ),
    )
    return ok(threshold_to_frontend(threshold))
