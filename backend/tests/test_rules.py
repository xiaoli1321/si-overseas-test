from datetime import UTC, datetime, timedelta

from src.rules.engine import run_rules
from src.rules.thresholds import default_thresholds, to_rule_config


def _series(values: list[float]) -> dict:
    now = datetime(2026, 6, 1, tzinfo=UTC)
    return {
        "serial_no": "SN1",
        "points": [
            {"timestamp": now + timedelta(minutes=30 * index), "glucose": value, "unit": "mmol/L", "alarm_status": 0}
            for index, value in enumerate(values)
        ],
    }


def _series_from(start: datetime, values: list[float], *, minutes: int = 30, timezone: str = "UTC") -> dict:
    return {
        "serial_no": "SN1",
        "timezone": timezone,
        "points": [
            {
                "timestamp": start + timedelta(minutes=minutes * index),
                "glucose": value,
                "unit": "mmol/L",
                "alarm_status": 0,
            }
            for index, value in enumerate(values)
        ],
    }


def test_system_managed_evidence_counts_override_legacy_thresholds() -> None:
    legacy = {
        "data_accuracy": {
            "data_deviation": {
                "min_pairs": 5,
                "within48hPairCount": 5,
                "within48hQualifiedPairCount": 4,
                "after48hPairCount": 6,
                "after48hQualifiedPairCount": 3,
            }
        },
        "application_failure": {"min_images": 9},
    }

    normalized = to_rule_config(legacy)

    deviation = normalized["data_accuracy"]["data_deviation"]
    assert deviation["min_pairs"] == 2
    assert deviation["within48hPairCount"] == 2
    assert deviation["within48hQualifiedPairCount"] == 2
    assert deviation["after48hPairCount"] == 2
    assert deviation["after48hQualifiedPairCount"] == 2
    assert normalized["application_failure"]["min_images"] == 2


def test_data_accuracy_should_match_persistently_low() -> None:
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=_series([2.7] * 10 + [7.4]),
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "Persistently Low"
    assert "data_accuracy.persistently_low" in result.matched_rules


def test_data_accuracy_should_not_sum_non_continuous_low_segments() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    glucose_series = _series_from(start, [2.7] * 5 + [5.0] + [2.7] * 5)
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=glucose_series,
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"


def test_data_accuracy_should_ignore_high_value_outside_recent_24h() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    old_high = {"timestamp": start, "glucose": 9.0, "unit": "mmol/L", "alarm_status": 0}
    recent_low = _series_from(start + timedelta(hours=25), [2.7] * 9)["points"]
    glucose_series = {"serial_no": "SN1", "timezone": "UTC", "points": [old_high, *recent_low]}
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=glucose_series,
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "Persistently Low"


def test_data_accuracy_should_block_low_rule_when_recent_24h_peak_is_high() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    low_points = _series_from(start, [2.7] * 9)["points"]
    recent_high = {"timestamp": start + timedelta(hours=5), "glucose": 8.0, "unit": "mmol/L", "alarm_status": 0}
    glucose_series = {"serial_no": "SN1", "timezone": "UTC", "points": [*low_points, recent_high]}
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=glucose_series,
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"


def test_data_accuracy_should_not_join_low_segment_across_device_day() -> None:
    start = datetime(2026, 6, 1, 22, 0, tzinfo=UTC)
    glucose_series = _series_from(start, [2.7] * 9, timezone="UTC")
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=glucose_series,
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"


def test_data_accuracy_should_match_no_fluctuation_continuous_segment() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    glucose_series = _series_from(start, [4.0, 4.2] * 9)
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=glucose_series,
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "No Fluctuation"


def test_data_accuracy_should_break_no_fluctuation_on_time_gap() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    first = _series_from(start, [4.0, 4.2] * 5)["points"]
    second = _series_from(start + timedelta(hours=8), [4.0, 4.2] * 5)["points"]
    glucose_series = {"serial_no": "SN1", "timezone": "UTC", "points": [*first, *second]}
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=glucose_series,
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"


