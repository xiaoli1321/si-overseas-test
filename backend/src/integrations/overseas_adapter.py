import re
from datetime import datetime, UTC, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any
import logging

logger = logging.getLogger(__name__)


STATUS_MAP = {
    0: "not_activated",  # 未激活
    1: "wearing",  # 使用中
    2: "deactivated",  # 已停用
    3: "initializing",  # 初始化
    4: "abnormal",  # 异常
    5: "initialization_failed",  # 初始化异常
    6: "temporarily_abnormal",  # 暂时异常
    7: "expired",  # 已过期
}


def _resolve_timezone(raw_timezone: Any) -> tzinfo:
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


def adapt_device_detail(
    device_detail: dict[str, Any],
    serial_no: str,
    settings: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    将海外 deviceDetail 接口返回的单一数据结构，
    转换为规则引擎 run_rules 所需的三个入参数据格式：(device, glucose_series, alarm)

    deviceDetail 返回结构示例:
    {
        "index": 210,
        "blueToothNum": "62SE457C",
        "deviceName": "AA250862SE",
        "enableTime": "1762928700552.000000",
        "status": 1,
        "abnormalTime": null,
        "timeZone": null,
        "wearDurationHours": 3.5,
        "fallOffStatus": "未脱落",
        "glucoseInfo": [
            {"t": "1762932240552", "v": "19", "i": 60, "s": -1, "ast": 1},
            ...
        ]
    }
    """
    # ── 1. 基础设备信息 ──────────────────────────────────────────

    device_name = device_detail.get("deviceName", "GS1")
    enable_time_raw = device_detail.get("enableTime")
    device_timezone = device_detail.get("timeZone")
    tz = _resolve_timezone(device_timezone)

    # 激活时间转换
    activated_at = ""
    enable_ts = None
    if enable_time_raw:
        try:
            ts = float(str(enable_time_raw).strip())
            if ts > 10_000_000_000:  # 毫秒戳
                ts = ts / 1000.0
            activated_at = datetime.fromtimestamp(ts, tz).isoformat()
            enable_ts = ts
        except Exception as exc:
            logger.error("Failed to parse enableTime '%s': %s", enable_time_raw, exc)
            activated_at = str(enable_time_raw)

    # 佩戴时间 (优先使用 wearDurationHours, 否则用 index 分钟换算)
    wear_hours_raw = device_detail.get("wearDurationHours")
    if wear_hours_raw is not None:
        wear_days = float(wear_hours_raw) / 24.0
    else:
        index_val = device_detail.get("index", 0)
        wear_days = float(index_val) / 1440.0

    # 设备状态 (0: 未激活, 1: 使用中, 2: 已停用, 3: 初始化, 4: 异常, 5: 初始化异常, 6: 暂时异常, 7: 已过期)
    raw_status = device_detail.get("status")
    device_status = int(raw_status) if raw_status is not None else 1

    # 脱落状态映射
    fall_off_str = device_detail.get("fallOffStatus", "")
    if (
        "已脱落" in fall_off_str
        or fall_off_str == "fallen_off"
        or fall_off_str == "脱落"
    ):
        fall_off_status = "fallen_off"
    elif "疑似脱落" in fall_off_str or fall_off_str == "suspected_fall_off":
        fall_off_status = "suspected_fall_off"
    else:
        fall_off_status = "not_fallen_off"

    # 业务探头型号，统一使用配置中的默认型号（如 "GS1"）
    default_type = getattr(settings, "default_device_type", "GS1")

    # 物理设备名/板卡号，使用接口返回的真实 deviceName
    device_name = device_detail.get("deviceName", default_type)

    device = {
        "sn": serial_no,
        "type": device_name,  # 对应前端详细页的 Probe code / type
        "status": STATUS_MAP.get(device_status, "wearing"),
        "activatedAt": activated_at,
        "timeZone": device_timezone,
        "wearDays": int(wear_days),
        "wearHours": round((wear_days - int(wear_days)) * 24, 2),
        "lastDataAt": "",  # 稍后从 glucoseInfo 推算
        "hasServiceCard": None,  # 海外 deviceDetail 接口不返回服务卡信息
        "fall_off_status": fall_off_status,
        "device_status": device_status,
        "wear_days": wear_days,
        "device_type": default_type,  # 对应业务规则判定和列表页的 Type
        "fault": None,  # 海外 deviceDetail 接口不返回 fault 信息
    }

    # ── 2. 映射血糖数据序列 ──────────────────────────────────────

    raw_points = device_detail.get("glucoseInfo") or []
    points = []
    latest_alarm_status = 0
    latest_t = None
    latest_sensor_internal_value = 0

    for p in raw_points:
        # deviceDetail 返回的 t 和 v 都是字符串
        t_raw = p.get("t", 0)
        v_raw = p.get("v")
        ast_val = _safe_int(p.get("ast", 0), default=0)

        if v_raw is None:
            continue

        try:
            t_val = int(float(str(t_raw)))
        except (ValueError, TypeError):
            t_val = 0

        if latest_t is None or t_val > latest_t:
            latest_t = t_val
            latest_sensor_internal_value = ast_val

        # 转换时间戳为 ISO 格式
        try:
            timestamp_str = datetime.fromtimestamp(t_val / 1000.0, tz).isoformat()
        except Exception:
            timestamp_str = ""

        # ast is the overseas sensor internal value; ast == 2 represents an abnormal alarm.
        is_abnormal_alarm = ast_val == 2

        # 血糖值已是 mmol/L，无需换算
        try:
            glucose_val = float(str(v_raw))
        except (ValueError, TypeError):
            glucose_val = 0.0

        point = {
            "glucose": glucose_val,
            "timestamp": timestamp_str,
            "alarm_status": 2 if is_abnormal_alarm else 0,
            "sensor_internal_value": ast_val,
            "effective": bool(p.get("effective", True)),
        }

        points.append(point)

    # 按时间升序排序
    points.sort(key=lambda x: x["timestamp"])
    latest_alarm_status = 2 if latest_sensor_internal_value == 2 else 0

    glucose_series = {"points": points, "timezone": device_timezone}

    # 更新设备最晚上传时间
    if latest_t:
        try:
            device["lastDataAt"] = datetime.fromtimestamp(
                latest_t / 1000.0, tz
            ).isoformat()
        except Exception:
            pass

    # ── 3. 映射报警对象 ──────────────────────────────────────────

    # 从 abnormalTime 推算异常持续时间
    abnormal_time_raw = device_detail.get("abnormalTime")
    abnormal_duration = 0.0
    latest_sensor_alert = ""

    if abnormal_time_raw is not None:
        try:
            abnormal_ts = float(str(abnormal_time_raw).strip())
            if abnormal_ts > 10_000_000_000:
                abnormal_ts = abnormal_ts / 1000.0
            latest_sensor_alert = datetime.fromtimestamp(abnormal_ts, tz).isoformat()

            # 计算从异常开始到现在的持续时间（分钟），以设备佩戴结束时间或当前时间为上限
            now_ts = datetime.now(UTC).timestamp()
            end_ts = now_ts
            if enable_ts is not None:
                session_end_ts = enable_ts + (wear_days * 24.0 * 3600.0)
                if now_ts > session_end_ts:
                    end_ts = session_end_ts

            abnormal_duration = (end_ts - abnormal_ts) / 60.0
            if abnormal_duration < 0:
                abnormal_duration = 0.0
        except Exception as exc:
            logger.error(
                "Failed to parse abnormalTime '%s': %s", abnormal_time_raw, exc
            )
    elif device_status in (4, 5, 6) and points:
        # 如果没有 abnormalTime 但设备状态异常，用佩戴总时长兜底
        abnormal_duration = wear_days * 1440.0

    alarm = {
        "latest_alarm_status": latest_alarm_status,
        "latest_sensor_internal_value": latest_sensor_internal_value,
        "abnormal_duration_minutes": int(abnormal_duration),
        "latest_sensor_alert": latest_sensor_alert,
    }

    return device, glucose_series, alarm


# ── 保留旧接口兼容（被 mock 流程使用时的适配） ────────────────────


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default
