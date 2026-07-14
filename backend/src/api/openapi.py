"""Partner-facing fault detection API, isolated from the Web API namespace."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InvalidParamsError,
    NotFoundError,
)
from src.core.responses import ok
from src.integrations import get_cgm_client
from src.models.tables import DetectRecord, User
from src.repositories.files import get_uploaded_file
from src.repositories.openapi import claim_openapi_idempotency_key, get_openapi_idempotency_key
from src.repositories.store import get_record
from src.rules.thresholds import openapi_threshold_template
from src.schemas.domain import LoginRequest, OpenApiDetectionCreateRequest
from src.services.audit import record_audit_event
from src.services.auth import login
from src.services.detections import create_detection, process_detection_record
from src.services.files import save_uploaded_file
from src.services.storage import get_stored_file_download_url, stored_file_exists
from src.services.thresholds import current_threshold

router = APIRouter(tags=["openapi"])

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
IDEMPOTENCY_TTL = timedelta(hours=24)


def _camelize(value: Any) -> Any:
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        parts = key.split("_")
        camel_key = parts[0] + "".join(part.title() for part in parts[1:])
        result[camel_key] = _camelize(item)
    return result


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _rewrite_openapi_file_urls(value: Any) -> Any:
    if isinstance(value, list):
        return [_rewrite_openapi_file_urls(item) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_openapi_file_urls(item) for key, item in value.items()}
    if isinstance(value, str) and value.startswith("/api/v1/files/"):
        return value.replace("/api/v1/files/", "/openapi/v1/files/", 1)
    return value


def _openapi_threshold_config(snapshot: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(snapshot)
    rules = config.get("rules", {})
    deviation = rules.get("inaccuracy", {}).get("deviation")
    if isinstance(deviation, dict):
        for field in (
            "within48hPairCount",
            "within48hQualifiedPairCount",
            "after48hPairCount",
            "after48hQualifiedPairCount",
        ):
            deviation.pop(field, None)
    application = rules.get("applicationFailure")
    if isinstance(application, dict):
        application.pop("photoCount", None)
    return config


def _openapi_evidence(record: DetectRecord) -> dict[str, Any]:
    """Return a compact partner-facing evidence summary.

    Persisted evidence contains Web detail-page helpers and internal image
    analysis payloads. Keep the OpenAPI response small and avoid exposing
    uploaded image metadata or scanner internals.
    """
    evidence = record.evidence if isinstance(record.evidence, dict) else {}
    result: dict[str, Any] = {
        "matched_rules": evidence.get("matched_rules", []),
    }

    if record.fault_category in {
        "Data accuracy",
        "Sensor falling off",
        "Sensor Abnormal",
    }:
        for key in (
            "device",
            "glucose_series_url",
            "vision_analysis",
            "data_accuracy_details",
            "alarm",
        ):
            if evidence.get(key) is not None:
                result[key] = evidence[key]
        return _rewrite_openapi_file_urls(_camelize(result))

    if record.fault_category == "Application failure":
        if evidence.get("device") is not None:
            result["device"] = evidence["device"]
        vision = evidence.get("vision")
        if isinstance(vision, dict):
            compact_vision = {
                "score": vision.get("score"),
                "final_scenario": vision.get("final_scenario"),
                "final_confidence": vision.get("final_confidence"),
                "features": vision.get("features"),
            }
            result["vision"] = {
                key: value
                for key, value in compact_vision.items()
                if value is not None
            }
        return _camelize(result)

    return _camelize(result)


def _detection_data(record: DetectRecord) -> dict[str, Any]:
    snapshot = record.threshold_snapshot or {}
    return {
        "detectionId": str(record.id),
        "serialNo": record.serial_no,
        "faultCategory": record.fault_category,
        "status": record.status,
        "verdict": record.verdict,
        "faultSubtype": record.fault_subtype,
        "issueDetected": record.issue_detected == "Issue Detected",
        "reason": record.reasons,
        "thresholdVersion": snapshot.get("version", record.threshold_id),
        "thresholdConfig": _camelize(_openapi_threshold_config(snapshot)),
        "evidence": _openapi_evidence(record),
        "errorMessage": record.error_message,
        "createdAt": _timestamp(record.created_at),
        "completedAt": _timestamp(record.completed_at),
    }


def _detection_create_data(record: DetectRecord) -> dict[str, Any]:
    """Return only the submission receipt; completed details are polled separately."""
    return {
        "detectionId": str(record.id),
        "serialNo": record.serial_no,
        "faultCategory": record.fault_category,
        "createdAt": _timestamp(record.created_at),
    }


def _request_hash(payload: OpenApiDetectionCreateRequest) -> str:
    serialized = json.dumps(
        payload.model_dump(by_alias=False), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def _resolve_serial_no(payload: OpenApiDetectionCreateRequest) -> str:
    if payload.serial_no:
        return payload.serial_no
    assert payload.device_name is not None
    try:
        matched = await get_cgm_client().get_device(payload.device_name)
    except (NotFoundError, InvalidParamsError) as exc:
        raise BusinessValidationError(
            "No device matched deviceName; submit serialNo to identify one device.",
            data={"candidateSerialNos": []},
        ) from exc
    matches = matched if isinstance(matched, list) else [matched]
    candidate_sns = sorted(
        {str(device.get("sn") or device.get("serial_no")) for device in matches if device.get("sn") or device.get("serial_no")}
    )
    if len(candidate_sns) != 1:
        state = "No device matched" if not candidate_sns else "Multiple devices matched"
        raise BusinessValidationError(
            f"{state} deviceName; submit serialNo to identify one device.",
            data={"candidateSerialNos": candidate_sns},
        )
    return candidate_sns[0]


@router.post("/auth/login")
async def login_endpoint(
    payload: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    token, user = await login(db, payload.email, payload.password, channel="openapi")
    await record_audit_event(
        db,
        user_id=user.id,
        action="openapi.auth.login",
        target_type="user",
        target_id=user.id,
        metadata={"channel": "openapi"},
    )
    await db.commit()
    return ok(
        {
            "accessToken": token,
            "expiresIn": 8 * 60 * 60,
            "distributor": {
                "id": str(user.distributor_id) if user.distributor_id else None,
                "name": user.distributor_name,
                "type": "Distributor",
            },
        }
    )


@router.post("/files/upload")
async def upload_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    files: Annotated[list[UploadFile], File(...)],
) -> dict:
    if not files:
        raise BusinessValidationError("At least one image file is required.")
    for file in files:
        if not (file.content_type or "").startswith("image/"):
            raise BusinessValidationError("Only image/* files are accepted.")
        if file.size is not None and file.size > MAX_IMAGE_SIZE_BYTES:
            raise BusinessValidationError("Each image must be 10MB or smaller.")

    saved = []
    for file in files:
        db_file = await save_uploaded_file(db, user.id, file)
        saved.append(db_file)
        await record_audit_event(
            db,
            user_id=user.id,
            action="openapi.file.upload",
            target_type="uploaded_file",
            target_id=db_file.id,
            metadata={
                "channel": "openapi",
                "filename": db_file.filename,
                "file_size": db_file.file_size,
            },
        )
    await db.commit()
    return ok(
        {
            "files": [
                {
                    "fileId": str(file.id),
                    "filename": file.filename,
                    "mimeType": file.mime_type,
                    "fileSize": file.file_size,
                }
                for file in saved
            ]
        }
    )


@router.post("/detections", status_code=202)
async def create_detection_endpoint(
    payload: OpenApiDetectionCreateRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", max_length=255)
    ] = None,
) -> dict:
    request_hash = _request_hash(payload)
    # Ensure a newly-created integration account has a durable current profile
    # before reserving an idempotency key in the request transaction.
    if payload.threshold_config is None:
        await current_threshold(db, user.id)
    if idempotency_key:
        existing = await get_openapi_idempotency_key(
            db, user_id=user.id, idempotency_key=idempotency_key
        )
        if existing and existing.expires_at <= datetime.now(UTC):
            await db.delete(existing)
            await db.flush()
            existing = None
        if existing:
            if existing.request_hash != request_hash:
                await record_audit_event(
                    db,
                    user_id=user.id,
                    action="openapi.detection.idempotency_conflict",
                    status="failure",
                    metadata={
                        "channel": "openapi",
                        "idempotency_key": idempotency_key,
                    },
                )
                await db.commit()
                raise ConflictError("Idempotency-Key was already used for a different request.")
            if existing.detect_record_id is None:
                raise ConflictError("The original idempotent request is still being created; retry shortly.")
            record = await get_record(
                db, user.id, existing.detect_record_id, source="openapi"
            )
            if record is None:
                raise NotFoundError("Idempotent detection record was not found.")
            return ok(_detection_create_data(record))

    serial_no = await _resolve_serial_no(payload)
    idempotency_entry = None
    if idempotency_key:
        idempotency_entry = await claim_openapi_idempotency_key(
            db,
            user_id=user.id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            expires_at=datetime.now(UTC) + IDEMPOTENCY_TTL,
        )
        if idempotency_entry is None:
            existing = await get_openapi_idempotency_key(
                db, user_id=user.id, idempotency_key=idempotency_key
            )
            if existing is None or existing.detect_record_id is None:
                raise ConflictError("The original idempotent request is still being created; retry shortly.")
            if existing.request_hash != request_hash:
                raise ConflictError("Idempotency-Key was already used for a different request.")
            record = await get_record(
                db, user.id, existing.detect_record_id, source="openapi"
            )
            if record is None:
                raise NotFoundError("Idempotent detection record was not found.")
            return ok(_detection_create_data(record))

    record = await create_detection(
        db,
        user_id=user.id,
        serial_no=serial_no,
        fault_category=payload.fault_category,
        file_ids=payload.file_ids,
        threshold_config=payload.threshold_config,
        source="openapi",
        run_immediately=False,
    )
    if idempotency_entry is not None:
        idempotency_entry.detect_record_id = record.id
    await record_audit_event(
        db,
        user_id=user.id,
        action="openapi.detection.create",
        target_type="detect_record",
        target_id=record.id,
        metadata={
            "channel": "openapi",
            "serial_no": record.serial_no,
            "fault_category": record.fault_category,
            "file_count": len(payload.file_ids),
        },
    )
    await db.commit()
    background_tasks.add_task(process_detection_record, record.id, payload.file_ids)
    return ok(_detection_create_data(record))


@router.get("/detections/{detection_id}")
async def get_detection_endpoint(
    detection_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    record = await get_record(db, user.id, detection_id, source="openapi")
    if record is None:
        raise NotFoundError("OpenAPI detection was not found.")
    await record_audit_event(
        db,
        user_id=user.id,
        action="openapi.detection.read",
        target_type="detect_record",
        target_id=record.id,
        metadata={"channel": "openapi"},
    )
    await db.commit()
    return ok(_detection_data(record))


@router.get("/files/{file_id}")
async def download_endpoint(
    file_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    db_file = await get_uploaded_file(db, user.id, file_id)
    if db_file is None:
        raise NotFoundError("Uploaded file was not found.")
    await record_audit_event(
        db,
        user_id=user.id,
        action="openapi.file.read",
        target_type="uploaded_file",
        target_id=db_file.id,
        metadata={"channel": "openapi"},
    )
    await db.commit()
    download_url = await get_stored_file_download_url(db_file)
    if download_url:
        return RedirectResponse(download_url)
    if not await stored_file_exists(db_file):
        raise NotFoundError("Physical file was not found on disk.")
    return FileResponse(
        path=db_file.object_key,
        filename=db_file.filename,
        media_type=db_file.mime_type,
    )


@router.get("/thresholds/current")
async def current_threshold_endpoint(
    _: Annotated[User, Depends(get_current_user)],
) -> dict:
    # This is a public copy-and-edit template, intentionally independent of
    # the authenticated distributor's saved Web threshold profile.
    return ok({"thresholdConfig": openapi_threshold_template()})
