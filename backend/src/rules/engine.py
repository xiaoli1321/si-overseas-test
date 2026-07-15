from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
import logging
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.logging import log_context
from src.rules.thresholds import to_rule_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuleResult:
    """
    规则引擎判定结果的数据结构。

    属性:
        verdict: 判定结论 (如 "Replacement Eligible" 符合换新, "Not Eligible" 不符合换新, "Under Review" 人工审核)
        issue_detected: 是否检测到问题
        fault_category: 故障主分类 (如 "Data accuracy", "Sensor falling off" 等)
        fault_subtype: 故障子类 (如 "Persistently Low" 持续偏低, "Sudden Fall Off" 骤降脱落)
        reasons: 判定理由/原因描述列表
        matched_rules: 命中的规则标识列表
        evidence: 诊断过程中沉淀的证据链数据 (包含设备信息、血糖点数据序列、报警数据等)
    """

    verdict: str
    issue_detected: bool
    fault_category: str
    fault_subtype: str
    reasons: list[str]
    matched_rules: list[str]
    evidence: dict[str, Any]


@dataclass(frozen=True)
class GlucosePoint:
    timestamp: datetime
    glucose: float
    interval_minutes: float | None = None


def run_rules(
    *,
    fault_category: str,
    device: dict[str, Any],
    glucose_series: dict[str, Any],
    alarm: dict[str, Any],
    threshold_config: dict[str, Any],
    file_ids: list[str] | None = None,
    vision_analysis: dict[str, Any] | None = None,
    prefer_file_deviation: bool = False,
) -> RuleResult:
    """
    售后故障判定规则引擎的核心入口函数。
    根据指定的故障类别，调用相应的子规则判定逻辑，并根据模拟/测试期望调整最终结果。

    参数:
        fault_category: 待诊断的故障主类
        device: 从海外接口获取的设备状态及基本信息
        glucose_series: 设备上传的血糖历史数据序列
        alarm: 设备上报的最新告警/异常记录
        threshold_config: 全局/用户自定义的判定阈值配置
        file_ids: 用户上传的凭证文件 ID 列表
        vision_analysis: VLM 视觉大模型对凭证图片的分析结果
        prefer_file_deviation: 有文件时跳过曲线规则，仅进行图片偏差判断
    """
    # 将配置转换为规范的规则配置结构
    threshold_config = to_rule_config(threshold_config)

    # 1. 血糖数据准确性诊断 ("Data accuracy")
    if fault_category == "Data accuracy":
        return _run_data_accuracy(
            device,
            glucose_series,
            threshold_config,
            file_ids,
            vision_analysis,
            prefer_file_deviation,
        )

    # 2. 传感器脱落诊断 ("Sensor falling off")
    if fault_category == "Sensor falling off":
        return _run_sensor_falling_off(device, threshold_config)

    # 3. 传感器异常诊断 ("Sensor Abnormal")
    if fault_category == "Sensor Abnormal":
        return _run_sensor_abnormal(device, alarm, threshold_config)

    # 4. 软件/应用故障诊断 ("Application failure")
    if fault_category == "Application failure":
        return _run_application_failure(
            file_ids or [], threshold_config, vision_analysis
        )

    # 不支持的故障分类返回人工审核状态
    return RuleResult(
        verdict="Under Review",
        issue_detected=False,
        fault_category=fault_category,
        fault_subtype="Unsupported category",
        reasons=[
            "The selected fault category is not supported by the MVP rule engine."
        ],
        matched_rules=[],
        evidence={"device": device},
    )


