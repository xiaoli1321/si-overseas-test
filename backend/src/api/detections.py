from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.exceptions import NotFoundError
from src.core.responses import ok
from src.models.tables import User
from src.repositories.store import get_batch_task, get_record
from src.schemas.domain import BatchDetectionCreateRequest, DetectionCreateRequest
from src.schemas.frontend import batch_to_frontend, record_to_frontend
from src.services.audit import record_audit_event
from src.services.detections import (
    create_batch_detection,
    create_detection,
    process_batch_task,
    process_detection_record,
    retry_record,
)

router = APIRouter(prefix="/detections", tags=["detections"])


@router.post("")
async def create_endpoint(
    payload: DetectionCreateRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    创建单台设备诊断任务接口。

    业务流程：
    1. 在数据库中创建一个状态为 processing 诊断记录行。
    2. 记录审计日志并提交事务。
    3. 通过 BackgroundTasks 异步执行核心诊断任务（包括 VLM 大模型分析），立即返回。
    """
    try:
        record = await create_detection(
            db,
            user_id=user.id,
            serial_no=payload.serial_no,
            fault_category=payload.fault_category,
            file_ids=payload.file_ids,
            run_immediately=False,
        )
        background_tasks.add_task(process_detection_record, record.id, payload.file_ids)
    except Exception as exc:
        await record_audit_event(
            db,
            user_id=user.id,
            action="detection.create",
            target_type="detect_record",
            status="failure",
            metadata={
                "serial_no": payload.serial_no,
                "fault_category": payload.fault_category,
                "error": str(exc),
            },
        )
        await db.commit()
        raise
    await record_audit_event(
        db,
        user_id=user.id,
        action="detection.create",
        target_type="detect_record",
        target_id=record.id,
        metadata={
            "serial_no": record.serial_no,
            "fault_category": record.fault_category,
            "file_count": len(payload.file_ids),
        },
    )
    await db.commit()
    return ok(record_to_frontend(record, user))


@router.get("/{record_id}")
async def detail_endpoint(
    record_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    查询单条设备诊断记录详情接口。
    """
    record = await get_record(db, user.id, record_id)
    if record is None:
        raise NotFoundError("Detect record was not found.")
    return ok(record_to_frontend(record, user))


@router.post("/{record_id}/retry")
async def retry_endpoint(
    record_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    重试失败诊断记录的接口。
    当某个诊断因为外部 API 抖动或大模型限流失败后，可以触发一键重试。
    """
    record = await retry_record(db, user_id=user.id, record_id=record_id)
    await record_audit_event(
        db,
        user_id=user.id,
        action="detection.retry",
        target_type="detect_record",
        target_id=record.id,
        metadata={
            "serial_no": record.serial_no,
            "fault_category": record.fault_category,
        },
    )
    await db.commit()
    return ok(record_to_frontend(record, user))


@router.post("/batch")
async def batch_endpoint(
    payload: BatchDetectionCreateRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    创建批量多设备诊断任务接口。
    用于同一个故障类型下同时录入多个设备 SN 的场景。后台会分发给多路并发 worker 处理。
    """
    try:
        task = await create_batch_detection(
            db,
            user_id=user.id,
            serial_nos=payload.serial_nos,
            fault_category=payload.fault_category,
            device_files=payload.device_files,
        )
    except Exception as exc:
        await record_audit_event(
            db,
            user_id=user.id,
            action="batch.create",
            target_type="batch_task",
            status="failure",
            metadata={
                "fault_category": payload.fault_category,
                "total_count": len(payload.serial_nos),
                "error": str(exc),
            },
        )
        await db.commit()
        raise
    await record_audit_event(
        db,
        user_id=user.id,
        action="batch.create",
        target_type="batch_task",
        target_id=task.id,
        metadata={
            "fault_category": task.fault_category,
            "total_count": task.total_count,
        },
    )
    await db.commit()
    # 异步开启批处理任务的并发调度
    background_tasks.add_task(process_batch_task, task.id)
    task = await get_batch_task(db, user.id, task.id)
    return ok(batch_to_frontend(task, user))
