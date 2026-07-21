from datetime import datetime
from typing import Any

from src.models.tables import BatchTask, DetectRecord, Threshold, User
from src.rules.presentation import build_verdict_presentation
from src.rules.thresholds import frontend_threshold_profile


def device_to_frontend(device: dict[str, Any]) -> dict[str, Any]:
    """将 OverseasCGMClient 返回的 adapted device dict 转换为前端所需格式"""
    return {
        "sn": device.get("sn", ""),
        "type": device.get("type", device.get("device_type", "GS1")),
        "status": device.get("status", "wearing"),
        "activatedAt": device.get("activatedAt", ""),
        "wearDays": device.get("wearDays", 0),
        "wearHours": device.get("wearHours", 0),
        "lastDataAt": device.get("lastDataAt", ""),
        "hasServiceCard": device.get("hasServiceCard"),
        "fault": device.get("fault"),
    }


def threshold_to_frontend(threshold: Threshold) -> dict[str, Any]:
    profile = frontend_threshold_profile(
        threshold.config_json,
        version=threshold.version,
        saved_at=threshold.created_at.isoformat() if threshold.created_at else None,
    )
    profile["remark"] = threshold.remark
    profile["restoredFrom"] = threshold.restored_from
    profile["isHidden"] = threshold.is_deleted
    return profile


def user_to_frontend(user: User) -> dict[str, Any]:
    distributor_name = user.distributor_name or "Unassigned dealer"
    return {
        "email": user.email,
        "displayName": "Chris Test"
        if user.email == "christest@sibionics.com"
        else distributor_name,
        "role": user.role if user.role in {"manager", "dealer"} else "dealer",
        "dealerId": "chris-overseas-dealer",
        "dealerName": distributor_name,
        "organizationName": distributor_name,
        "organizationType": "Distributor",
        "region": "A Region",
    }


def managed_user_to_frontend(user: User) -> dict[str, Any]:
    """Account row for the manager's account-management center."""
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "dealerName": user.distributor_name or "—",
        "createdAt": user.created_at.isoformat() if user.created_at else None,
    }


def record_to_frontend(
    record: DetectRecord, user: User | None = None
) -> dict[str, Any]:
    adoption = {"adopted": "Yes", "rejected": "No", "none": "Not recorded"}.get(
        record.feedback_status, "Not recorded"
    )
    profile = record.threshold_snapshot or {"version": 1, "savedAt": None, "rules": {}}
    threshold_profile = (
        profile
        if "rules" in profile
        else frontend_threshold_profile(profile, record.threshold_id or 1, None)
    )
    account = (
        user_to_frontend(user)
        if user
        else {
            "email": "christest@sibionics.com",
            "displayName": "Chris Test",
            "dealerId": "chris-overseas-dealer",
            "dealerName": "Chris Overseas Dealer",
            "organizationName": "Chris Overseas Dealer",
            "organizationType": "Distributor",
            "region": "A Region",
        }
    )
    after_sales = record.verdict or "Under Review"
    presentation = build_verdict_presentation(
        fault_category=record.fault_category,
        fault_subtype=record.fault_subtype,
        verdict=record.verdict,
        issue_detected=record.issue_detected,
        evidence=record.evidence,
        threshold_snapshot=threshold_profile,
    )
    return {
        "id": str(record.id),
        "sn": record.serial_no,
        "email": account["email"],
        "initiatorEmail": account["email"],
        "initiatorName": account["displayName"],
        "dealerId": account["dealerId"],
        "dealerName": account["dealerName"],
        "organizationName": account["organizationName"],
        "organizationType": account["organizationType"],
        "region": account["region"],
        "deviceType": record.device_type,
        "faultCategory": record.fault_category,
        "faultSubtype": record.fault_subtype or "",
        "conclusion": "Issue Detected"
        if record.issue_detected == "Issue Detected"
        else "No Issue",
        "afterSales": after_sales,
        "timestamp": record.created_at.isoformat(),
        "thresholdProfileVersion": threshold_profile.get(
            "version", record.threshold_id or 1
        ),
        "thresholdSnapshot": threshold_profile,
        "reasonSummary": record.reasons or record.error_message or "",
        "verdictAdoption": adoption,
        "verdictRejectionReason": record.reject_reason or "",
        "adoptedAt": record.adopted_at.isoformat() if record.adopted_at else None,
        "status": "complete" if record.status == "completed" else record.status,
        "errorMessage": record.error_message,
        "evidence": record.evidence,
        "presentation": presentation,
        "batchId": f"MULTI-{record.batch_task_id}" if record.batch_task_id else None,
    }


def batch_to_frontend(task: BatchTask, user: User | None = None) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "batchId": f"MULTI-{task.id}",
        "faultCategory": task.fault_category,
        "totalCount": task.total_count,
        "successCount": task.success_count,
        "failedCount": task.failed_count,
        "status": "complete" if task.status == "completed" else task.status,
        "createdAt": task.created_at.isoformat(),
        "updatedAt": task.updated_at.isoformat(),
        "records": [record_to_frontend(record, user) for record in task.records],
        "sessions": [
            {
                "id": str(record.id),
                "sn": record.serial_no,
                "faultCategory": record.fault_category,
                "status": "complete"
                if record.status in {"completed", "failed"}
                else "processing",
                "startedAt": record.started_at.isoformat()
                if record.started_at
                else task.created_at.isoformat(),
                "updatedAt": record.updated_at.isoformat(),
                "recordId": str(record.id)
                if record.status in {"completed", "failed"}
                else None,
                "source": "multi",
                "batchId": f"MULTI-{task.id}",
                "stepLabel": "Complete"
                if record.status == "completed"
                else "Failed"
                if record.status == "failed"
                else record.status.title(),
                "progress": 100 if record.status in {"completed", "failed"} else 50,
            }
            for record in task.records
        ],
    }


def record_to_list_item(
    record: DetectRecord, submitter: User | None = None
) -> dict[str, Any]:
    """轻量级列表渲染，不包含 evidence/presentation/thresholdSnapshot 等重字段。

    ``submitter`` 为该记录的真实提交账号（manager 跨账号查看时用于区分国家/账号）。
    """
    adoption = {"adopted": "Yes", "rejected": "No", "none": "Not recorded"}.get(
        record.feedback_status, "Not recorded"
    )
    initiator_email = submitter.username if submitter else None
    dealer_name = (submitter.distributor_name if submitter else None) or "—"
    return {
        "id": str(record.id),
        "sn": record.serial_no,
        "deviceType": record.device_type,
        "faultCategory": record.fault_category,
        "faultSubtype": record.fault_subtype or "",
        "conclusion": "Issue Detected"
        if record.issue_detected == "Issue Detected"
        else "No Issue",
        "afterSales": record.verdict or "Under Review",
        "verdictAdoption": adoption,
        "verdictRejectionReason": record.reject_reason or "",
        "timestamp": record.created_at.isoformat(),
        "reasonSummary": record.reasons or record.error_message or "",
        "status": "complete" if record.status == "completed" else record.status,
        "errorMessage": record.error_message,
        "batchId": f"MULTI-{record.batch_task_id}" if record.batch_task_id else None,
        "accountId": str(record.user_id),
        "initiatorEmail": initiator_email or "—",
        "dealerName": dealer_name,
    }


def stats_to_frontend(stats: dict[str, int]) -> dict[str, int]:
    return {
        "total": stats["total"],
        "allowed": stats["allowed"],
        "notAllowed": stats["not_allowed"],
        "pending": stats["pending"],
    }
