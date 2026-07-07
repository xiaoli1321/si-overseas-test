from datetime import UTC, datetime, timedelta

from src.rules.presentation import build_verdict_presentation


def _series(values: list[float]) -> dict:
    now = datetime(2026, 6, 1, tzinfo=UTC)
    return {
        "points": [
            {"timestamp": now + timedelta(minutes=30 * index), "glucose": value, "unit": "mmol/L"}
            for index, value in enumerate(values)
        ]
    }


def _config() -> dict:
    return {
        "enabled": True,
        "template_version": "unit-template-v1",
        "templates": {
            "data_accuracy.first_pass.persistent_low": {
                "badge": "WARRANTY ELIGIBLE",
                "title": "Persistent Low Glucose Detected",
                "summary": "summary",
                "whatWeFound": "Low {low_hours} h below {below_mmol} mmol/L, 24h peak {peak_24h_mmol} mmol/L",
                "whyThisResult": "Low <= {below_mmol} for {min_hours}h",
                "possibleCauses": "cause",
                "supportingMaterials": "Not displayed",
                "guidance": {"afterSalesStatus": "You can continue to after-sales from this result."},
            },
            "fall_off.not_detected": {
                "badge": "NOT WARRANTY ELIGIBLE",
                "title": "Fall off not detected",
                "summary": "summary",
                "whatWeFound": "State {device_status}. Last Upload {last_upload}",
                "whyThisResult": "Current state is {device_status}",
                "possibleCauses": "",
                "supportingMaterials": "Not displayed",
                "guidance": {"text": "manual judgment"},
            },
        },
    }


def _threshold_snapshot() -> dict:
    return {
        "version": 1,
        "rules": {
            "inaccuracy": {
                "lowPersist": {"belowMmol": 2.8, "minHours": 4, "max24hMmol": 7.8},
                "noFluctuation": {"floorMmol": 4.5, "minHours": 8, "maxSwingMmol": 1.0},
                "jump": {"deltaMmol": 3.0, "consecutive": 3},
                "deviation": {"within48hDeviationMmol": 7.0, "within48hPairCount": 2},
            }
        },
    }


def test_verdict_presentation_should_render_configured_template_variables() -> None:
    presentation = build_verdict_presentation(
        fault_category="Data accuracy",
        fault_subtype="Persistently Low",
        verdict="Replacement Eligible",
        issue_detected="Issue Detected",
        evidence={"glucose_series": _series([2.7] * 10 + [7.4])},
        threshold_snapshot=_threshold_snapshot(),
        settings_config=_config(),
    )

    assert presentation is not None
    assert presentation["templateVersion"] == "unit-template-v1"
    assert presentation["scenarioKey"] == "data_accuracy.first_pass.persistent_low"
    assert presentation["title"] == "Persistent Low Glucose Detected"
    assert "below 2.8 mmol/L" in presentation["whatWeFound"]
    assert "24h peak 7.4 mmol/L" in presentation["whatWeFound"]


