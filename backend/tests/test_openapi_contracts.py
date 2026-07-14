from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.api.openapi import (
    _detection_create_data,
    _detection_data,
    _request_hash,
    _resolve_serial_no,
)
from src.core.exceptions import BusinessValidationError
from src.main import app
from src.schemas.domain import OpenApiDetectionCreateRequest
from src.rules.thresholds import default_thresholds, openapi_threshold_template


def test_openapi_paths_are_isolated_from_web_api() -> None:
    paths = app.openapi()["paths"]
    assert {
        "/openapi/v1/auth/login",
        "/openapi/v1/files/upload",
        "/openapi/v1/files/{file_id}",
        "/openapi/v1/detections",
        "/openapi/v1/detections/{detection_id}",
        "/openapi/v1/thresholds/current",
    }.issubset(paths)
    assert "/api/v1/detections" in paths


def test_openapi_threshold_template_is_default_and_copyable() -> None:
    template = openapi_threshold_template()

    assert set(template) == {"rules"}
    assert template["rules"]["inaccuracy"]["jump"] == {
        "deltaMmol": 3.0,
        "consecutive": 3,
    }
    deviation = template["rules"]["inaccuracy"]["deviation"]
    assert "within48hPairCount" not in deviation
    assert "after48hPairCount" not in deviation
    assert "photoCount" not in template["rules"]["applicationFailure"]

    payload = OpenApiDetectionCreateRequest.model_validate(
        {
            "serialNo": "SN-1",
            "faultCategory": "Data accuracy",
            "thresholdConfig": template,
        }
    )
    assert payload.threshold_config is not None


def test_openapi_request_requires_one_device_identifier_and_normalizes_it() -> None:
    by_sn = OpenApiDetectionCreateRequest.model_validate(
        {"serialNo": " sn-1 ", "faultCategory": "Sensor Abnormal"}
    )
    assert by_sn.serial_no == "SN-1"

    by_name = OpenApiDetectionCreateRequest.model_validate(
        {"deviceName": " aa123 ", "faultCategory": "Sensor Abnormal"}
    )
    assert by_name.device_name == "AA123"

    with pytest.raises(ValueError, match="serialNo or deviceName"):
        OpenApiDetectionCreateRequest.model_validate(
            {"faultCategory": "Sensor Abnormal"}
        )

    valid_config = OpenApiDetectionCreateRequest.model_validate(
        {
            "serialNo": "SN-1",
            "faultCategory": "Sensor Abnormal",
            "thresholdConfig": default_thresholds(),
        }
    )
    assert valid_config.threshold_config is not None

    with pytest.raises(ValueError, match="Invalid thresholdConfig"):
        OpenApiDetectionCreateRequest.model_validate(
            {
                "serialNo": "SN-1",
                "faultCategory": "Sensor Abnormal",
                "thresholdConfig": {"rules": {"applicationFailure": {}}},
            }
        )

    unsupported_count_config = default_thresholds()
    unsupported_count_config["rules"]["inaccuracy"]["deviation"]["within48hPairCount"] = 3
    with pytest.raises(ValueError, match="system-managed and fixed at 2"):
        OpenApiDetectionCreateRequest.model_validate(
            {
                "serialNo": "SN-1",
                "faultCategory": "Sensor Abnormal",
                "thresholdConfig": unsupported_count_config,
            }
        )


@pytest.mark.asyncio
async def test_openapi_device_name_requires_exactly_one_match(monkeypatch: pytest.MonkeyPatch) -> None:
    class MultipleMatchesClient:
        async def get_device(self, _: str):
            return [{"sn": "SN-2"}, {"sn": "SN-1"}]

    monkeypatch.setattr("src.api.openapi.get_cgm_client", lambda: MultipleMatchesClient())
    payload = OpenApiDetectionCreateRequest.model_validate(
        {"deviceName": "AA123", "faultCategory": "Sensor Abnormal"}
    )

    with pytest.raises(BusinessValidationError) as exc:
        await _resolve_serial_no(payload)

    assert exc.value.data == {"candidateSerialNos": ["SN-1", "SN-2"]}


@pytest.mark.asyncio
async def test_openapi_device_name_preserves_upstream_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnavailableClient:
        async def get_device(self, _: str):
            raise RuntimeError("overseas API timed out")

    monkeypatch.setattr("src.api.openapi.get_cgm_client", lambda: UnavailableClient())
    payload = OpenApiDetectionCreateRequest.model_validate(
        {"deviceName": "AA123", "faultCategory": "Sensor Abnormal"}
    )

    with pytest.raises(RuntimeError, match="timed out"):
        await _resolve_serial_no(payload)


def test_openapi_idempotency_hash_is_stable_for_the_same_request() -> None:
    payload = OpenApiDetectionCreateRequest.model_validate(
        {
            "serialNo": "SN-1",
            "faultCategory": "Sensor Abnormal",
            "fileIds": ["file-1"],
        }
    )
    assert _request_hash(payload) == _request_hash(payload)