def test_data_accuracy_should_match_consecutive_jumps_only() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    glucose_series = _series_from(start, [5.0, 9.0, 5.0, 9.0])
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=glucose_series,
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "Sudden Fluctuation"


def test_data_accuracy_should_not_match_non_consecutive_jump_total() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    glucose_series = _series_from(start, [5.0, 9.0, 9.0, 5.0, 9.0])
    result = run_rules(
        fault_category="Data accuracy",
        device={"serial_no": "SN1"},
        glucose_series=glucose_series,
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"


def test_sensor_falling_off_should_reject_suspected_fall_off() -> None:
    result = run_rules(
        fault_category="Sensor falling off",
        device={"fall_off_status": "suspected_fall_off", "wear_days": 2},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Not Eligible"
    assert result.issue_detected is False
    assert result.fault_subtype == "Suspected Fall Off"


def test_sensor_falling_off_reason_formats_wear_days() -> None:
    result = run_rules(
        fault_category="Sensor falling off",
        device={"fall_off_status": "fallen_off", "wear_days": 10.184166666666666},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "Sudden Fall Off"
    assert result.reasons == [
        "Device is fallen off and wear time 10.2 d is below 14.0 d."
    ]


def test_application_failure_should_require_minimum_images() -> None:
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["one"],
    )

    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Insufficient Images"


def test_application_failure_should_score_exposed_needle_from_vision() -> None:
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["photo-1", "photo-2"],
        vision_analysis={
            "is_cgm_device_present": True,
            "is_reproduced_photo": False,
            "needle_exposed": True,
            "adhesive_detached": False,
            "implanter_damage": False,
            "model_name": "unit-test-vlm",
            "prompt_version": "unit-test",
        },
    )

    assert result.verdict == "Replacement Eligible"
    assert result.issue_detected is True
    assert result.evidence["vision"]["score"] == 10
    assert result.evidence["vision"]["features"]["needle_exposed"] is True


def test_application_failure_should_reject_unrelated_image() -> None:
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["photo-1", "photo-2"],
        vision_analysis={
            "is_cgm_device_present": False,
            "is_reproduced_photo": False,
            "needle_exposed": True,
            "adhesive_detached": True,
            "implanter_damage": True,
            "model_name": "unit-test-vlm",
            "prompt_version": "unit-test",
        },
    )

    assert result.verdict == "Not Eligible"
    assert result.issue_detected is False
    assert result.evidence["vision"]["score"] == 0
    assert "CGM device was not detected" in result.reasons[0]


def test_application_failure_should_reject_reproduced_photo() -> None:
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["photo-1", "photo-2"],
        vision_analysis={
            "is_cgm_device_present": True,
            "is_reproduced_photo": True,
            "needle_exposed": True,
            "adhesive_detached": False,
            "implanter_damage": False,
            "model_name": "unit-test-vlm",
            "prompt_version": "unit-test",
        },
    )

    assert result.verdict == "Not Eligible"
    assert result.issue_detected is False
    assert result.evidence["vision"]["score"] == 0
    assert "screen reproduction" in result.reasons[0]


def test_data_accuracy_data_deviation_without_enough_images() -> None:
    # A device mapped to Data Deviation Detected with an active service card
    device = {
        "serial_no": "P2251212823BFV10",
        "fault": {
            "faultCategory": "Data accuracy",
            "faultSubtype": "Data Deviation Detected",
            "expectedAfterSales": "Replacement Eligible",
            "notes": "Two paired CGM/BGM image groups confirm..."
        }
    }
    # No files uploaded
    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=[],
    )
    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"
    assert result.issue_detected is False

    # 3 files (not enough)
    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["file1", "file2", "file3"],
    )
    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"
    assert result.issue_detected is False


