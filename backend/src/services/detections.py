import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
import json
import logging
import time
from typing import Any

from src.schemas.evidence import (
    DataAccuracyEvidence,
    SensorFallingOffEvidence,
    SensorAbnormalEvidence,
    ApplicationFailureEvidence,
)

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal
from src.core.exceptions import BusinessValidationError, NotFoundError
from src.core.logging import current_millis, log_context
from src.integrations import get_cgm_client
from src.integrations.overseas_adapter import STATUS_MAP
from src.integrations.vlm import QwenVlClient
from src.models.tables import BatchTask, DetectRecord, UploadedFile, User
from src.repositories.files import bind_uploaded_files_to_record, list_uploaded_files
from src.repositories.store import get_batch_records, get_batch_task, get_record
from src.rules.engine import run_rules
from src.rules.thresholds import (
    APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT,
    normalize_threshold_profile,
)
from src.services.analytics import track_diagnosis_completed
from src.services.implantation_scanner import scan_implantation_photos
from src.services.storage import get_vlm_reference, new_file_id, save_bytes_to_storage
from src.services.thresholds import current_threshold

vlm_client = QwenVlClient()
logger = logging.getLogger(__name__)
_semaphore = asyncio.Semaphore(get_settings().batch_concurrency)


async def validate_file_ownership(
    db: AsyncSession, user_id: int, file_ids: list[str]
) -> Sequence[UploadedFile]:
    if not file_ids:
        return []
    files = await list_uploaded_files(db, user_id, file_ids)
    file_map = {str(file.id): file for file in files}

    for fid in file_ids:
        if fid not in file_map:
            raise BusinessValidationError(f"File ID {fid} does not exist.")
    return files


async def _load_uploaded_files(
    db: AsyncSession, user_id: int, file_ids: list[str]
) -> Sequence[UploadedFile]:
    if not file_ids:
        return []
    return await list_uploaded_files(db, user_id, file_ids)


async def _vlm_refs_from_uploaded_files(
    file_ids: list[str], files: Sequence[UploadedFile]
) -> list[str]:
    file_map = {str(file.id): file for file in files}
    refs: list[str] = []
    for file_id in file_ids:
        uploaded_file = file_map.get(file_id)
        if uploaded_file is None:
            logger.error(
                "Uploaded file was not found while resolving VLM refs",
                extra=log_context("detection.file_ref_missing", file_id=file_id),
            )
            continue
        refs.append(await get_vlm_reference(uploaded_file))
    return refs


def _uploaded_files_metadata(files: Sequence[UploadedFile]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(file.id),
            "filename": file.filename,
            "storage_backend": file.storage_backend,
            "object_key": file.object_key,
            "public_url": file.public_url,
            "mime_type": file.mime_type,
            "file_size": file.file_size,
        }
        for file in files
    ]