def test_openapi_result_is_compact_and_uses_camel_case() -> None:
    now = datetime.now(UTC)
    record = SimpleNamespace(
        id=42,
        serial_no="SN-1",
        fault_category="Data accuracy",
        status="completed",
        verdict="Under Review",
        fault_subtype="Insufficient Images",
        issue_detected="no issue",
        reasons="At least 2 images are required.",
        threshold_id=3,
        threshold_snapshot={
            "version": 3,
            "rules": {
                "inaccuracy": {
                    "deviation": {
                        "within48hDeviationMmol": 7.0,
                        "within48hPairCount": 2,
                        "within48hQualifiedPairCount": 2,
                        "after48hDeviationRangePct": 20,
                        "after48hPairCount": 2,
                        "after48hQualifiedPairCount": 2,
                    }
                },
                "applicationFailure": {
                    "photoCount": 2,
                    "afterSalesScore": 7.0,
                    "manualReviewScore": 5.0,
                },
            },
        },
        evidence={
            "matched_rules": [],
            "glucose_series_url": "/api/v1/files/1",
            "files_metadata": [{"public_url": "/api/v1/files/2"}],
        },
        error_message=None,
        created_at=now,
        completed_at=now,
    )

    result = _detection_data(record)

    assert result["detectionId"] == "42"
    assert result["serialNo"] == "SN-1"
    assert "deviceName" not in result
    assert result["issueDetected"] is False
    deviation = result["thresholdConfig"]["rules"]["inaccuracy"]["deviation"]
    assert "within48hPairCount" not in deviation
    assert "within48hQualifiedPairCount" not in deviation
    assert "after48hPairCount" not in deviation
    assert "after48hQualifiedPairCount" not in deviation
    assert "photoCount" not in result["thresholdConfig"]["rules"]["applicationFailure"]
    assert result["evidence"]["matchedRules"] == []
    assert result["evidence"]["glucoseSeriesUrl"] == "/openapi/v1/files/1"
    assert "filesMetadata" not in result["evidence"]


def test_openapi_application_failure_evidence_hides_image_metadata() -> None:
    now = datetime.now(UTC)
    record = SimpleNamespace(
        id=43,
        serial_no="SN-APP",
        fault_category="Application failure",
        status="completed",
        verdict="Replacement Eligible",
        fault_subtype="Adhesive detaching",
        issue_detected="Issue Detected",
        reasons="Application failure evidence matched.",
        threshold_id=3,
        threshold_snapshot={
            "version": 3,
            "rules": {
                "applicationFailure": {
                    "photoCount": 2,
                    "afterSalesScore": 7.0,
                    "manualReviewScore": 5.0,
                }
            },
        },
        evidence={
            "matched_rules": ["application_failure.adhesive_detached"],
            "files_metadata": [
                {
                    "file_id": "1001",
                    "filename": "photo-1.jpg",
                    "public_url": "/api/v1/files/1001",
                    "file_size": 123456,
                }
            ],
            "file_ids": ["1001"],
            "implantation_scanner": [
                {
                    "image": "/tmp/photo-1.jpg",
                    "scenario_results": [{"large": "internal payload"}],
                }
            ],
            "vision": {
                "model_name": "internal-model",
                "prompt_version": "internal-prompt",
                "source": "vlm",
                "score": 8.5,
                "final_scenario": "Adhesive detaching",
                "final_confidence": 0.91,
                "scenarios": [{"verbose": "large internal model output"}],
                "features": {
                    "is_cgm_device_present": True,
                    "is_reproduced_photo": False,
                    "needle_exposed": False,
                    "adhesive_detached": True,
                    "implanter_damage": False,
                },
            },
        },
        error_message=None,
        created_at=now,
        completed_at=now,
    )

    result = _detection_data(record)
    evidence = result["evidence"]

    assert evidence["matchedRules"] == ["application_failure.adhesive_detached"]
    assert evidence["vision"] == {
        "score": 8.5,
        "finalScenario": "Adhesive detaching",
        "finalConfidence": 0.91,
        "features": {
            "isCgmDevicePresent": True,
            "isReproducedPhoto": False,
            "needleExposed": False,
            "adhesiveDetached": True,
            "implanterDamage": False,
        },
    }
    assert "filesMetadata" not in evidence
    assert "fileIds" not in evidence
    assert "implantationScanner" not in evidence
    assert "scenarios" not in evidence["vision"]
    assert "modelName" not in evidence["vision"]
    assert "promptVersion" not in evidence["vision"]
    assert "source" not in evidence["vision"]


def test_openapi_create_result_is_a_submission_receipt() -> None:
    now = datetime.now(UTC)
    record = SimpleNamespace(
        id=42,
        serial_no="SN-1",
        fault_category="Data accuracy",
        created_at=now,
    )

    result = _detection_create_data(record)

    assert result == {
        "detectionId": "42",
        "serialNo": "SN-1",
        "faultCategory": "Data accuracy",
        "createdAt": now.isoformat(),
    }