def test_data_accuracy_data_deviation_with_enough_images() -> None:
    device = {
        "serial_no": "P2251212823BFV10",
        "wear_days": 2.0,
        "fault": {
            "faultCategory": "Data accuracy",
            "faultSubtype": "Data Deviation Detected",
            "expectedAfterSales": "Replacement Eligible",
            "notes": "Two paired CGM/BGM image groups confirm..."
        }
    }
    # 4 files (enough)
    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["file1", "file2", "file3", "file4"],
    )
    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "Data Deviation Detected"
    assert result.issue_detected is True
    assert result.evidence["file_ids"] == ["file1", "file2", "file3", "file4"]


def test_data_accuracy_vlm_edge_cases() -> None:
    device = {
        "serial_no": "P2251212823BFV10",
        "wear_days": 2.0,
        "fault": {
            "faultCategory": "Data accuracy",
            "faultSubtype": "Data Deviation Detected",
            "expectedAfterSales": "Replacement Eligible"
        }
    }

    # Case 1: Insufficient deviation (e.g. CGM 5.0, BGM 5.2 -> diff 0.2 / 5.2 = 3.8% < 20%)
    vision_normal = {
        "glucose_readings": [
            {"value": 5.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 5.2, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 6.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 6.1, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False}
        ]
    }
    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["file1", "file2", "file3", "file4"],
        vision_analysis=vision_normal
    )
    assert result.verdict == "Not Eligible"
    assert result.fault_subtype == "Accuracy Within Normal Limits"
    assert "Sensor accuracy is within acceptable limits" in result.reasons[0]

    # Case 2: Fraud/reproduced photo
    vision_fraud = {
        "glucose_readings": [
            {"value": 4.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 6.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": True}, # Fraud
            {"value": 3.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 4.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False}
        ]
    }
    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["file1", "file2", "file3", "file4"],
        vision_analysis=vision_fraud
    )
    assert result.verdict == "Not Eligible"
    assert result.fault_subtype == "Fraud Detected"
    assert "reproduction" in result.reasons[0]

    # Case 3: Invalid/blurry image
    vision_blurry = {
        "glucose_readings": [
            {"value": 4.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": None, "device_type": "BGM", "unit": "mmol/L", "is_valid": False, "is_reproduced": False}, # Blurry
            {"value": 3.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 4.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False}
        ]
    }
    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["file1", "file2", "file3", "file4"],
        vision_analysis=vision_blurry
    )
    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"
    assert "blurry, unreadable or invalid" in result.reasons[0]

    # Case 4: Mismatched device types
    vision_mismatched = {
        "glucose_readings": [
            {"value": 4.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False}, # Wrong device type
            {"value": 6.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 3.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 4.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False}
        ]
    }
    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["file1", "file2", "file3", "file4"],
        vision_analysis=vision_mismatched
    )
    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"
    assert "do not match the expected CGM and BGM device layout" in result.reasons[0]


def test_application_failure_multiturn_replacement_eligible() -> None:
    # Scenario: Highest matched is "Guiding needle retention" with confidence 8.2 (>= 7.0)
    vision_data = {
        "is_cgm_device_present": True,
        "is_reproduced_photo": False,
        "scenarios": [
            {"scenario": "Assembly failed", "matched": True, "confidence": 4.5, "reason": "Weak match"},
            {"scenario": "Guiding needle retention", "matched": True, "confidence": 8.2, "reason": "Strong match"},
            {"scenario": "Exposed Electrodes", "matched": False, "confidence": 0.0, "reason": ""},
            {"scenario": "Adhesive detaching", "matched": False, "confidence": 0.0, "reason": ""},
            {"scenario": "Implanter damage", "matched": False, "confidence": 0.0, "reason": ""},
            {"scenario": "None of the above", "matched": False, "confidence": 0.0, "reason": ""},
        ],
        "model_name": "qwen2.5-vl-7b-instruct",
        "prompt_version": "v2",
        "source": "live_model",
    }
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["photo1", "photo2"],
        vision_analysis=vision_data
    )
    assert result.verdict == "Replacement Eligible"
    assert result.issue_detected is True
    assert result.fault_subtype == "Guiding needle retention"
    assert result.evidence["vision"]["score"] == 8.2
    assert "Guiding needle retention" in result.reasons[2]