def test_verdict_presentation_should_use_fallback_for_missing_template() -> None:
    presentation = build_verdict_presentation(
        fault_category="Sensor Abnormal",
        fault_subtype="No Abnormal",
        verdict="Not Eligible",
        issue_detected="no issue",
        evidence={},
        threshold_snapshot=_threshold_snapshot(),
        settings_config=_config(),
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "sensor_abnormal.no_abnormality"
    assert presentation["title"] == "No Abnormal"
    assert "template is missing" in presentation["whyThisResult"]


def test_verdict_presentation_should_render_device_status_for_fall_off() -> None:
    presentation = build_verdict_presentation(
        fault_category="Sensor falling off",
        fault_subtype="No Fall Off",
        verdict="Not Eligible",
        issue_detected="no issue",
        evidence={"device": {"status": "In use", "last_upload": "2026-03-24 08:30"}},
        threshold_snapshot=_threshold_snapshot(),
        settings_config=_config(),
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "fall_off.not_detected"
    assert presentation["whatWeFound"] == "State In use. Last Upload 2026-03-24 08:30"


def test_verdict_presentation_should_not_render_processing_record() -> None:
    presentation = build_verdict_presentation(
        fault_category="Sensor falling off",
        fault_subtype=None,
        verdict=None,
        issue_detected=None,
        evidence={},
        threshold_snapshot=_threshold_snapshot(),
        settings_config=_config(),
    )

    assert presentation is None


def test_verdict_presentation_should_render_abnormal_time() -> None:
    config_with_abnormal = _config()
    config_with_abnormal["templates"]["sensor_abnormal.gs1_after_warmup"] = {
        "badge": "WARRANTY ELIGIBLE",
        "title": "Abnormal after Warm-up",
        "summary": "summary",
        "whatWeFound": "Abnormality occurred at {abnormal_time}.",
        "whyThisResult": "rule met",
        "possibleCauses": "cause",
        "supportingMaterials": "Not displayed",
        "guidance": {"afterSalesStatus": "eligible"},
    }

    presentation = build_verdict_presentation(
        fault_category="Sensor Abnormal",
        fault_subtype="Replace Device - Use",
        verdict="Replacement Eligible",
        issue_detected="Issue Detected",
        evidence={
            "device": {"timeZone": "+08:00"},
            "alarm": {"latest_sensor_alert": "2026-03-24T00:30:00+00:00"}
        },
        threshold_snapshot=_threshold_snapshot(),
        settings_config=config_with_abnormal,
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "sensor_abnormal.gs1_after_warmup"
    # UTC 00:30 + 08:00 timezone = 08:30
    assert presentation["whatWeFound"] == "Abnormality occurred at 2026-03-24 08:30."


def test_verdict_presentation_should_render_initialization_abnormal_time() -> None:
    config_with_abnormal = _config()
    config_with_abnormal["templates"]["sensor_abnormal.gs1_initialization"] = {
        "badge": "WARRANTY ELIGIBLE",
        "title": "Initialization abnormality",
        "summary": "summary",
        "whatWeFound": "Initialization abnormality time is {abnormal_time}",
        "whyThisResult": "rule met",
        "possibleCauses": "cause",
        "supportingMaterials": "Not displayed",
        "guidance": {"afterSalesStatus": "eligible"},
    }

    presentation = build_verdict_presentation(
        fault_category="Sensor Abnormal",
        fault_subtype="Initialization Abnormal",
        verdict="Replacement Eligible",
        issue_detected="Issue Detected",
        evidence={
            "device": {"timeZone": "UTC"},
            "alarm": {"latest_sensor_alert": "2026-03-24T08:30:00Z"}
        },
        threshold_snapshot=_threshold_snapshot(),
        settings_config=config_with_abnormal,
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "sensor_abnormal.gs1_initialization"
    assert presentation["whatWeFound"] == "Initialization abnormality time is 2026-03-24 08:30"


def test_verdict_presentation_should_render_waiting_recovery() -> None:
    config_with_abnormal = _config()
    config_with_abnormal["templates"]["sensor_abnormal.waiting_recovery"] = {
        "badge": "PENDING REVIEW",
        "title": "Temporary sensor abnormality",
        "summary": "summary",
        "whatWeFound": "Abnormality occurred at {abnormal_time}.",
        "whyThisResult": "rule met",
        "possibleCauses": "cause",
        "supportingMaterials": "Not displayed",
        "guidance": {"afterSalesStatus": "pending"},
    }

    presentation = build_verdict_presentation(
        fault_category="Sensor Abnormal",
        fault_subtype="Waiting Recovery",
        verdict="Not Eligible",
        issue_detected="no issue",
        evidence={
            "device": {"timeZone": "UTC"},
            "alarm": {"latest_sensor_alert": "2026-03-24T08:30:00Z"}
        },
        threshold_snapshot=_threshold_snapshot(),
        settings_config=config_with_abnormal,
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "sensor_abnormal.waiting_recovery"
    assert presentation["whatWeFound"] == "Abnormality occurred at 2026-03-24 08:30."


def test_verdict_presentation_should_render_low_recovery_possibility() -> None:
    config_with_abnormal = _config()
    config_with_abnormal["templates"]["sensor_abnormal.low_recovery_possibility"] = {
        "badge": "WARRANTY ELIGIBLE",
        "title": "Abnormal after Warm-up",
        "summary": "summary",
        "whatWeFound": "Abnormality occurred at {abnormal_time}.",
        "whyThisResult": "rule met",
        "possibleCauses": "cause",
        "supportingMaterials": "Not displayed",
        "guidance": {"afterSalesStatus": "eligible"},
    }

    presentation = build_verdict_presentation(
        fault_category="Sensor Abnormal",
        fault_subtype="Low Recovery Possibility",
        verdict="Replacement Eligible",
        issue_detected="Issue Detected",
        evidence={
            "device": {"timeZone": "UTC"},
            "alarm": {"latest_sensor_alert": "2026-03-24T08:30:00Z"}
        },
        threshold_snapshot=_threshold_snapshot(),
        settings_config=config_with_abnormal,
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "sensor_abnormal.low_recovery_possibility"
    assert presentation["whatWeFound"] == "Abnormality occurred at 2026-03-24 08:30."


def test_verdict_presentation_should_render_application_failure() -> None:
    config_with_app = _config()
    config_with_app["templates"]["application_failure.guide_needle_retention"] = {
        "badge": "WARRANTY ELIGIBLE",
        "title": "Application failure {subtype} detected",
        "summary": "summary",
        "whatWeFound": "VLM identified {subtype} from {photo_count} photos. Detail: {vlm_reason}. Score {score} / 10",
        "whyThisResult": "Needs >= {app_photo_count} photos, score > {app_after_sales_score}",
        "possibleCauses": "cause",
        "supportingMaterials": "Not displayed",
        "guidance": {"afterSalesStatus": "eligible"},
    }

    presentation = build_verdict_presentation(
        fault_category="Application failure",
        fault_subtype="Guiding needle retention",
        verdict="Replacement Eligible",
        issue_detected="Issue Detected",
        evidence={
            "file_ids": ["photo-1", "photo-2"],
            "vision": {
                "score": 9.0,
                "final_scenario": "Guiding needle retention",
                "scenarios": [
                    {"scenario": "Guiding needle retention", "matched": True, "reason": "Needle did not retract"},
                ]
            }
        },
        threshold_snapshot={
            "rules": {
                "applicationFailure": {
                    "photoCount": 2,
                    "afterSalesScore": 7.0,
                    "manualReviewScore": 5.0,
                }
            }
        },
        settings_config=config_with_app,
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "application_failure.guide_needle_retention"
    assert presentation["title"] == "Application failure Guiding needle retention detected"
    assert presentation["whatWeFound"] == "VLM identified Guiding needle retention from 2 photos. Detail: Needle did not retract. Score 9 / 10"
    assert presentation["whyThisResult"] == "Needs >= 2 photos, score > 7"


def test_verdict_presentation_should_fallback_to_data_accuracy_details_when_glucose_series_is_missing() -> None:
    presentation = build_verdict_presentation(
        fault_category="Data accuracy",
        fault_subtype="Persistently Low",
        verdict="Replacement Eligible",
        issue_detected="Issue Detected",
        evidence={
            "data_accuracy_details": {
                "persistently_low": {
                    "max_glucose_24h": 7.4,
                    "actual_low_hours": 4.5,
                    "trigger_segments": []
                }
            }
        },
        threshold_snapshot=_threshold_snapshot(),
        settings_config=_config(),
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "data_accuracy.first_pass.persistent_low"
    assert presentation["title"] == "Persistent Low Glucose Detected"
    assert "below 2.8 mmol/L" in presentation["whatWeFound"]
    assert "24h peak 7.4 mmol/L" in presentation["whatWeFound"]
    assert "Low 4.5 h" in presentation["whatWeFound"]


def test_verdict_presentation_fallback_abnormal_started_at() -> None:
    config_with_abnormal = _config()
    config_with_abnormal["templates"]["sensor_abnormal.gs1_initialization"] = {
        "badge": "WARRANTY ELIGIBLE",
        "title": "Initialization abnormality",
        "summary": "summary",
        "whatWeFound": "Initialization abnormality time is {abnormal_time}",
        "whyThisResult": "rule met",
        "possibleCauses": "cause",
        "supportingMaterials": "Not displayed",
        "guidance": {"afterSalesStatus": "eligible"},
    }

    presentation = build_verdict_presentation(
        fault_category="Sensor Abnormal",
        fault_subtype="Initialization Abnormal",
        verdict="Replacement Eligible",
        issue_detected="Issue Detected",
        evidence={
            "device": {"timeZone": "UTC"},
            "alarm": {"abnormal_started_at": "2026-03-24T08:30:00Z"}
        },
        threshold_snapshot=_threshold_snapshot(),
        settings_config=config_with_abnormal,
    )

    assert presentation is not None
    assert presentation["scenarioKey"] == "sensor_abnormal.gs1_initialization"
    assert presentation["whatWeFound"] == "Initialization abnormality time is 2026-03-24 08:30"