async def _save_compact_glucose_file(
    db: AsyncSession,
    user_id: int,
    serial_no: str,
    raw_glucose: dict[str, Any],
    details: dict[str, Any] | None,
) -> str:
    """
    对时序数据进行混合降采样，保存为本地极简格式的 JSON 文件，并创建对应的数据库记录。
    返回文件的下载 URL 路径。
    """
    settings = get_settings()
    timezone_str = raw_glucose.get("timezone") or "UTC"
    raw_points = raw_glucose.get("points", [])

    # ── 1. 数据解析与 24 小时裁切 ─────────────────────────────
    parsed_points = []
    for p in raw_points:
        ts_raw = p.get("timestamp")
        if isinstance(ts_raw, datetime):
            ts = ts_raw
        elif isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
        else:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        try:
            val = float(p["glucose"])
        except (KeyError, TypeError, ValueError):
            continue
        parsed_points.append((ts, val))

    if not parsed_points:
        return await _write_glucose_file_record(
            db, user_id, serial_no, {"tz": timezone_str, "points": []}
        )

    parsed_points = sorted(parsed_points, key=lambda x: x[0])
    latest_time = parsed_points[-1][0]
    cutoff_time = latest_time - timedelta(hours=24)
    window_points = [p for p in parsed_points if cutoff_time <= p[0] <= latest_time]

    # ── 2. 生成保护区间 (Protected Ranges) ─────────────────────────────
    protected_ranges: list[tuple[datetime, datetime]] = []

    if details:
        # 低糖区间保护
        if details.get("persistently_low") and details["persistently_low"].get(
            "trigger_segments"
        ):
            for seg in details["persistently_low"]["trigger_segments"]:
                try:
                    start = datetime.fromisoformat(
                        seg["start_at"].replace("Z", "+00:00")
                    )
                    end = datetime.fromisoformat(seg["end_at"].replace("Z", "+00:00"))
                    protected_ranges.append(
                        (start - timedelta(hours=1), end + timedelta(hours=1))
                    )
                except Exception:
                    pass
        # 平线区间保护
        if details.get("no_fluctuation") and details["no_fluctuation"].get(
            "trigger_segments"
        ):
            for seg in details["no_fluctuation"]["trigger_segments"]:
                try:
                    start = datetime.fromisoformat(
                        seg["start_at"].replace("Z", "+00:00")
                    )
                    end = datetime.fromisoformat(seg["end_at"].replace("Z", "+00:00"))
                    protected_ranges.append(
                        (start - timedelta(hours=1), end + timedelta(hours=1))
                    )
                except Exception:
                    pass
        # 突变跳变点保护
        if details.get("sudden_fluctuation") and details["sudden_fluctuation"].get(
            "jump_points"
        ):
            for pt in details["sudden_fluctuation"]["jump_points"]:
                try:
                    ts_val = datetime.fromtimestamp(pt["timestamp"], UTC)
                    protected_ranges.append(
                        (ts_val - timedelta(hours=1), ts_val + timedelta(hours=1))
                    )
                except Exception:
                    pass

    # ── 3. 进行数据分类并执行降采样 ───────────────────────────
    protected_points = []
    normal_points = []

    for ts, val in window_points:
        is_protected = False
        for p_start, p_end in protected_ranges:
            if p_start <= ts <= p_end:
                is_protected = True
                break
        if is_protected:
            protected_points.append((ts, val))
        else:
            normal_points.append((ts, val))

    # 普通区点位 20 分钟降采样
    downsampled_normal = []
    buckets = {}
    for ts, val in normal_points:
        bucket_id = int(ts.timestamp() // 1200)
        if bucket_id not in buckets:
            buckets[bucket_id] = (ts, val)
            downsampled_normal.append((ts, val))

    combined = sorted(protected_points + downsampled_normal, key=lambda x: x[0])
    points_tuples = [[int(ts.timestamp()), val] for ts, val in combined]

    compact_data = {"tz": timezone_str, "points": points_tuples}

    return await _write_glucose_file_record(db, user_id, serial_no, compact_data)


async def _write_glucose_file_record(
    db: AsyncSession, user_id: int, serial_no: str, compact_data: dict[str, Any]
) -> str:
    from src.repositories.files import create_uploaded_file

    file_id = new_file_id("file-glucose")
    contents = json.dumps(compact_data, ensure_ascii=False).encode("utf-8")
    stored = await save_bytes_to_storage(
        user_id=user_id,
        file_id=file_id,
        filename=f"{file_id}.json",
        data=contents,
        content_type="application/json",
    )

    db_file = await create_uploaded_file(
        db,
        file_id=file_id,
        user_id=user_id,
        filename=f"glucose_series_{serial_no}.json",
        storage_backend=stored.storage_backend,
        object_key=stored.object_key,
        file_size=stored.file_size,
    )
    await db.flush()
    await db.refresh(db_file)
    return db_file.public_url


async def _load_cgm_inputs(
    client: Any,
    serial_no: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    device, glucose, alarm = await asyncio.gather(
        client.get_device(serial_no),
        client.get_glucose_series(serial_no),
        client.get_latest_alarm(serial_no),
    )
    if isinstance(device, list):
        if not device:
            raise NotFoundError(f"Device {serial_no} not found")
        device = device[0]
    return device, glucose, alarm


def _unactivated_device_inputs(
    serial_no: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """构造植入失败场景的占位设备数据，跳过海外设备接口查询。

    植入失败 (Application failure) 场景下设备通常尚未激活，海外 API 查询不到（返回为空），
    因此这里不再调用设备接口，直接信任用户输入的 SN / deviceName。
    规则引擎判定植入失败时仅依赖上传的图片，不使用设备 / 血糖 / 告警数据，
    故返回一份最小占位数据即可，仅用于回填诊断记录的设备快照。
    """
    device = {
        "sn": serial_no,
        "type": None,  # 物理板卡号未知（设备未激活）
        "device_type": get_settings().default_device_type,
        "status": "not_activated",
        "device_status": 0,  # 0: 未激活
        "fall_off_status": "not_fallen_off",
        "wear_days": 0.0,
        "wearHours": 0.0,
        "activatedAt": "",
        "lastDataAt": "",
        "timeZone": None,
    }
    glucose: dict[str, Any] = {"points": [], "timezone": None}
    alarm = {
        "latest_alarm_status": 0,
        "latest_sensor_internal_value": 0,
        "abnormal_duration_minutes": 0,
        "latest_sensor_alert": "",
    }
    return device, glucose, alarm


async def create_detection(
    db: AsyncSession,
    *,
    user_id: int,
    serial_no: str,
    fault_category: str,
    file_ids: list[str],
    batch_task_id: int | None = None,
    run_immediately: bool = True,
    threshold_config: dict | None = None,
    source: str = "web",
) -> DetectRecord:
    files = await validate_file_ownership(db, user_id, file_ids)
    if threshold_config is None:
        threshold = await current_threshold(db, user_id)
        snapshot = jsonable_encoder(normalize_threshold_profile(threshold.config))
        threshold_id = threshold.id
    else:
        snapshot = jsonable_encoder(normalize_threshold_profile(threshold_config))
        threshold_id = None
    record = DetectRecord(
        user_id=user_id,
        batch_task_id=batch_task_id,
        serial_no=serial_no,
        source=source,
        device_type=get_settings().default_device_type,
        fault_category=fault_category,
        status="processing",
        created_by=user_id,
        started_at=datetime.now(UTC),
        threshold_id=threshold_id,
        threshold_snapshot=snapshot,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    if source == "openapi":
        try:
            await bind_uploaded_files_to_record(
                db,
                user_id=user_id,
                file_ids=file_ids,
                detect_record_id=record.id,
            )
        except ValueError as exc:
            raise BusinessValidationError(str(exc)) from exc
    if run_immediately:
        await execute_detection(db, record, file_ids=file_ids, preloaded_files=files)
    return record


async def execute_detection(
    db: AsyncSession,
    record: DetectRecord,
    *,
    file_ids: list[str],
    preloaded_files: Sequence[UploadedFile] | None = None,
) -> DetectRecord:
    """
    执行售后诊断任务的核心逻辑。

    业务流程：
    1. 获取凭证文件及生成大模型输入路径。
    2. 获取用户的自定义判定规则阈值快照。
    3. 并发获取海外三方系统设备的基础数据、血糖数据和告警记录
       （植入失败场景设备未激活、接口查不到，跳过查询并信任用户输入）。
    4. 可选：针对特定故障，调用 VLM 视觉大模型对用户上传的凭证图进行分析。
    5. 调用规则引擎判定诊断结果。
    6. 将所有的诊断结果、命中的规则以及完整证据链序列化并存入数据库。
    """
    started = time.perf_counter()
    logger.info(
        "Detection execution started",
        extra=log_context(
            "detection.started",
            record_id=record.id,
            serial_no=record.serial_no,
            fault_category=record.fault_category,
            file_count=len(file_ids),
        ),
    )
    try:
        # Step 1: 加载并校验上传的凭证文件，解析出提供给 VLM 的图片引用 (本地路径或 URL)
        if preloaded_files is not None:
            uploaded_files = preloaded_files
        else:
            uploaded_files = await _load_uploaded_files(db, record.user_id, file_ids)
        vlm_image_refs = await _vlm_refs_from_uploaded_files(file_ids, uploaded_files)

        # Step 2: use the snapshot taken at task creation. This keeps async
        # execution reproducible when a user changes thresholds meanwhile.
        if record.threshold_snapshot is None:
            threshold = await current_threshold(db, record.user_id)
            threshold_config = threshold.config
            record.threshold_id = threshold.id
            record.threshold_snapshot = jsonable_encoder(threshold.config)
        else:
            threshold_config = normalize_threshold_profile(record.threshold_snapshot)
            record.threshold_snapshot = jsonable_encoder(threshold_config)

        # Step 3: 获取设备数据 (设备状态、血糖序列、告警信息)
        # 植入失败 (Application failure) 场景：设备尚未激活，海外 API 查询不到（返回为空），
        # 因此不调用设备接口，直接信任用户输入的 SN / deviceName，仅走图片识别流程。
        if record.fault_category == "Application failure":
            device, glucose, alarm = _unactivated_device_inputs(record.serial_no)
        else:
            client = get_cgm_client()
            device, glucose, alarm = await _load_cgm_inputs(client, record.serial_no)

        # Step 4: 根据故障品类，按需运行 VLM 大模型多模态图片识别
        vision_analysis = None
        implantation_scan_data = []
        min_images = APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT
        if record.fault_category == "Application failure" and len(file_ids) >= min_images:
            # 软件/应用故障：识别图片中是否有探头、针头是否外露、不干胶是否脱落等
            vision_raw = await vlm_client.analyze_sensor_photos(vlm_image_refs)
            vision_analysis = vision_raw.model_dump()

            logger.info(
                "VLM analysis result for detection",
                extra=log_context(
                    "detection.vlm_analysis",
                    record_id=record.id,
                    serial_no=record.serial_no,
                    final_scenario=vision_raw.final_scenario,
                    final_confidence=vision_raw.final_confidence,
                    scenario_count=len(vision_raw.scenarios or []),
                    # Log all scenarios with matched/confidence/reason (truncated)
                    scenarios_detail=[
                        {
                            "scenario": s.scenario,
                            "matched": s.matched,
                            "confidence": s.confidence,
                            "reason": s.reason[:300] if s.reason else "",
                        }
                        for s in (vision_raw.scenarios or [])
                    ],
                ),
            )

            try:
                scanner_results = await scan_implantation_photos(vlm_image_refs)
                implantation_scan_data = list(scanner_results)
            except Exception as exc:
                logger.error(
                    "Implantation scanner failed",
                    extra=log_context(
                        "detection.implantation_scanner_failed",
                        record_id=record.id,
                        serial_no=record.serial_no,
                        error_type=type(exc).__name__,
                    ),
                )
                implantation_scan_data = []
        elif (
            record.fault_category == "Data accuracy" and file_ids and len(file_ids) >= 4
        ):
            # 血糖准确性：当自动规则未命中且提供了足够对照片时，通过 VLM 分析血糖对比图
            vision_analysis = (
                await vlm_client.analyze_glucose_readings(vlm_image_refs)
            ).model_dump()

        # Step 5: 将所有输入参数喂给规则引擎，执行业务判定
        result = run_rules(
            fault_category=record.fault_category,
            device=device,
            glucose_series=glucose,
            alarm=alarm,
            threshold_config=threshold_config,
            file_ids=file_ids,
            vision_analysis=vision_analysis,
        )

        # Step 6: 判定成功，回填诊断记录 (DetectRecord) 相关属性
        record.device_type = device["device_type"]
        record.status = "completed"
        record.verdict = result.verdict
        record.issue_detected = (
            "Issue Detected" if result.issue_detected else "no issue"
        )
        record.fault_subtype = result.fault_subtype
        record.reasons = "\n".join(result.reasons)

        # 封装文件元数据
        files_meta = [
            {
                "file_id": item["id"],
                "filename": item["filename"],
                "public_url": item["public_url"],
                "file_size": item["file_size"],
            }
            for item in _uploaded_files_metadata(uploaded_files)
        ]

        device_status_int = int(device.get("device_status") or 1)
        device_snap = {
            "sn": device.get("serial_no") or device.get("sn") or record.serial_no,
            "type": device.get("type"),
            "device_type": device.get(
                "device_type", get_settings().default_device_type
            ),
            "wear_days": float(device.get("wear_days") or 0.0),
            "wearHours": device.get("wearHours"),
            "device_status": device_status_int,
            "fall_off_status": device.get("fall_off_status", "not_fallen_off"),
            "status": device.get("status")
            or STATUS_MAP.get(device_status_int, "wearing"),
            "activatedAt": device.get("activatedAt") or "",
            "lastDataAt": device.get("lastDataAt") or "",
            "timeZone": device.get("timeZone"),
        }

        # 根据判定种类，组装证据链结构并执行强类型 Pydantic 校验
        if record.fault_category == "Data accuracy":
            details_dict = result.evidence.get("data_accuracy_details")
            glucose_url = await _save_compact_glucose_file(
                db, record.user_id, record.serial_no, glucose, details_dict
            )

            evidence_data = {
                "matched_rules": result.matched_rules,
                "files_metadata": files_meta,
                "device": device_snap,
                "glucose_series_url": glucose_url,
                "vision_analysis": result.evidence.get("vision_analysis"),
                "data_accuracy_details": details_dict,
            }
            validated = DataAccuracyEvidence.model_validate(evidence_data)

        elif record.fault_category == "Sensor falling off":
            evidence_data = {
                "matched_rules": result.matched_rules,
                "files_metadata": files_meta,
                "device": device_snap,
            }
            validated = SensorFallingOffEvidence.model_validate(evidence_data)

        elif record.fault_category == "Sensor Abnormal":
            evidence_data = {
                "matched_rules": result.matched_rules,
                "files_metadata": files_meta,
                "device": device_snap,
                "alarm": result.evidence.get("alarm"),
            }
            validated = SensorAbnormalEvidence.model_validate(evidence_data)

        elif record.fault_category == "Application failure":
            evidence_data = {
                "matched_rules": result.matched_rules,
                "files_metadata": files_meta,
                "device": device_snap,
                "vision": result.evidence.get("vision"),
                "implantation_scanner": implantation_scan_data,
                "file_ids": file_ids,
            }
            validated = ApplicationFailureEvidence.model_validate(evidence_data)
        else:
            # 兜底
            from src.schemas.evidence import BaseEvidence

            evidence_data = {
                "matched_rules": result.matched_rules,
                "files_metadata": files_meta,
            }
            validated = BaseEvidence.model_validate(evidence_data)

        record.evidence = jsonable_encoder(validated)
        record.error_message = None
        record.completed_at = datetime.now(UTC)
        logger.info(
            "Detection execution completed",
            extra=log_context(
                "detection.completed",
                duration_ms=current_millis(started),
                record_id=record.id,
                serial_no=record.serial_no,
                fault_category=record.fault_category,
                verdict=result.verdict,
                fault_subtype=result.fault_subtype,
                matched_rule_count=len(result.matched_rules),
                vision_analysis_keys=list(vision_analysis.keys())
                if vision_analysis
                else None,
                vision_final_scenario=vision_analysis.get("final_scenario")
                if vision_analysis
                else None,
                vision_final_confidence=vision_analysis.get("final_confidence")
                if vision_analysis
                else None,
                vision_scenario_count=len(vision_analysis.get("scenarios") or [])
                if vision_analysis
                else None,
            ),
        )
    except Exception as exc:
        logger.exception(
            "Detection execution failed",
            extra=log_context(
                "detection.failed",
                duration_ms=current_millis(started),
                record_id=record.id,
                serial_no=record.serial_no,
                fault_category=record.fault_category,
                error_type=type(exc).__name__,
            ),
        )
        record.status = "failed"
        detail = str(exc).strip() or "no details returned by the upstream service"
        record.error_message = f"{type(exc).__name__}: {detail}"
        record.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(record)

    if record.status == "completed":
        try:
            user_res = await db.execute(select(User).where(User.id == record.user_id))
            user_obj = user_res.scalar_one_or_none()
            if user_obj:
                is_ai = False
                # Check rules or category
                if (
                    "result" in locals()
                    and result
                    and result.matched_rules
                    and any("vlm" in r.lower() for r in result.matched_rules)
                ):
                    is_ai = True
                elif (
                    record.fault_category == "Application failure"
                    and file_ids
                    and len(file_ids) >= 1
                ):
                    is_ai = True

                judgment_source = "AI (VLM)" if is_ai else "Rule Engine"
                has_images = bool(file_ids and len(file_ids) > 0)
                await track_diagnosis_completed(
                    db,
                    user=user_obj,
                    record=record,
                    judgment_source=judgment_source,
                    has_images=has_images,
                )
                await db.commit()
        except Exception as track_exc:
            logger.exception(
                "Diagnosis completion tracking failed",
                extra=log_context(
                    "detection.analytics_tracking_failed",
                    record_id=record.id,
                    serial_no=record.serial_no,
                    error_type=type(track_exc).__name__,
                ),
            )

    return record


async def create_batch_detection(
    db: AsyncSession,
    *,
    user_id: int,
    serial_nos: list[str],
    fault_category: str,
    device_files: dict[str, list[str]] | None = None,
) -> BatchTask:
    all_file_ids = []
    if device_files:
        for files in device_files.values():
            all_file_ids.extend(files)
    await validate_file_ownership(db, user_id, all_file_ids)

    settings = get_settings()
    if len(serial_nos) > settings.batch_max_serials:
        raise BusinessValidationError(
            f"Batch size cannot exceed {settings.batch_max_serials} SNs."
        )
    task = BatchTask(
        user_id=user_id,
        fault_category=fault_category,
        total_count=len(serial_nos),
        status="pending",
        created_by=user_id,
    )
    db.add(task)
    await db.flush()
    for serial_no in serial_nos:
        files = (device_files or {}).get(serial_no, [])
        db.add(
            DetectRecord(
                user_id=user_id,
                batch_task_id=task.id,
                serial_no=serial_no,
                device_type=get_settings().default_device_type,
                fault_category=fault_category,
                status="pending",
                created_by=user_id,
                evidence={"file_ids": files} if files else None,
            )
        )
    await db.commit()
    await db.refresh(task)
    return task


async def process_batch_task(task_id: int) -> None:
    async with AsyncSessionLocal() as db:
        task = await _get_task_any_user(db, task_id)
        if task is None:
            logger.error(
                "Batch task was not found",
                extra=log_context("batch.not_found", task_id=task_id),
            )
            return
        task.status = "processing"
        task.started_at = datetime.now(UTC)
        await db.commit()
        records = await get_batch_records(db, task.id)

    started = time.perf_counter()
    logger.info(
        "Batch task started",
        extra=log_context(
            "batch.started",
            task_id=task.id,
            record_count=len(records),
            fault_category=task.fault_category,
        ),
    )
    await asyncio.gather(*[_process_one(record.id) for record in records])

    async with AsyncSessionLocal() as db:
        task = await _get_task_any_user(db, task_id)
        if task is None:
            return
        records = await get_batch_records(db, task.id)
        task.success_count = sum(
            1 for record in records if record.status == "completed"
        )
        task.failed_count = sum(1 for record in records if record.status == "failed")
        task.status = "completed"
        task.completed_at = datetime.now(UTC)
        await db.commit()
        logger.info(
            "Batch task completed",
            extra=log_context(
                "batch.completed",
                duration_ms=current_millis(started),
                task_id=task.id,
                success_count=task.success_count,
                failed_count=task.failed_count,
            ),
        )


async def _process_one(record_id: int) -> None:
    async with _semaphore:
        logger.info(
            "Batch worker started record processing",
            extra=log_context("batch.record_started", record_id=record_id),
        )
        async with AsyncSessionLocal() as db:
            record = await _get_record_any_user(db, record_id)
            if record is None:
                return
            record.status = "processing"
            record.started_at = datetime.now(UTC)
            await db.commit()
            file_ids = []
            if (
                record.evidence
                and isinstance(record.evidence, dict)
                and "file_ids" in record.evidence
            ):
                file_ids = record.evidence["file_ids"]
            await execute_detection(db, record, file_ids=file_ids)


async def process_detection_record(record_id: int, file_ids: list[str]) -> None:
    async with _semaphore:
        logger.info(
            "Detection background task started",
            extra=log_context(
                "detection.task_started", record_id=record_id, file_count=len(file_ids)
            ),
        )
        async with AsyncSessionLocal() as db:
            try:
                record = await _get_record_any_user(db, record_id)
                if record is None:
                    return
                record.status = "processing"
                if record.started_at is None:
                    record.started_at = datetime.now(UTC)
                await db.commit()
                await execute_detection(db, record, file_ids=file_ids)
            except Exception:
                logger.exception(
                    "Detection background task failed unexpectedly",
                    extra=log_context("detection.task_failed", record_id=record_id),
                )
                try:
                    record = await _get_record_any_user(db, record_id)
                    if record is not None:
                        record.status = "failed"
                        record.error_message = "Background task failed unexpectedly"
                        record.completed_at = datetime.now(UTC)
                        await db.commit()
                except Exception:
                    logger.exception(
                        "Failed to update record status after background task error",
                        extra=log_context(
                            "detection.task_cleanup_failed", record_id=record_id
                        ),
                    )


async def retry_record(
    db: AsyncSession, *, user_id: int, record_id: int
) -> DetectRecord:
    record = await get_record(db, user_id, record_id, source="web")
    if record is None:
        raise NotFoundError("Detect record was not found.")
    record.status = "processing"
    record.error_message = None
    record.started_at = datetime.now(UTC)
    await db.commit()
    return await execute_detection(db, record, file_ids=[])


async def update_feedback(
    db: AsyncSession,
    *,
    user_id: int,
    record_id: int,
    feedback_status: str,
    reject_reason: str | None,
) -> DetectRecord:
    record = await get_record(db, user_id, record_id, source="web")
    if record is None:
        raise NotFoundError("Detect record was not found.")
    record.adoption_status = feedback_status
    record.reject_reason = reject_reason if feedback_status == "rejected" else None
    record.adopted_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(record)
    return record


async def delete_record(
    db: AsyncSession,
    *,
    user_id: int,
    record_id: int,
) -> DetectRecord:
    record = await get_record(db, user_id, record_id, source="web")
    if record is None:
        raise NotFoundError("Detect record was not found.")
    record.is_visible_in_workbench = False
    await db.commit()
    await db.refresh(record)
    return record


async def batch_delete_records(
    db: AsyncSession,
    *,
    user_id: int,
    record_ids: list[int],
) -> list[int]:
    if not record_ids:
        return []

    query = select(DetectRecord.id).where(
        DetectRecord.id.in_(record_ids),
        DetectRecord.user_id == user_id,
        DetectRecord.is_visible_in_workbench.is_(True),
        DetectRecord.source == "web",
    )
    result = await db.execute(query)
    target_ids = list(result.scalars().all())

    if not target_ids:
        return []

    stmt = (
        update(DetectRecord)
        .where(DetectRecord.id.in_(target_ids))
        .values(is_visible_in_workbench=False, updated_at=datetime.now(UTC))
    )
    await db.execute(stmt)
    await db.commit()
    return target_ids


async def _get_task_any_user(db: AsyncSession, task_id: int) -> BatchTask | None:
    """Internal worker lookup: task ids are created by scoped APIs before this background job runs."""
    result = await db.execute(select(BatchTask).where(BatchTask.id == task_id))
    return result.scalar_one_or_none()


async def _get_record_any_user(db: AsyncSession, record_id: int) -> DetectRecord | None:
    """Internal worker lookup: record ids are attached to a scoped batch task before execution."""
    result = await db.execute(select(DetectRecord).where(DetectRecord.id == record_id))
    return result.scalar_one_or_none()