def test_application_failure_multiturn_under_review() -> None:
    # Scenario: Highest matched is "Assembly failed" with confidence 5.8 (5.0 <= conf < 7.0)
    vision_data = {
        "is_cgm_device_present": True,
        "is_reproduced_photo": False,
        "scenarios": [
            {"scenario": "Assembly failed", "matched": True, "confidence": 5.8, "reason": "Partial evidence"},
            {"scenario": "Guiding needle retention", "matched": False, "confidence": 0.0, "reason": ""},
            {"scenario": "None of the above", "matched": False, "confidence": 0.0, "reason": ""},
        ],
        "model_name": "qwen2.5-vl-7b-instruct",
        "prompt_version": "v2",
        "source": "live_model",
    }
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["photo1", "photo2"],
        vision_analysis=vision_data
    )
    assert result.verdict == "Under Review"
    assert result.issue_detected is False
    assert result.fault_subtype == "Assembly failed"
    assert result.evidence["vision"]["score"] == 5.8


def test_application_failure_multiturn_not_eligible() -> None:
    # Scenario: Highest matched is "Implanter damage" with confidence 3.2 (< 5.0)
    vision_data = {
        "is_cgm_device_present": True,
        "is_reproduced_photo": False,
        "scenarios": [
            {"scenario": "Implanter damage", "matched": True, "confidence": 3.2, "reason": "Scratches only"},
            {"scenario": "None of the above", "matched": False, "confidence": 0.0, "reason": ""},
        ],
        "model_name": "qwen2.5-vl-7b-instruct",
        "prompt_version": "v2",
        "source": "live_model",
    }
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["photo1", "photo2"],
        vision_analysis=vision_data
    )
    assert result.verdict == "Not Eligible"
    assert result.issue_detected is False
    assert result.fault_subtype == "No Application Failure"
    assert result.evidence["vision"]["score"] == 3.2


def test_application_failure_multiturn_no_scenarios() -> None:
    # Scenario: Scenarios list empty or none matched
    vision_data = {
        "is_cgm_device_present": True,
        "is_reproduced_photo": False,
        "scenarios": [],
        "model_name": "qwen2.5-vl-7b-instruct",
        "prompt_version": "v2",
        "source": "live_model",
    }
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["photo1", "photo2"],
        vision_analysis=vision_data
    )
    assert result.verdict == "Not Eligible"
    assert result.issue_detected is False
    assert result.fault_subtype == "No Application Failure"
    assert result.evidence["vision"]["score"] == 0.0


def test_application_failure_multiturn_ignores_external_score() -> None:
    # Input has external final_scenario and final_confidence (e.g. telling rules engine it's "None of the above" and score 0.0).
    # But scenarios has a matched "Guiding needle retention" with confidence 9.5.
    # The rules engine MUST ignore the external score/verdict and compute it dynamically.
    vision_data = {
        "is_cgm_device_present": True,
        "is_reproduced_photo": False,
        "final_scenario": "None of the above",
        "final_confidence": 0.0,
        "scenarios": [
            {"scenario": "Guiding needle retention", "matched": True, "confidence": 9.5, "reason": "Strong match"},
        ],
        "model_name": "qwen2.5-vl-7b-instruct",
        "prompt_version": "v2",
        "source": "live_model",
    }
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=["photo1", "photo2"],
        vision_analysis=vision_data
    )
    assert result.verdict == "Replacement Eligible"
    assert result.issue_detected is True
    assert result.fault_subtype == "Guiding needle retention"
    assert result.evidence["vision"]["score"] == 9.5


