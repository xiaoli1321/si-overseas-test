from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.tables import Threshold
from src.repositories.store import (
    get_active_threshold,
    get_next_threshold_version,
    get_threshold_history as repo_get_threshold_history,
    get_threshold_by_version,
)
from src.rules.thresholds import default_thresholds, normalize_threshold_profile


async def current_threshold(db: AsyncSession, user_id: int) -> Threshold:
    threshold = await get_active_threshold(db, user_id)
    if threshold is None:
        threshold = Threshold(
            user_id=user_id, version=1, config_json=default_thresholds(), is_active=True
        )
        db.add(threshold)
        await db.commit()
        await db.refresh(threshold)
    return threshold


async def save_threshold(
    db: AsyncSession,
    user_id: int,
    config: dict,
    remark: str | None = None,
    restored_from: int | None = None,
) -> Threshold:
    version = await get_next_threshold_version(db, user_id)
    config = normalize_threshold_profile(config)
    if "rules" in config:
        config = {
            **config,
            "version": version,
            "savedAt": datetime.now(UTC).isoformat(),
        }
    await db.execute(
        update(Threshold).where(Threshold.user_id == user_id).values(is_active=False)
    )
    threshold = Threshold(
        user_id=user_id,
        version=version,
        config_json=config,
        is_active=True,
        remark=remark,
        restored_from=restored_from,
        is_deleted=False,
    )
    db.add(threshold)
    await db.commit()
    await db.refresh(threshold)
    return threshold


async def reset_threshold(db: AsyncSession, user_id: int) -> Threshold:
    return await save_threshold(
        db, user_id, default_thresholds(), remark="Reset to defaults"
    )


async def get_threshold_history(db: AsyncSession, user_id: int) -> list[Threshold]:
    history = await repo_get_threshold_history(db, user_id)
    return list(history)


async def rollback_threshold(
    db: AsyncSession,
    user_id: int,
    version: int,
    remark: str | None = None,
) -> Threshold:
    target = await get_threshold_by_version(db, user_id, version)
    if target is None:
        raise NotFoundError(
            f"Threshold configuration with version {version} not found."
        )

    config = dict(target.config_json)
    # Strip out nested metadata if present to let save_threshold regenerate them cleanly
    if "version" in config:
        config.pop("version")
    if "savedAt" in config:
        config.pop("savedAt")

    resolved_remark = remark or f"Restored from Version {version}"
    return await save_threshold(
        db,
        user_id,
        config,
        remark=resolved_remark,
        restored_from=version,
    )


async def hide_threshold(db: AsyncSession, user_id: int, version: int) -> Threshold:
    target = await get_threshold_by_version(db, user_id, version)
    if target is None:
        raise NotFoundError(
            f"Threshold configuration with version {version} not found."
        )
    target.is_deleted = True
    await db.commit()
    await db.refresh(target)
    return target


async def update_threshold_remark(
    db: AsyncSession,
    user_id: int,
    version: int,
    remark: str | None,
) -> Threshold:
    target = await get_threshold_by_version(db, user_id, version)
    if target is None:
        raise NotFoundError(
            f"Threshold configuration with version {version} not found."
        )
    target.remark = remark
    await db.commit()
    await db.refresh(target)
    return target