def _parse_point_timestamp(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _normalize_glucose_points(glucose_series: dict[str, Any]) -> list[GlucosePoint]:
    normalized: list[GlucosePoint] = []
    for raw_point in glucose_series.get("points", []):
        if not isinstance(raw_point, dict):
            continue
        timestamp = _parse_point_timestamp(raw_point.get("timestamp"))
        if timestamp is None:
            continue
        try:
            glucose = float(raw_point["glucose"])
        except (KeyError, TypeError, ValueError):
            continue
        interval = _positive_float_or_none(raw_point.get("interval_minutes"))
        normalized.append(
            GlucosePoint(
                timestamp=timestamp, glucose=glucose, interval_minutes=interval
            )
        )
    return sorted(normalized, key=lambda point: point.timestamp)


def _positive_float_or_none(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _resolve_series_timezone(raw_timezone: Any) -> tzinfo:
    if not isinstance(raw_timezone, str) or not raw_timezone.strip():
        return UTC
    value = raw_timezone.strip()
    if value.upper() in {"UTC", "Z"}:
        return UTC
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        pass
    offset = value
    if offset.upper().startswith("UTC"):
        offset = offset[3:].strip()
    if offset and offset[0] in {"+", "-"}:
        sign = 1 if offset[0] == "+" else -1
        parts = offset[1:].split(":", 1)
        try:
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            return UTC
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    return UTC


def _recent_24h_points(points: list[GlucosePoint]) -> list[GlucosePoint]:
    if not points:
        return []
    latest = points[-1].timestamp
    start = latest - timedelta(hours=24)
    return [point for point in points if start <= point.timestamp <= latest]


def _expected_interval_minutes(points: list[GlucosePoint]) -> float | None:
    explicit = [
        point.interval_minutes for point in points if point.interval_minutes is not None
    ]
    if explicit:
        return float(median(explicit))
    gaps = [
        (points[index].timestamp - points[index - 1].timestamp).total_seconds() / 60
        for index in range(1, len(points))
        if points[index].timestamp > points[index - 1].timestamp
    ]
    return float(median(gaps)) if gaps else None


def _is_continuous(
    prev: GlucosePoint, current: GlucosePoint, expected_minutes: float | None
) -> bool:
    if expected_minutes is None:
        return True
    gap_minutes = (current.timestamp - prev.timestamp).total_seconds() / 60
    return gap_minutes <= expected_minutes * 2


def _group_points_by_device_day(
    points: list[GlucosePoint], device_tz: tzinfo
) -> list[list[GlucosePoint]]:
    groups: dict[Any, list[GlucosePoint]] = {}
    for point in points:
        day = point.timestamp.astimezone(device_tz).date()
        groups.setdefault(day, []).append(point)
    return [groups[day] for day in sorted(groups)]


def _point_span_hours(points: list[GlucosePoint]) -> float:
    if len(points) < 2:
        return 0.0
    return (points[-1].timestamp - points[0].timestamp).total_seconds() / 3600


def _has_low_segment(
    day_groups: list[list[GlucosePoint]],
    *,
    low_value: float,
    duration_hours: float,
    expected_minutes: float | None,
) -> tuple[bool, list[tuple[datetime, datetime]]]:
    matched_segments = []
    for group in day_groups:
        segment: list[GlucosePoint] = []
        for point in group:
            if point.glucose > low_value:
                if segment and _point_span_hours(segment) >= duration_hours:
                    matched_segments.append(
                        (segment[0].timestamp, segment[-1].timestamp)
                    )
                segment = []
                continue
            if segment and not _is_continuous(segment[-1], point, expected_minutes):
                if _point_span_hours(segment) >= duration_hours:
                    matched_segments.append(
                        (segment[0].timestamp, segment[-1].timestamp)
                    )
                segment = []
            segment.append(point)
        if segment and _point_span_hours(segment) >= duration_hours:
            matched_segments.append((segment[0].timestamp, segment[-1].timestamp))
    return len(matched_segments) > 0, matched_segments


def _has_no_fluctuation_segment(
    day_groups: list[list[GlucosePoint]],
    *,
    max_value: float,
    max_delta: float,
    duration_hours: float,
    expected_minutes: float | None,
) -> tuple[bool, list[tuple[datetime, datetime]], float]:
    matched_segments = []
    max_observed_delta = 0.0
    for group in day_groups:
        segment: list[GlucosePoint] = []
        for point in group:
            if point.glucose >= max_value:
                if segment and _point_span_hours(segment) >= duration_hours:
                    matched_segments.append(segment)
                segment = []
                continue
            if segment:
                continuous = _is_continuous(segment[-1], point, expected_minutes)
                flat = abs(point.glucose - segment[-1].glucose) <= max_delta
                if not continuous or not flat:
                    if _point_span_hours(segment) >= duration_hours:
                        matched_segments.append(segment)
                    segment = []
            segment.append(point)
        if segment and _point_span_hours(segment) >= duration_hours:
            matched_segments.append(segment)

    if not matched_segments:
        return False, [], 0.0

    result_ranges = []
    for seg in matched_segments:
        vals = [p.glucose for p in seg]
        seg_delta = max(vals) - min(vals) if vals else 0.0
        max_observed_delta = max(max_observed_delta, seg_delta)
        result_ranges.append((seg[0].timestamp, seg[-1].timestamp))

    return True, result_ranges, max_observed_delta


def _max_consecutive_jumps(
    day_groups: list[list[GlucosePoint]],
    *,
    delta: float,
    expected_minutes: float | None,
) -> tuple[int, list[dict[str, Any]]]:
    max_count = 0
    jump_points = []
    for group in day_groups:
        current_count = 0
        for index in range(1, len(group)):
            prev = group[index - 1]
            current = group[index]
            if not _is_continuous(prev, current, expected_minutes):
                current_count = 0
                continue
            diff = abs(current.glucose - prev.glucose)
            if diff > delta:
                current_count += 1
                max_count = max(max_count, current_count)
                jump_points.append(
                    {
                        "timestamp": int(current.timestamp.timestamp()),
                        "pre_value": prev.glucose,
                        "post_value": current.glucose,
                        "delta": round(diff, 2),
                    }
                )
            else:
                current_count = 0
    return max_count, jump_points


def _run_data_accuracy(
    device: dict[str, Any],
    glucose_series: dict[str, Any],
    thresholds: dict[str, Any],
    file_ids: list[str] | None = None,
    vision_analysis: dict[str, Any] | None = None,
    prefer_file_deviation: bool = False,
) -> RuleResult:
    """
    诊断血糖数据准确性 (Data accuracy)。
    基于不同的血糖序列数据特征进行规则匹配：
    1. Persistently Low (持续偏低): 血糖持续处于极低状态且无高值峰。
    2. No Fluctuation (无波动): 血糖值几乎成一条直线，缺乏生理性正常波动。
    3. Sudden Fluctuation (骤变/突变): 血糖序列中出现超出正常生理变化的突增或突降点。
    """
    points = _normalize_glucose_points(glucose_series)
    window_points = _recent_24h_points(points)
    values = [point.glucose for point in window_points]
    device_tz = _resolve_series_timezone(
        glucose_series.get("timezone") or device.get("timeZone")
    )
    day_groups = _group_points_by_device_day(window_points, device_tz)
    expected_minutes = _expected_interval_minutes(window_points)
    rules = thresholds["data_accuracy"]

    # 1. 判定是否为持续偏低 (Persistently Low)
    low = rules["persistently_low"]
    has_low_segment, low_segments = _has_low_segment(
        day_groups,
        low_value=float(low["low_value"]),
        duration_hours=float(low["duration_hours"]),
        expected_minutes=expected_minutes,
    )
    max_val = max(values) if values else 0.0

    # 2. 判定是否为无波动 (No Fluctuation)
    no_fluc = rules["no_fluctuation"]
    has_flat_segment, flat_segments, flat_delta = _has_no_fluctuation_segment(
        day_groups,
        max_value=float(no_fluc["max_value"]),
        max_delta=float(no_fluc["max_delta"]),
        duration_hours=float(no_fluc["duration_hours"]),
        expected_minutes=expected_minutes,
    )

    # 3. 判定是否为突然波动 (Sudden Fluctuation)
    sudden = rules["sudden_fluctuation"]
    jump_count, jump_points = _max_consecutive_jumps(
        day_groups,
        delta=float(sudden["delta"]),
        expected_minutes=expected_minutes,
    )

    # 构造细节信息字典
    details = {
        "persistently_low": {
            "max_glucose_24h": max_val,
            "actual_low_hours": float(low["duration_hours"])
            if has_low_segment
            else 0.0,
            "trigger_segments": [
                {"start_at": start.isoformat(), "end_at": end.isoformat()}
                for start, end in low_segments
            ],
        }
        if has_low_segment
        else None,
        "no_fluctuation": {
            "max_glucose_24h": max_val,
            "actual_flat_hours": float(no_fluc["duration_hours"])
            if has_flat_segment
            else 0.0,
            "actual_max_delta": flat_delta,
            "trigger_segments": [
                {"start_at": start.isoformat(), "end_at": end.isoformat()}
                for start, end in flat_segments
            ],
        }
        if has_flat_segment
        else None,
        "sudden_fluctuation": {"jump_count": jump_count, "jump_points": jump_points}
        if jump_count >= sudden["count"]
        else None,
    }

    # OpenAPI treats supplied screenshots as the source of truth for a data
    # deviation review.  In that case do not let a curve pattern override the
    # image-based result.
    if prefer_file_deviation and file_ids:
        return _run_data_accuracy_deviation(
            device, glucose_series, thresholds, file_ids, vision_analysis, details
        )

    if values and max_val <= low["max_glucose_24h"] and has_low_segment:
        return RuleResult(
            verdict="Replacement Eligible",
            issue_detected=True,
            fault_category="Data accuracy",
            fault_subtype="Persistently Low",
            reasons=[
                f"24h peak {max_val:.1f} mmol/L is within {low['max_glucose_24h']} mmol/L.",
                f"Low-value segment lasts at least {low['duration_hours']} hours.",
            ],
            matched_rules=["data_accuracy.persistently_low"],
            evidence={
                "device": device,
                "glucose_series": glucose_series,
                "data_accuracy_details": details,
            },
        )

    if has_flat_segment:
        return RuleResult(
            verdict="Replacement Eligible",
            issue_detected=True,
            fault_category="Data accuracy",
            fault_subtype="No Fluctuation",
            reasons=["Glucose values remain flat within configured swing threshold."],
            matched_rules=["data_accuracy.no_fluctuation"],
            evidence={
                "device": device,
                "glucose_series": glucose_series,
                "data_accuracy_details": details,
            },
        )

    if jump_count >= sudden["count"]:
        return RuleResult(
            verdict="Replacement Eligible",
            issue_detected=True,
            fault_category="Data accuracy",
            fault_subtype="Sudden Fluctuation",
            reasons=[f"{jump_count} jumps exceed {sudden['delta']} mmol/L."],
            matched_rules=["data_accuracy.sudden_fluctuation"],
            evidence={
                "device": device,
                "glucose_series": glucose_series,
                "data_accuracy_details": details,
            },
        )

    # If curves do not match, check if user provided files (data deviation review)
    is_mock_deviation = (
        device.get("fault")
        and device["fault"].get("faultCategory") == "Data accuracy"
        and device["fault"].get("faultSubtype") == "Data Deviation Detected"
    )

    if file_ids or is_mock_deviation:
        return _run_data_accuracy_deviation(
            device, glucose_series, thresholds, file_ids or [], vision_analysis, details
        )

    return RuleResult(
        verdict="Under Review",
        issue_detected=False,
        fault_category="Data accuracy",
        fault_subtype="Data Deviation Review Required",
        reasons=[
            "Curve screening did not match automatic rules; paired CGM/BGM evidence is required."
        ],
        matched_rules=[],
        evidence={
            "device": device,
            "glucose_series": glucose_series,
            "data_accuracy_details": details,
        },
    )


def _run_data_accuracy_deviation(
    device: dict[str, Any],
    glucose_series: dict[str, Any],
    thresholds: dict[str, Any],
    file_ids: list[str],
    vision_analysis: dict[str, Any] | None,
    details: dict[str, Any],
) -> RuleResult:
    dev_rules = thresholds.get("data_accuracy", {}).get("data_deviation", {})
    wear_days_raw = device.get("wear_days")
    try:
        wear_days = float(wear_days_raw) if wear_days_raw is not None else 0.0
    except (ValueError, TypeError):
        wear_days = 0.0

    after_48h_wear_days = float(dev_rules.get("after48hWearDays", 2.0))
    if after_48h_wear_days <= 0:
        after_48h_wear_days = 2.0
    min_pairs = int(
        dev_rules.get(
            "within48hPairCount" if wear_days < after_48h_wear_days else "after48hPairCount",
            2,
        )
    )
    required_images = 2 * min_pairs

    if len(file_ids) < required_images:
        return RuleResult(
            verdict="Under Review",
            issue_detected=False,
            fault_category="Data accuracy",
            fault_subtype="Data Deviation Review Required",
            reasons=[
                f"Paired CGM/BGM evidence is required for data-deviation review (at least {required_images} images)."
            ],
            matched_rules=[],
            evidence={
                "device": device,
                "glucose_series": glucose_series,
                "file_ids": file_ids,
                "data_accuracy_details": details,
            },
        )

    v_analysis = vision_analysis
    if not v_analysis:
        from src.integrations.vlm import fallback_glucose_analysis

        v_analysis = fallback_glucose_analysis(file_ids).model_dump()
    verdict, subtype_override, vlm_reasons = _verify_data_accuracy_vision(
        v_analysis, thresholds, device
    )
    return RuleResult(
        verdict=verdict,
        issue_detected=(verdict == "Replacement Eligible"),
        fault_category="Data accuracy",
        fault_subtype=subtype_override or "Data Deviation Detected",
        reasons=vlm_reasons,
        matched_rules=["data_accuracy.vlm_deviation_check"],
        evidence={
            "device": device,
            "glucose_series": glucose_series,
            "file_ids": file_ids,
            "vision_analysis": v_analysis,
            "data_accuracy_details": details,
        },
    )


def _run_sensor_falling_off(
    device: dict[str, Any], thresholds: dict[str, Any]
) -> RuleResult:
    limit = thresholds["sensor_falling_off"]["wear_days_limit"]
    fall_status = device["fall_off_status"]
    wear_days = float(device["wear_days"])
    if fall_status == "fallen_off" and wear_days < limit:
        return RuleResult(
            verdict="Replacement Eligible",
            issue_detected=True,
            fault_category="Sensor falling off",
            fault_subtype="Sudden Fall Off",
            reasons=[
                f"Device is fallen off and wear time {wear_days:.1f} d is below {float(limit):.1f} d."
            ],
            matched_rules=["sensor_falling_off.sudden_fall_off"],
            evidence={"device": device},
        )
    if fall_status == "suspected_fall_off":
        return RuleResult(
            verdict="Not Eligible",
            issue_detected=False,
            fault_category="Sensor falling off",
            fault_subtype="Suspected Fall Off",
            reasons=[
                "Device is marked as suspected fall off, which requires manual/customer guidance first."
            ],
            matched_rules=["sensor_falling_off.suspected_fall_off"],
            evidence={"device": device},
        )
    return RuleResult(
        verdict="Not Eligible",
        issue_detected=False,
        fault_category="Sensor falling off",
        fault_subtype="No Fall Off",
        reasons=["No qualifying fall-off status was detected."],
        matched_rules=[],
        evidence={"device": device},
    )


def _run_sensor_abnormal(
    device: dict[str, Any], alarm: dict[str, Any], thresholds: dict[str, Any]
) -> RuleResult:
    rules = thresholds["sensor_abnormal"]
    status = int(device["device_status"])
    wear_minutes = float(device["wear_days"]) * 24 * 60
    abnormal_minutes = int(alarm["abnormal_duration_minutes"])
    internal_value = int(alarm.get("latest_sensor_internal_value") or 0)

    if status == 6 and abnormal_minutes > rules["temporary_abnormal_hours"] * 60:
        subtype = "Temporary Abnormal"
    elif (
        status == 4
        and internal_value in (0, 1)
        and wear_minutes <= rules["warmup_minutes"]
    ):
        subtype = "Replace Device - Init"
    elif status == 4 and internal_value == 2 and wear_minutes > rules["warmup_minutes"]:
        subtype = "Replace Device - Use"
    elif (
        status == 1
        and alarm["latest_alarm_status"] == 2
        and abnormal_minutes > rules["waiting_recovery_hours"] * 60
    ):
        subtype = "Low Recovery Possibility"
    elif status == 5 and wear_minutes <= rules["warmup_minutes"]:
        subtype = "Initialization Abnormal"
    else:
        subtype = ""

    # Map alarm keys to Snapshot format for engine output
    alarm_snapshot = {
        "serial_no": str(
            device.get("serial_no")
            or device.get("sn")
            or alarm.get("serial_no")
            or "unknown"
        ),
        "latest_alarm_status": int(alarm.get("latest_alarm_status", 0)),
        "latest_sensor_internal_value": internal_value,
        "abnormal_started_at": str(
            alarm.get("latest_sensor_alert")
            or alarm.get("abnormal_started_at")
            or "unknown"
        ),
        "abnormal_duration_minutes": int(alarm.get("abnormal_duration_minutes", 0)),
        "raw_device_status": int(
            device.get("device_status") or alarm.get("raw_device_status") or 0
        ),
    }

    if subtype:
        return RuleResult(
            verdict="Replacement Eligible",
            issue_detected=True,
            fault_category="Sensor Abnormal",
            fault_subtype=subtype,
            reasons=[
                (
                    f"Raw device status {status}, sensor internal value "
                    f"{internal_value}, abnormal duration {abnormal_minutes} minutes."
                )
            ],
            matched_rules=[f"sensor_abnormal.{subtype.lower().replace(' ', '_')}"],
            evidence={"device": device, "alarm": alarm_snapshot},
        )

    waiting = status == 1 and alarm["latest_alarm_status"] == 2
    return RuleResult(
        verdict="Not Eligible",
        issue_detected=False,
        fault_category="Sensor Abnormal",
        fault_subtype="Waiting Recovery" if waiting else "No Abnormal",
        reasons=["No qualifying abnormal replacement condition was detected."],
        matched_rules=["sensor_abnormal.waiting_recovery"] if waiting else [],
        evidence={"device": device, "alarm": alarm_snapshot},
    )


def _run_application_failure(
    file_ids: list[str],
    thresholds: dict[str, Any],
    vision_analysis: dict[str, Any] | None,
) -> RuleResult:
    rules = thresholds["application_failure"]
    if len(file_ids) < rules["min_images"]:
        return RuleResult(
            verdict="Under Review",
            issue_detected=False,
            fault_category="Application failure",
            fault_subtype="Insufficient Images",
            reasons=[f"At least {rules['min_images']} images are required."],
            matched_rules=[],
            evidence={"file_ids": file_ids, "vision": None},
        )

    vision = _normalize_vision_analysis(vision_analysis)
    score = _application_failure_score(vision)
    after_sales_score = float(rules.get("after_sales_score", 7.0))
    manual_review_score = float(rules["min_score"])

    if score >= after_sales_score:
        verdict = "Replacement Eligible"
    elif score >= manual_review_score:
        verdict = "Under Review"
    else:
        verdict = "Not Eligible"

    reasons = _application_failure_reasons(
        vision, score, after_sales_score, manual_review_score
    )
    matched_rules = _application_failure_matched_rules(vision)

    return RuleResult(
        verdict=verdict,
        issue_detected=verdict == "Replacement Eligible",
        fault_category="Application failure",
        fault_subtype=_application_failure_subtype(vision, verdict),
        reasons=reasons,
        matched_rules=matched_rules,
        evidence={
            "file_ids": file_ids,
            "vision": {
                "model_name": vision.get("model_name", "unknown"),
                "prompt_version": vision.get("prompt_version", "unknown"),
                "source": vision.get("source", "unknown"),
                "score": score,
                "scenarios": vision.get("scenarios", []),
                "final_scenario": vision.get("final_scenario"),
                "final_confidence": vision.get("final_confidence"),
                "features": {
                    "is_cgm_device_present": vision["is_cgm_device_present"],
                    "is_reproduced_photo": vision["is_reproduced_photo"],
                    "needle_exposed": vision["needle_exposed"],
                    "adhesive_detached": vision["adhesive_detached"],
                    "implanter_damage": vision["implanter_damage"],
                },
            },
        },
    )


def _normalize_vision_analysis(
    vision_analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = vision_analysis or {}
    scenarios = raw.get("scenarios")

    if scenarios is not None:
        normalized_scenarios = []
        for s in scenarios:
            if hasattr(s, "model_dump"):
                normalized_scenarios.append(s.model_dump())
            elif isinstance(s, dict):
                normalized_scenarios.append(s)
            else:
                normalized_scenarios.append(dict(s))
        scenarios = normalized_scenarios
    else:
        # Construct scenarios from legacy fields
        scenarios = []
        is_present = bool(raw.get("is_cgm_device_present", False))
        is_fraud = bool(raw.get("is_reproduced_photo", False))

        needle_exposed = bool(raw.get("needle_exposed", False))
        adhesive_detached = bool(raw.get("adhesive_detached", False))
        implanter_damage = bool(raw.get("implanter_damage", False))

        scenarios.append(
            {
                "scenario": "Assembly failed",
                "matched": False,
                "confidence": 0.0,
                "reason": "Legacy feature check.",
            }
        )
        scenarios.append(
            {
                "scenario": "Guiding needle retention",
                "matched": False,
                "confidence": 0.0,
                "reason": "Legacy feature check.",
            }
        )
        scenarios.append(
            {
                "scenario": "Exposed Electrodes",
                "matched": needle_exposed and is_present and not is_fraud,
                "confidence": 10.0
                if needle_exposed and is_present and not is_fraud
                else 0.0,
                "reason": "Legacy Exposed Electrodes match.",
            }
        )
        scenarios.append(
            {
                "scenario": "Adhesive detaching",
                "matched": adhesive_detached and is_present and not is_fraud,
                "confidence": 8.0
                if adhesive_detached and is_present and not is_fraud
                else 0.0,
                "reason": "Legacy Adhesive detaching match.",
            }
        )
        scenarios.append(
            {
                "scenario": "Implanter damage",
                "matched": implanter_damage and is_present and not is_fraud,
                "confidence": 7.0
                if implanter_damage and is_present and not is_fraud
                else 0.0,
                "reason": "Legacy Implanter damage match.",
            }
        )
        scenarios.append(
            {
                "scenario": "None of the above",
                "matched": not any(
                    [needle_exposed, adhesive_detached, implanter_damage]
                ),
                "confidence": 0.0
                if any([needle_exposed, adhesive_detached, implanter_damage])
                else 1.0,
                "reason": "Legacy default.",
            }
        )

    matched_scenarios = [s for s in scenarios if s.get("matched")]
    if matched_scenarios:
        best_match = max(matched_scenarios, key=lambda s: s.get("confidence", 0.0))
        final_scenario = best_match["scenario"]
        final_confidence = best_match["confidence"]
    else:
        final_scenario = "None of the above"
        final_confidence = 0.0

    return {
        "is_cgm_device_present": bool(
            raw.get(
                "is_cgm_device_present",
                not scenarios
                or any(
                    s.get("matched")
                    for s in scenarios
                    if s.get("scenario") != "None of the above"
                ),
            )
        ),
        "is_reproduced_photo": bool(raw.get("is_reproduced_photo", False)),
        "needle_exposed": bool(
            raw.get("needle_exposed", False)
            or any(
                s.get("matched")
                for s in scenarios
                if s.get("scenario") == "Exposed Electrodes"
            )
        ),
        "adhesive_detached": bool(
            raw.get("adhesive_detached", False)
            or any(
                s.get("matched")
                for s in scenarios
                if s.get("scenario") == "Adhesive detaching"
            )
        ),
        "implanter_damage": bool(
            raw.get("implanter_damage", False)
            or any(
                s.get("matched")
                for s in scenarios
                if s.get("scenario") == "Implanter damage"
            )
        ),
        "scenarios": scenarios,
        "final_scenario": final_scenario,
        "final_confidence": float(final_confidence),
        "model_name": raw.get("model_name", "unknown"),
        "prompt_version": raw.get("prompt_version", "unknown"),
        "source": raw.get("source", "unknown"),
    }


def _application_failure_score(vision: dict[str, Any]) -> float:
    if not vision["is_cgm_device_present"] or vision["is_reproduced_photo"]:
        return 0.0
    return float(vision.get("final_confidence", 0.0))


def _application_failure_matched_rules(vision: dict[str, Any]) -> list[str]:
    rules = []
    if vision["is_reproduced_photo"]:
        rules.append("application_failure.reproduced_photo")
    if not vision["is_cgm_device_present"]:
        rules.append("application_failure.cgm_not_present")

    final_scenario = vision.get("final_scenario")
    if final_scenario and final_scenario != "None of the above":
        clean_name = final_scenario.lower().replace(" ", "_")
        rules.append(f"application_failure.{clean_name}")
    return rules


def _application_failure_reasons(
    vision: dict[str, Any],
    score: float,
    after_sales_score: float,
    manual_review_score: float,
) -> list[str]:
    if not vision["is_cgm_device_present"]:
        return [
            "CGM device was not detected in the uploaded evidence; score is forced to 0."
        ]
    if vision["is_reproduced_photo"]:
        return [
            "Uploaded evidence appears to be a screen reproduction; score is forced to 0."
        ]

    reasons = [
        f"Vision score {score:.1f} was calculated from scenario evaluation.",
        f"Replacement threshold is {after_sales_score:.1f}; manual review threshold is {manual_review_score:.1f}.",
    ]

    final_scenario = vision.get("final_scenario")
    if final_scenario and final_scenario != "None of the above":
        reasons.append(
            f'Matched scenario: "{final_scenario}" with confidence {score:.1f}/10.'
        )
    else:
        reasons.append("No application-failure visual defect was identified.")

    return reasons


def _application_failure_subtype(vision: dict[str, Any], verdict: str) -> str:
    if not vision["is_cgm_device_present"]:
        return "Invalid Evidence"
    if vision["is_reproduced_photo"]:
        return "Reproduced Evidence"
    if verdict == "Not Eligible" or vision["final_scenario"] == "None of the above":
        return "No Application Failure"
    return vision["final_scenario"]


def _verify_data_accuracy_vision(
    vision_analysis: dict[str, Any] | None,
    thresholds: dict[str, Any],
    device: dict[str, Any],
) -> tuple[str, str | None, list[str]]:
    """
    Returns (verdict, fault_subtype_override, reasons)
    If verification passes: returns ("Replacement Eligible", "Data Deviation Detected", reasons)
    If fraud detected: returns ("Not Eligible", "Fraud Detected", reasons)
    If readings are not deviating enough: returns ("Not Eligible", "Accuracy Within Normal Limits", reasons)
    If images are invalid/unreadable: returns ("Under Review", "Data Deviation Review Required", reasons)
    """
    from src.core.config import get_settings

    settings = get_settings()

    logger.info(
        "Data accuracy vision verification started",
        extra=log_context("rules.data_accuracy_vision_started"),
    )

    if not vision_analysis or "glucose_readings" not in vision_analysis:
        logger.error(
            "Data accuracy vision readings are missing",
            extra=log_context("rules.data_accuracy_vision_missing"),
        )
        return (
            "Under Review",
            "Data Deviation Review Required",
            ["Paired CGM/BGM evidence is required but analysis is missing."],
        )

    readings = vision_analysis["glucose_readings"]

    # Retrieve rules config and parse device wear days
    dev_rules = thresholds.get("data_accuracy", {}).get("data_deviation", {})
    wear_days_raw = device.get("wear_days")
    try:
        wear_days = float(wear_days_raw) if wear_days_raw is not None else 0.0
    except (ValueError, TypeError):
        wear_days = 0.0

    after_48h_wear_days = float(dev_rules.get("after48hWearDays", 2.0))
    if after_48h_wear_days <= 0:
        after_48h_wear_days = 2.0

    is_within_48h = wear_days < after_48h_wear_days
    boundary = float(dev_rules.get("after48hDeviationRangeBoundary", 4.4))

    # Load dynamic group parameters
    if is_within_48h:
        min_pairs = int(dev_rules.get("within48hPairCount", 2))
        req_qualified = int(dev_rules.get("within48hQualifiedPairCount", 2))
        abs_thresh = float(dev_rules.get("within48hDeviationMmol", 7.0))
        rel_thresh = None
        mode_desc = f"48h内 (当前佩戴天数: {wear_days:.2f}天 < 门槛: {after_48h_wear_days:.1f}天)"
        logger.info(
            "Data accuracy vision uses within-48h rule",
            extra=log_context(
                "rules.data_accuracy_vision_mode",
                mode="within_48h",
                wear_days=round(wear_days, 2),
                absolute_threshold=abs_thresh,
                pair_count=min_pairs,
                qualified_pair_count=req_qualified,
            ),
        )
    else:
        min_pairs = int(dev_rules.get("after48hPairCount", 2))
        req_qualified = int(dev_rules.get("after48hQualifiedPairCount", 2))
        abs_thresh = dev_rules.get("after48hDeviationMmol")
        if abs_thresh is None:
            abs_thresh = settings.data_accuracy_abs_threshold
        else:
            abs_thresh = float(abs_thresh)
        rel_thresh = float(dev_rules.get("after48hDeviationRangePct", 20.0)) / 100.0
        mode_desc = f"48h外 (当前佩戴天数: {wear_days:.2f}天 >= 门槛: {after_48h_wear_days:.1f}天)"
        logger.info(
            "Data accuracy vision uses after-48h rule",
            extra=log_context(
                "rules.data_accuracy_vision_mode",
                mode="after_48h",
                wear_days=round(wear_days, 2),
                absolute_threshold=abs_thresh,
                relative_threshold_pct=round(rel_thresh * 100, 2),
                boundary=boundary,
                pair_count=min_pairs,
                qualified_pair_count=req_qualified,
            ),
        )

    # Validate that the model analyzed enough pairs
    required_readings = 2 * min_pairs
    if not readings or len(readings) < required_readings:
        logger.error(
            "Data accuracy vision has insufficient readings",
            extra=log_context(
                "rules.data_accuracy_readings_insufficient",
                required_reading_count=required_readings,
                actual_reading_count=len(readings) if readings else 0,
            ),
        )
        return (
            "Under Review",
            "Data Deviation Review Required",
            [
                f"Insufficient readings analyzed: expected {required_readings}, got {len(readings) if readings else 0}."
            ],
        )

    # Check for invalid or unreadable images
    for idx in range(required_readings):
        r = readings[idx]
        if not r.get("is_valid", True) or r.get("value") is None:
            logger.error(
                "Data accuracy vision reading is invalid",
                extra=log_context(
                    "rules.data_accuracy_reading_invalid",
                    image_index=idx + 1,
                    device_type=r.get("device_type", "unknown"),
                ),
            )
            return (
                "Under Review",
                "Data Deviation Review Required",
                [
                    f"Image {idx + 1} ({r.get('device_type', 'unknown')}) is blurry, unreadable or invalid."
                ],
            )

    # Check for fraud/screen reproduction
    for idx in range(required_readings):
        r = readings[idx]
        if r.get("is_reproduced", False):
            logger.error(
                "Data accuracy vision detected reproduced evidence",
                extra=log_context(
                    "rules.data_accuracy_reproduced_evidence",
                    image_index=idx + 1,
                ),
            )
            return (
                "Not Eligible",
                "Fraud Detected",
                [
                    f"Evidence verification failed: Image {idx + 1} was detected as a screen reproduction (fraudulent photo)."
                ],
            )

    # Validate pairs
    pairs = []
    for i in range(min_pairs):
        pairs.append((readings[2 * i], readings[2 * i + 1], f"Group {i + 1}"))

    reasons = [f"Mode: {mode_desc}."]
    pairs_dev = []

    for r_cgm, r_bgm, label in pairs:
        # Check device types
        if r_cgm.get("device_type") != "CGM" or r_bgm.get("device_type") != "BGM":
            logger.error(
                "Data accuracy vision pair has mismatched device slots",
                extra=log_context(
                    "rules.data_accuracy_pair_mismatch", pair_label=label
                ),
            )
            return (
                "Under Review",
                "Data Deviation Review Required",
                [
                    f"Evidence verification failed: {label} slots do not match the expected CGM and BGM device layout."
                ],
            )

        cgm_raw = r_cgm["value"]
        bgm_raw = r_bgm["value"]

        # Convert to mmol/L if mg/dL
        cgm = (
            cgm_raw / 18.0
            if r_cgm.get("unit", "mmol/L").lower() in ("mg/dl", "mgdl")
            else cgm_raw
        )
        bgm = (
            bgm_raw / 18.0
            if r_bgm.get("unit", "mmol/L").lower() in ("mg/dl", "mgdl")
            else bgm_raw
        )

        # Calculate deviation
        if is_within_48h:
            # Within 48h: check absolute difference against within48hDeviationMmol
            diff = abs(cgm - bgm)
            is_deviating = diff >= abs_thresh
            log_msg = f"{label}: CGM 读数 {cgm_raw:.1f}, BGM 读数 {bgm_raw:.1f}. 实际绝对差值 {diff:.2f} mmol/L (配置偏差阈值 >= {abs_thresh:.2f}). 结果: {'异常偏差' if is_deviating else '正常'}"
            reasons.append(log_msg)
            logger.info(
                "Data accuracy vision pair evaluated",
                extra=log_context(
                    "rules.data_accuracy_pair_evaluated",
                    pair_label=label,
                    mode="within_48h",
                    diff=round(diff, 2),
                    threshold=round(abs_thresh, 2),
                    deviating=is_deviating,
                ),
            )
        else:
            # After 48h: split based on BGM level <= boundary
            if bgm <= boundary:
                diff = abs(cgm - bgm)
                is_deviating = diff >= abs_thresh
                log_msg = f"{label} (低血糖区间 <= {boundary:.1f}): CGM 读数 {cgm_raw:.1f}, BGM 读数 {bgm_raw:.1f}. 实际绝对差值 {diff:.2f} mmol/L (绝对差阈值 >= {abs_thresh:.2f}). 结果: {'异常偏差' if is_deviating else '正常'}"
                reasons.append(log_msg)
                logger.info(
                    "Data accuracy vision pair evaluated",
                    extra=log_context(
                        "rules.data_accuracy_pair_evaluated",
                        pair_label=label,
                        mode="after_48h_absolute",
                        diff=round(diff, 2),
                        threshold=round(abs_thresh, 2),
                        deviating=is_deviating,
                    ),
                )
            else:
                diff_pct = abs(cgm - bgm) / bgm
                is_deviating = diff_pct >= rel_thresh
                log_msg = f"{label} (正常/高血糖区间 > {boundary:.1f}): CGM 读数 {cgm_raw:.1f}, BGM 读数 {bgm_raw:.1f}. 实际相对偏差 {diff_pct * 100:.1f}% (相对差阈值 >= {rel_thresh * 100:.1f}%). 结果: {'异常偏差' if is_deviating else '正常'}"
                reasons.append(log_msg)
                logger.info(
                    "Data accuracy vision pair evaluated",
                    extra=log_context(
                        "rules.data_accuracy_pair_evaluated",
                        pair_label=label,
                        mode="after_48h_relative",
                        diff_pct=round(diff_pct * 100, 2),
                        threshold_pct=round(rel_thresh * 100, 2),
                        deviating=is_deviating,
                    ),
                )

        pairs_dev.append(is_deviating)

    num_deviating = sum(pairs_dev)
    if num_deviating >= req_qualified:
        logger.info(
            "Data accuracy vision verification completed",
            extra=log_context(
                "rules.data_accuracy_vision_completed",
                verdict="Replacement Eligible",
                deviating_pair_count=num_deviating,
                qualified_pair_count=req_qualified,
                pair_count=min_pairs,
            ),
        )
        return (
            "Replacement Eligible",
            "Data Deviation Detected",
            [
                f"{num_deviating} of {min_pairs} groups of CGM/BGM comparison readings confirm significant deviation (required: {req_qualified})."
            ]
            + reasons,
        )
    else:
        logger.info(
            "Data accuracy vision verification completed",
            extra=log_context(
                "rules.data_accuracy_vision_completed",
                verdict="Not Eligible",
                deviating_pair_count=num_deviating,
                qualified_pair_count=req_qualified,
                pair_count=min_pairs,
            ),
        )
        return (
            "Not Eligible",
            "Accuracy Within Normal Limits",
            [
                f"Evidence verification failed: only {num_deviating} of {min_pairs} groups show significant deviation (required: {req_qualified}). Sensor accuracy is within acceptable limits."
            ]
            + reasons,
        )