def test_data_accuracy_within_48h_custom_deviation() -> None:
    # Within 48h (wear_days < after48hWearDays)
    # custom thresholds: deviation 6.0 mmol/L; the paired-evidence count is
    # system-managed at two pairs.
    tc = default_thresholds()
    tc["rules"]["inaccuracy"]["deviation"] = {
        "within48hDeviationMmol": 6.0,
        "within48hPairCount": 2,
        "within48hQualifiedPairCount": 2,
        "after48hDeviationRangePct": 20.0,
        "after48hPairCount": 2,
        "after48hQualifiedPairCount": 2,
        "after48hWearDays": 2,
    }

    device = {
        "serial_no": "P2251212823BFV10",
        "wear_days": 1.0,  # Within 48h (1.0 < 2)
    }

    # Case A: 2 pairs, both are qualified (deviating >= 6.0 mmol/L)
    # Pair 1: CGM 10.0, BGM 3.0 (diff 7.0 >= 6.0) -> qualified
    # Pair 2: CGM 9.0, BGM 2.5 (diff 6.5 >= 6.0) -> qualified
    # Pair 3: CGM 5.0, BGM 4.8 (diff 0.2 < 6.0) -> not qualified
    vision_data = {
        "glucose_readings": [
            {"value": 10.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 3.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 9.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 2.5, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
        ]
    }

    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=tc,
        file_ids=["f1", "f2", "f3", "f4"],
        vision_analysis=vision_data
    )
    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "Data Deviation Detected"
    assert "2 of 2 groups of CGM/BGM comparison readings confirm" in result.reasons[0]


