from __future__ import annotations

from collections import Counter
from datetime import datetime
from string import Formatter
from typing import Any

from src.core.config import get_settings


TEXT_FIELDS = (
    "badge",
    "title",
    "summary",
    "whatWeFound",
    "whyThisResult",
    "possibleCauses",
)


class SafeTemplateValues(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "N/A"


def build_verdict_presentation(
    *,
    fault_category: str | None,
    fault_subtype: str | None,
    verdict: str | None,
    issue_detected: str | None,
    evidence: dict[str, Any] | None,
    threshold_snapshot: dict[str, Any] | None,
    settings_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    config = (
        settings_config
        if settings_config is not None
        else get_settings().verdict_presentation
    )
    if not config or config.get("enabled", True) is False:
        return None
    if not verdict or not fault_subtype:
        return None

    scenario_key = _scenario_key(
        fault_category=fault_category,
        fault_subtype=fault_subtype,
        verdict=verdict,
        issue_detected=issue_detected,
        evidence=evidence or {},
    )
    if not scenario_key:
        return None

    templates = config.get("templates", {})
    template = templates.get(scenario_key)
    if not isinstance(template, dict):
        return _fallback_presentation(config, scenario_key, fault_subtype, verdict)

    values = SafeTemplateValues(
        _template_values(evidence or {}, threshold_snapshot or {})
    )
    rendered = {
        "templateVersion": str(config.get("template_version", "unknown")),
        "scenarioKey": scenario_key,
    }
    for field in TEXT_FIELDS:
        rendered[field] = _render(template.get(field, ""), values)
    rendered["supportingMaterials"] = _render_value(
        template.get("supportingMaterials", "Not displayed"), values
    )
    rendered["guidance"] = _render_value(template.get("guidance", {}), values)
    return rendered


def _scenario_key(
    *,
    fault_category: str | None,
    fault_subtype: str | None,
    verdict: str | None,
    issue_detected: str | None,
    evidence: dict[str, Any],
) -> str | None:
    subtype = fault_subtype or ""
    if fault_category == "Data accuracy":
        if "Persistent" in subtype or "Persistently" in subtype:
            return "data_accuracy.first_pass.persistent_low"
        if "No Fluctuation" in subtype:
            return "data_accuracy.first_pass.no_fluctuation"
        if "Jump" in subtype or "Sudden Fluctuation" in subtype:
            return "data_accuracy.first_pass.jump_points"
        if "Review Required" in subtype:
            return "data_accuracy.first_pass.path_switching"
        if "Data Deviation" in subtype:
            return _paired_key(evidence, verdict == "Replacement Eligible")
        if "Accuracy Within Normal Limits" in subtype:
            return _paired_key(evidence, False)
        return None
    if fault_category == "Sensor falling off":
        if verdict == "Replacement Eligible" or issue_detected == "Issue Detected":
            return "fall_off.detected"
        return "fall_off.not_detected"
    if fault_category == "Sensor Abnormal":
        if verdict != "Replacement Eligible" and issue_detected != "Issue Detected":
            if subtype == "Waiting Recovery":
                return "sensor_abnormal.waiting_recovery"
            return "sensor_abnormal.no_abnormality"
        if "Init" in subtype or "Initialization" in subtype:
            return "sensor_abnormal.gs1_initialization"
        if subtype == "Low Recovery Possibility":
            return "sensor_abnormal.low_recovery_possibility"
        return "sensor_abnormal.gs1_after_warmup"
    if fault_category == "Application failure":
        if subtype == "Insufficient Images":
            return "application_failure.insufficient_images"
        if subtype == "Invalid Evidence":
            return "application_failure.invalid_evidence"
        if subtype == "Reproduced Evidence":
            return "application_failure.reproduced_evidence"
        if subtype == "No Application Failure" or verdict == "Not Eligible":
            return "application_failure.no_application_failure"

        sub_lower = subtype.lower()
        if "assembly" in sub_lower:
            return "application_failure.assembly_failure"
        if "retention" in sub_lower or "retained" in sub_lower:
            return "application_failure.guide_needle_retention"
        if "early" in sub_lower or "launch" in sub_lower:
            return "application_failure.early_launches"
        if "exposed" in sub_lower or "electrode" in sub_lower:
            return "application_failure.exposed_electrodes"
        if (
            "adhesion" in sub_lower
            or "adhesive" in sub_lower
            or "detaching" in sub_lower
            or "detached" in sub_lower
        ):
            return "application_failure.adhesion_failure"
        if "falling" in sub_lower or "fall" in sub_lower:
            return "application_failure.sensor_falling_out"
        if "damage" in sub_lower:
            return "application_failure.implanter_damage"

        clean_subtype = subtype.lower().replace(" ", "_").replace("-", "_")
        return f"application_failure.{clean_subtype}"
    return None


def _paired_key(evidence: dict[str, Any], outside_range: bool) -> str:
    device = evidence.get("device") if isinstance(evidence.get("device"), dict) else {}
    wear_days = _float_or_none(device.get("wear_days"))
    within_48h = wear_days is None or wear_days <= 2
    if within_48h and outside_range:
        return "data_accuracy.paired.within_48_outside_range"
    if within_48h:
        return "data_accuracy.paired.within_48_within_range"
    if outside_range:
        return "data_accuracy.paired.after_48_outside_range"
    return "data_accuracy.paired.after_48_within_range"


def _fallback_presentation(
    config: dict[str, Any],
    scenario_key: str,
    fault_subtype: str | None,
    verdict: str | None,
) -> dict[str, Any]:
    return {
        "templateVersion": str(config.get("template_version", "unknown")),
        "scenarioKey": scenario_key,
        "badge": _badge_for_verdict(verdict),
        "title": fault_subtype or "Verdict",
        "summary": "Standard presentation template was not configured for this result.",
        "whatWeFound": "No configured standard-case explanation is available for this result.",
        "whyThisResult": (
            "The backend returned the verdict fields successfully, "
            "but the presentation template is missing."
        ),
        "possibleCauses": "",
        "supportingMaterials": "Not displayed",
        "guidance": {
            "text": "Please review the backend verdict fields and configure the matching standard-case template."
        },
    }


def _badge_for_verdict(verdict: str | None) -> str:
    if verdict == "Replacement Eligible":
        return "WARRANTY ELIGIBLE"
    if verdict == "Not Eligible":
        return "NOT WARRANTY ELIGIBLE"
    return "PENDING REVIEW"


def _template_values(
    evidence: dict[str, Any], threshold_snapshot: dict[str, Any]
) -> dict[str, Any]:
    device = evidence.get("device") if isinstance(evidence.get("device"), dict) else {}
    glucose_series = (
        evidence.get("glucose_series")
        if isinstance(evidence.get("glucose_series"), dict)
        else {}
    )
    alarm = evidence.get("alarm") if isinstance(evidence.get("alarm"), dict) else {}

    # Format abnormal time with timezone
    latest_sensor_alert = alarm.get("latest_sensor_alert") or alarm.get(
        "abnormal_started_at"
    )
    abnormal_time_formatted = "N/A"
    if latest_sensor_alert and latest_sensor_alert != "unknown":
        dt = _parse_datetime(latest_sensor_alert)
        if dt:
            tz_str = device.get("timeZone")
            if tz_str:
                from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
                from datetime import timezone as datetime_timezone, timedelta

                try:
                    tz = ZoneInfo(tz_str)
                    dt = dt.astimezone(tz)
                except (ZoneInfoNotFoundError, ValueError, KeyError):
                    offset = tz_str.strip()
                    if offset.upper().startswith("UTC"):
                        offset = offset[3:].strip()
                    if offset and offset[0] in {"+", "-"}:
                        sign = 1 if offset[0] == "+" else -1
                        parts = offset[1:].split(":", 1)
                        try:
                            hours = int(parts[0])
                            minutes = int(parts[1]) if len(parts) > 1 else 0
                            tz = datetime_timezone(
                                sign * timedelta(hours=hours, minutes=minutes)
                            )
                            dt = dt.astimezone(tz)
                        except ValueError:
                            pass
            abnormal_time_formatted = dt.strftime("%Y-%m-%d %H:%M")

    thresholds = _threshold_rules(threshold_snapshot)
    values = {
        "device_status": device.get("status")
        or device.get("device_status")
        or device.get("fall_off_status")
        or "N/A",
        "last_upload": device.get("last_upload") or device.get("last_data_at") or "N/A",
        "abnormal_time": abnormal_time_formatted,
        "below_mmol": thresholds.get("below_mmol", "2.8"),
        "min_hours": thresholds.get("low_min_hours", "4"),
        "max_24h_mmol": thresholds.get("max_24h_mmol", "7.8"),
        "floor_mmol": thresholds.get("floor_mmol", "4.5"),
        "no_fluc_min_hours": thresholds.get("no_fluc_min_hours", "8"),
        "max_swing_mmol": thresholds.get("max_swing_mmol", "1"),
        "delta_mmol": thresholds.get("delta_mmol", "3"),
        "min_consecutive": thresholds.get("min_consecutive", "3"),
        "within_48h_deviation_mmol": thresholds.get("within_48h_deviation_mmol", "7.0"),
        "within_48h_pair_count": thresholds.get("within_48h_pair_count", "2"),
        "pair_count": "2",
        "failed_pair_count": "2",
        "pair1_cgm": "N/A",
        "pair1_bgm": "N/A",
        "pair2_cgm": "N/A",
        "pair2_bgm": "N/A",
        "app_photo_count": thresholds.get("app_photo_count", "2"),
        "app_after_sales_score": thresholds.get("app_after_sales_score", "7.0"),
        "app_manual_review_score": thresholds.get("app_manual_review_score", "5.0"),
        "photo_count": str(len(evidence.get("file_ids", []))),
    }

    vision = evidence.get("vision") or {}
    vision_score = vision.get("score")
    if vision_score is not None:
        values["score"] = _fmt(vision_score)
    else:
        values["score"] = "N/A"

    values["subtype"] = vision.get("final_scenario") or "N/A"

    # VLM reason — only show the best-matched scenario's reason, not all concatenated
    vlm_reason = "N/A"
    scenarios_list = vision.get("scenarios") or []
    matched = [
        s
        for s in scenarios_list
        if isinstance(s, dict) and s.get("matched") and s.get("reason")
    ]
    if matched:
        best = max(matched, key=lambda s: float(s.get("confidence") or 0.0))
        vlm_reason = best["reason"]
    values["vlm_reason"] = vlm_reason

    data_accuracy_details = evidence.get("data_accuracy_details")
    values.update(_glucose_metrics(glucose_series, thresholds, data_accuracy_details))
    values.update(_vision_pair_metrics(evidence))
    return values


def _threshold_rules(snapshot: dict[str, Any]) -> dict[str, Any]:
    rules = snapshot.get("rules", snapshot)
    inaccuracy = rules.get("inaccuracy", {}) if isinstance(rules, dict) else {}
    low = inaccuracy.get("lowPersist", {}) if isinstance(inaccuracy, dict) else {}
    no_fluc = (
        inaccuracy.get("noFluctuation", {}) if isinstance(inaccuracy, dict) else {}
    )
    jump = inaccuracy.get("jump", {}) if isinstance(inaccuracy, dict) else {}
    deviation = inaccuracy.get("deviation", {}) if isinstance(inaccuracy, dict) else {}

    app_failure = rules.get("applicationFailure", {}) if isinstance(rules, dict) else {}
    if not app_failure and isinstance(rules, dict):
        app_failure = rules.get("application_failure", {})

    return {
        "below_mmol": _fmt(low.get("belowMmol", low.get("low_value", 2.8))),
        "low_min_hours": _fmt(low.get("minHours", low.get("duration_hours", 4))),
        "max_24h_mmol": _fmt(low.get("max24hMmol", low.get("max_glucose_24h", 7.8))),
        "floor_mmol": _fmt(no_fluc.get("floorMmol", no_fluc.get("max_value", 4.5))),
        "no_fluc_min_hours": _fmt(
            no_fluc.get("minHours", no_fluc.get("duration_hours", 8))
        ),
        "max_swing_mmol": _fmt(
            no_fluc.get("maxSwingMmol", no_fluc.get("max_delta", 1.0))
        ),
        "delta_mmol": _fmt(jump.get("deltaMmol", jump.get("delta", 3.0))),
        "min_consecutive": _fmt(jump.get("consecutive", jump.get("count", 3))),
        "within_48h_deviation_mmol": _fmt(
            deviation.get(
                "within48hDeviationMmol", deviation.get("deviation_mmol", 7.0)
            )
        ),
        "within_48h_pair_count": _fmt(
            deviation.get("within48hPairCount", deviation.get("min_pairs", 2))
        ),
        "app_photo_count": _fmt(
            app_failure.get("photoCount", app_failure.get("min_images", 2))
        ),
        "app_after_sales_score": _fmt(
            app_failure.get(
                "afterSalesScore", app_failure.get("after_sales_score", 7.0)
            )
        ),
        "app_manual_review_score": _fmt(
            app_failure.get("manualReviewScore", app_failure.get("min_score", 5.0))
        ),
    }


def _glucose_metrics(
    glucose_series: dict[str, Any],
    thresholds: dict[str, Any],
    data_accuracy_details: dict[str, Any] | None = None,
) -> dict[str, str]:
    points = glucose_series.get("points", [])
    if not isinstance(points, list) or not points:
        low_hours = "N/A"
        peak_24h_mmol = "N/A"
        flat_hours = "N/A"
        swing_mmol = "N/A"
        max_step_mmol = "N/A"
        consecutive_jumps = "N/A"

        if data_accuracy_details:
            # 1. persistently_low
            low_details = data_accuracy_details.get("persistently_low")
            if isinstance(low_details, dict):
                if "max_glucose_24h" in low_details:
                    peak_24h_mmol = _fmt(low_details["max_glucose_24h"])
                if "actual_low_hours" in low_details:
                    low_hours = _fmt(low_details["actual_low_hours"])

            # 2. no_fluctuation
            flat_details = data_accuracy_details.get("no_fluctuation")
            if isinstance(flat_details, dict):
                if "max_glucose_24h" in flat_details and peak_24h_mmol == "N/A":
                    peak_24h_mmol = _fmt(flat_details["max_glucose_24h"])
                if "actual_flat_hours" in flat_details:
                    flat_hours = _fmt(flat_details["actual_flat_hours"])
                if "actual_max_delta" in flat_details:
                    swing_mmol = _fmt(flat_details["actual_max_delta"])

            # 3. sudden_fluctuation
            sudden_details = data_accuracy_details.get("sudden_fluctuation")
            if isinstance(sudden_details, dict):
                if "jump_count" in sudden_details:
                    consecutive_jumps = str(sudden_details["jump_count"])
                jump_points = sudden_details.get("jump_points") or []
                if isinstance(jump_points, list) and jump_points:
                    deltas = []
                    for pt in jump_points:
                        if isinstance(pt, dict) and "delta" in pt:
                            deltas.append(pt["delta"])
                    if deltas:
                        max_step_mmol = _fmt(max(deltas))

        return {
            "low_hours": low_hours,
            "peak_24h_mmol": peak_24h_mmol,
            "flat_hours": flat_hours,
            "swing_mmol": swing_mmol,
            "max_step_mmol": max_step_mmol,
            "consecutive_jumps": consecutive_jumps,
        }

    values = [
        _float_or_none(point.get("glucose"))
        for point in points
        if isinstance(point, dict)
    ]
    values = [value for value in values if value is not None]
    below = _float_or_none(thresholds.get("below_mmol")) or 2.8
    delta = _float_or_none(thresholds.get("delta_mmol")) or 3.0
    low_points = [
        point
        for point in points
        if isinstance(point, dict)
        and (_float_or_none(point.get("glucose")) or 999) <= below
    ]
    jumps = [abs(values[index] - values[index - 1]) for index in range(1, len(values))]
    return {
        "low_hours": _fmt(_duration_hours(low_points)),
        "peak_24h_mmol": _fmt(max(values) if values else None),
        "flat_hours": _fmt(_duration_hours(points)),
        "swing_mmol": _fmt((max(values) - min(values)) if values else None),
        "max_step_mmol": _fmt(max(jumps) if jumps else None),
        "consecutive_jumps": str(sum(1 for jump in jumps if jump > delta)),
    }


def _vision_pair_metrics(evidence: dict[str, Any]) -> dict[str, str]:
    vision = evidence.get("vision_analysis") or evidence.get("vision") or {}
    if not isinstance(vision, dict):
        return {}
    readings = vision.get("glucose_readings")
    if not isinstance(readings, list) or len(readings) < 4:
        return {}
    pair_values = []
    for index in (0, 2):
        cgm = readings[index] if isinstance(readings[index], dict) else {}
        bgm = readings[index + 1] if isinstance(readings[index + 1], dict) else {}
        pair_values.append((cgm.get("value"), bgm.get("value")))
    failed_count = 0
    for cgm, bgm in pair_values:
        cgm_float = _float_or_none(cgm)
        bgm_float = _float_or_none(bgm)
        if (
            cgm_float is not None
            and bgm_float is not None
            and abs(cgm_float - bgm_float) > 0
        ):
            failed_count += 1
    return {
        "pair1_cgm": _fmt(pair_values[0][0]),
        "pair1_bgm": _fmt(pair_values[0][1]),
        "pair2_cgm": _fmt(pair_values[1][0]),
        "pair2_bgm": _fmt(pair_values[1][1]),
        "pair_count": str(len(pair_values)),
        "failed_pair_count": str(failed_count),
    }


def _duration_hours(points: list[Any]) -> float | None:
    timestamps = []
    for point in points:
        if not isinstance(point, dict) or "timestamp" not in point:
            continue
        parsed = _parse_datetime(point["timestamp"])
        if parsed is not None:
            timestamps.append(parsed)
    if len(timestamps) < 2:
        return None
    return abs((max(timestamps) - min(timestamps)).total_seconds()) / 3600


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "N/A"
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"


def _render_value(value: Any, values: SafeTemplateValues) -> Any:
    if isinstance(value, str):
        return _render(value, values)
    if isinstance(value, list):
        return [_render_value(item, values) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item, values) for key, item in value.items()}
    return value


def _render(template: Any, values: SafeTemplateValues) -> str:
    if not isinstance(template, str):
        return ""
    field_names = [
        field_name for _, field_name, _, _ in Formatter().parse(template) if field_name
    ]
    if field_names:
        missing = Counter(name for name in field_names if name not in values)
        values.update({name: "N/A" for name in missing})
    return template.format_map(values)