def test_data_accuracy_after_48h_custom_deviation() -> None:
    # After 48h (wear_days >= after48hWearDays)
    # custom thresholds: deviation % 25.0, pair_count 2, qualified_count 2, boundary 5.0, absolute 1.0 mmol/L
    tc = default_thresholds()
    tc["rules"]["inaccuracy"]["deviation"] = {
        "within48hDeviationMmol": 7.0,
        "within48hPairCount": 2,
        "within48hQualifiedPairCount": 2,
        "after48hDeviationRangePct": 25.0,
        "after48hDeviationRangeBoundary": 5.0,
        "after48hDeviationMmol": 1.0,
        "after48hPairCount": 2,
        "after48hQualifiedPairCount": 2,
        "after48hWearDays": 2,
    }

    device = {
        "serial_no": "P2251212823BFV10",
        "wear_days": 3.0,  # After 48h (3.0 >= 2)
    }

    # Pair 1: BGM 4.8 (<= 5.0), CGM 6.0. Abs diff = 1.2. (1.2 >= 1.0) -> qualified
    # Pair 2: BGM 8.0 (> 5.0), CGM 11.0. Rel diff = 3.0/8.0 = 37.5% (>= 25.0%) -> qualified
    vision_data = {
        "glucose_readings": [
            {"value": 6.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 4.8, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 11.0, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
            {"value": 8.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
        ]
    }

    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=_series([5.6]),
        alarm={},
        threshold_config=tc,
        file_ids=["f1", "f2", "f3", "f4"],
        vision_analysis=vision_data
    )
    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "Data Deviation Detected"


def test_sensor_abnormal_status_4_warmup_ast_1_should_replace_device_init() -> None:
    device = {
        "sn": "260302GB3U238BAS60",
        "device_status": 4,
        "wear_days": 30 / 1440,
    }
    alarm = {
        "abnormal_duration_minutes": 30,
        "latest_alarm_status": 0,
        "latest_sensor_internal_value": 1,
        "latest_sensor_alert": "2026-05-10T19:21:56.635000+00:00",
    }
    result = run_rules(
        fault_category="Sensor Abnormal",
        device=device,
        glucose_series=_series([5.6]),
        alarm=alarm,
        threshold_config=default_thresholds(),
        file_ids=None,
    )
    assert result.verdict == "Replacement Eligible"
    assert result.issue_detected is True
    assert result.fault_subtype == "Replace Device - Init"
    assert result.evidence["alarm"]["latest_sensor_internal_value"] == 1
    assert "sensor_abnormal.replace_device_-_init" in result.matched_rules


def test_sensor_abnormal_status_4_warmup_ast_0_should_replace_device_init() -> None:
    device = {
        "sn": "260302GB3U238BAS60",
        "device_status": 4,
        "wear_days": 30 / 1440,
    }
    alarm = {
        "abnormal_duration_minutes": 30,
        "latest_alarm_status": 0,
        "latest_sensor_internal_value": 0,
        "latest_sensor_alert": "2026-05-10T19:21:56.635000+00:00",
    }
    result = run_rules(
        fault_category="Sensor Abnormal",
        device=device,
        glucose_series=_series([5.6]),
        alarm=alarm,
        threshold_config=default_thresholds(),
        file_ids=None,
    )
    assert result.verdict == "Replacement Eligible"
    assert result.issue_detected is True
    assert result.fault_subtype == "Replace Device - Init"
    assert result.evidence["alarm"]["latest_sensor_internal_value"] == 0
    assert "sensor_abnormal.replace_device_-_init" in result.matched_rules


def test_sensor_abnormal_status_4_after_warmup_ast_2_should_replace_device_use() -> None:
    device = {
        "sn": "260302GB3U238BAS60",
        "device_status": 4,
        "wear_days": 10.0,
    }
    alarm = {
        "abnormal_duration_minutes": 66662,
        "latest_alarm_status": 2,
        "latest_sensor_internal_value": 2,
        "latest_sensor_alert": "2026-05-10T19:21:56.635000+00:00",
    }
    result = run_rules(
        fault_category="Sensor Abnormal",
        device=device,
        glucose_series=_series([5.6]),
        alarm=alarm,
        threshold_config=default_thresholds(),
        file_ids=None,
    )
    assert result.verdict == "Replacement Eligible"
    assert result.issue_detected is True
    assert result.fault_subtype == "Replace Device - Use"
    assert result.evidence["alarm"]["latest_sensor_internal_value"] == 2
    assert "sensor_abnormal.replace_device_-_use" in result.matched_rules


def test_sensor_abnormal_status_1_ast_2_should_wait_before_recovery_threshold() -> None:
    device = {
        "sn": "260302GB3U238BAS60",
        "device_status": 1,
        "wear_days": 10.0,
    }
    alarm = {
        "abnormal_duration_minutes": 60,
        "latest_alarm_status": 2,
        "latest_sensor_internal_value": 2,
        "latest_sensor_alert": "2026-05-10T19:21:56.635000+00:00",
    }
    result = run_rules(
        fault_category="Sensor Abnormal",
        device=device,
        glucose_series=_series([5.6]),
        alarm=alarm,
        threshold_config=default_thresholds(),
        file_ids=None,
    )
    assert result.verdict == "Not Eligible"
    assert result.issue_detected is False
    assert result.fault_subtype == "Waiting Recovery"


def test_sensor_abnormal_status_1_ast_2_should_replace_after_recovery_threshold() -> None:
    device = {
        "sn": "260302GB3U238BAS60",
        "device_status": 1,
        "wear_days": 10.0,
    }
    alarm = {
        "abnormal_duration_minutes": 181,
        "latest_alarm_status": 2,
        "latest_sensor_internal_value": 2,
        "latest_sensor_alert": "2026-05-10T19:21:56.635000+00:00",
    }
    result = run_rules(
        fault_category="Sensor Abnormal",
        device=device,
        glucose_series=_series([5.6]),
        alarm=alarm,
        threshold_config=default_thresholds(),
        file_ids=None,
    )
    assert result.verdict == "Replacement Eligible"
    assert result.issue_detected is True
    assert result.fault_subtype == "Low Recovery Possibility"
