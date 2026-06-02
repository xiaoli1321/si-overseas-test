from src.integrations.overseas_adapter import adapt_device_detail
from src.schemas.evidence import ApplicationFailureEvidence, SensorFallingOffEvidence
from src.rules.engine import run_rules
from src.rules.thresholds import default_thresholds


class DummySettings:
    def __init__(self, default_device_type="GS1"):
        self.default_device_type = default_device_type





def test_adapt_device_detail_should_use_latest_glucose_ast_as_internal_value() -> None:
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 1,
        "wearDurationHours": 24.0,
        "fallOffStatus": "未脱落",
        "glucoseInfo": [
            {"t": 1723807180000, "v": 5.0, "ast": 2},
            {"t": 1723807480000, "v": 5.2, "ast": 1},
        ],
    }
    settings = DummySettings()

    _, glucose_series, alarm = adapt_device_detail(detail, "SN-AST-LATEST", settings)

    assert [point["sensor_internal_value"] for point in glucose_series["points"]] == [
        2,
        1,
    ]
    assert alarm["latest_sensor_internal_value"] == 1
    assert alarm["latest_alarm_status"] == 0





def test_adapt_device_detail_should_preserve_timezone_without_mapping_index_to_interval() -> None:
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 1,
        "wearDurationHours": 24.0,
        "fallOffStatus": "未脱落",
        "timeZone": "Asia/Shanghai",
        "glucoseInfo": [
            {"t": "1723807180000", "v": "5.0", "i": 5, "ast": 1},
            {"t": "1723806880000", "v": "4.5", "i": "5", "ast": 1},
        ],
    }
    settings = DummySettings()

    device, glucose_series, alarm = adapt_device_detail(detail, "SN-TZ-TEST", settings)

    assert device["timeZone"] == "Asia/Shanghai"
    assert glucose_series["timezone"] == "Asia/Shanghai"
    assert [point["glucose"] for point in glucose_series["points"]] == [4.5, 5.0]
    assert all("interval_minutes" not in point for point in glucose_series["points"])
    assert [point["sensor_internal_value"] for point in glucose_series["points"]] == [1, 1]
    assert alarm["latest_alarm_status"] == 0
    assert alarm["latest_sensor_internal_value"] == 1


def test_run_rules_should_ignore_glucose_index_when_checking_curve_continuity() -> None:
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 1,
        "wearDurationHours": 24.0,
        "fallOffStatus": "未脱落",
        "timeZone": "UTC",
        "glucoseInfo": [
            {"t": "1717200000000", "v": "2.7", "i": 60, "ast": 1},
            {"t": "1717201800000", "v": "2.7", "i": 65, "ast": 1},
            {"t": "1717203600000", "v": "2.7", "i": 70, "ast": 1},
            {"t": "1717243200000", "v": "2.7", "i": 730, "ast": 1},
            {"t": "1717245000000", "v": "2.7", "i": 735, "ast": 1},
            {"t": "1717246800000", "v": "2.7", "i": 740, "ast": 1},
        ],
    }
    settings = DummySettings()
    device, glucose_series, alarm = adapt_device_detail(detail, "SN-GAP-TEST", settings)

    result = run_rules(
        fault_category="Data accuracy",
        device=device,
        glucose_series=glucose_series,
        alarm=alarm,
        threshold_config=default_thresholds(),
    )

    assert result.verdict == "Under Review"
    assert result.fault_subtype == "Data Deviation Review Required"

def test_rules_integration_sudden_fall_off() -> None:
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 2,
        "wearDurationHours": 120.0, # 5天 < 14天阈值
        "fallOffStatus": "已脱落",
        "glucoseInfo": []
    }

    settings = DummySettings()
    device, glucose_series, alarm = adapt_device_detail(detail, "240112NNG9672DAE58", settings)

    # 运行脱落换货规则
    result = run_rules(
        fault_category="Sensor falling off",
        device=device,
        glucose_series=glucose_series,
        alarm=alarm,
        threshold_config=default_thresholds(),
    )
    assert result.verdict == "Replacement Eligible"
    assert result.fault_subtype == "Sudden Fall Off"


def test_adapt_device_detail_timezone_conversion() -> None:
    # 模拟包含特定时区的 deviceDetail 接口数据
    # 激活时间：1723805564000 毫秒 (2024-08-16 10:52:44 UTC)
    # 血糖点时间：1723806880000 毫秒 (2024-08-16 11:14:40 UTC)
    # 异常时间：1723806000000 毫秒 (2024-08-16 11:00:00 UTC)
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 4,  # 异常状态
        "wearDurationHours": 24.0,
        "fallOffStatus": "未脱落",
        "timeZone": "Asia/Shanghai",  # UTC+8
        "abnormalTime": 1723806000000,
        "glucoseInfo": [
            {"t": "1723806880000", "v": "5.0", "i": 5, "ast": 1},
        ],
    }
    settings = DummySettings()
    device, glucose_series, alarm = adapt_device_detail(detail, "SN-TZ-CONV", settings)

    # 验证时区正确保存
    assert device["timeZone"] == "Asia/Shanghai"
    assert glucose_series["timezone"] == "Asia/Shanghai"

    # 验证激活时间转换为当地时间 (UTC+8)
    # 10:52:44 UTC + 8 hours = 18:52:44
    assert device["activatedAt"] == "2024-08-16T18:52:44+08:00"

    # 验证血糖点时间转换为当地时间 (UTC+8)
    # 11:14:40 UTC + 8 hours = 19:14:40
    assert glucose_series["points"][0]["timestamp"] == "2024-08-16T19:14:40+08:00"

    # 验证最晚数据上传时间 (UTC+8)
    assert device["lastDataAt"] == "2024-08-16T19:14:40+08:00"

    # 验证最新告警时间 (UTC+8)
    # 11:00:00 UTC + 8 hours = 19:00:00
    assert alarm["latest_sensor_alert"] == "2024-08-16T19:00:00+08:00"


def test_adapt_device_detail_timezone_offset_conversion() -> None:
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 1,
        "wearDurationHours": 24.0,
        "fallOffStatus": "未脱落",
        "timeZone": "+05:30",  # UTC+5.5
        "glucoseInfo": [
            {"t": "1723806880000", "v": "5.0", "i": 5, "ast": 1},
        ],
    }
    settings = DummySettings()
    device, glucose_series, alarm = adapt_device_detail(detail, "SN-TZ-OFFSET", settings)

    # 验证激活时间转换为当地时间 (UTC+5.5)
    # 10:52:44 UTC + 5h30m = 16:22:44
    assert device["activatedAt"] == "2024-08-16T16:22:44+05:30"


def test_device_snapshot_preserves_timezone_adjusted_activation_time() -> None:
    evidence = SensorFallingOffEvidence.model_validate(
        {
            "matched_rules": ["sensor_falling_off.sudden_fall_off"],
            "files_metadata": [],
            "device": {
                "sn": "SN-TZ-CONV",
                "type": "AA2506QHHR",
                "device_type": "GS1",
                "wear_days": 1.0,
                "wearHours": 0.27,
                "device_status": 1,
                "fall_off_status": "fallen_off",
                "status": "wearing",
                "activatedAt": "2024-08-16T18:52:44+08:00",
                "lastDataAt": "2024-08-16T19:14:40+08:00",
                "timeZone": "Asia/Shanghai",
            },
        }
    )

    assert evidence.device.activatedAt == "2024-08-16T18:52:44+08:00"
    assert evidence.device.timeZone == "Asia/Shanghai"
    assert evidence.device.type == "AA2506QHHR"
    assert evidence.device.wearHours == 0.27


def test_application_failure_evidence_preserves_device_activation_time() -> None:
    evidence = ApplicationFailureEvidence.model_validate(
        {
            "matched_rules": ["application_failure.assembly_failed"],
            "files_metadata": [],
            "file_ids": ["file-1", "file-2"],
            "vision": None,
            "device": {
                "sn": "SN-IMPLANT",
                "device_type": "GS1",
                "wear_days": 1.0,
                "device_status": 1,
                "fall_off_status": "not_fallen_off",
                "status": "wearing",
                "activatedAt": "2024-08-16T18:52:44+08:00",
                "lastDataAt": "2024-08-16T19:14:40+08:00",
                "timeZone": "Asia/Shanghai",
            },
        }
    )

    assert evidence.device is not None
    assert evidence.device.activatedAt == "2024-08-16T18:52:44+08:00"


def test_adapt_device_detail_fall_off_status_variants() -> None:
    settings = DummySettings()

    # 1. Test "脱落"
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 1,
        "fallOffStatus": "脱落",
    }
    device, _, _ = adapt_device_detail(detail, "SN-TEST", settings)
    assert device["fall_off_status"] == "fallen_off"

    # 2. Test "已脱落"
    detail["fallOffStatus"] = "已脱落"
    device, _, _ = adapt_device_detail(detail, "SN-TEST", settings)
    assert device["fall_off_status"] == "fallen_off"

    # 3. Test "疑似脱落"
    detail["fallOffStatus"] = "疑似脱落"
    device, _, _ = adapt_device_detail(detail, "SN-TEST", settings)
    assert device["fall_off_status"] == "suspected_fall_off"
    
    # 4. Test "未脱落"
    detail["fallOffStatus"] = "未脱落"
    device, _, _ = adapt_device_detail(detail, "SN-TEST", settings)
    assert device["fall_off_status"] == "not_fallen_off"


def test_device_status_and_type_adaptation() -> None:
    # 验证 8 种整数状态被精准映射到字符串状态
    expected_statuses = {
        0: "not_activated",
        1: "wearing",
        2: "deactivated",
        3: "initializing",
        4: "abnormal",
        5: "initialization_failed",
        6: "temporarily_abnormal",
        7: "expired"
    }
    
    for raw_status, expected_str in expected_statuses.items():
        detail_with_name = {
            "deviceName": "AA2601G4HA",
            "enableTime": 1723805564000,
            "status": raw_status,
            "fallOffStatus": "未脱落",
        }
        # 传入 custom settings，验证 default_device_type 起作用
        settings = DummySettings(default_device_type="GS_CONFIGURED")
        
        # 验证 device["type"] 为 deviceName，device["device_type"] 始终为 settings.default_device_type
        device, _, _ = adapt_device_detail(detail_with_name, "REAL_SN_12345", settings)
        assert device["status"] == expected_str
        assert device["type"] == "AA2601G4HA"
        assert device["device_type"] == "GS_CONFIGURED"

        device2, _, _ = adapt_device_detail(detail_with_name, "TESGS2ABCDE", settings)
        assert device2["type"] == "AA2601G4HA"
        assert device2["device_type"] == "GS_CONFIGURED"


def test_adapt_device_detail_abnormal_duration_capped() -> None:
    # 模拟一个历史异常设备，已经超过佩戴时间。
    # 激活时间：1723805564000 (2024-08-16 10:52:44 UTC)
    # 佩戴时间：24.0 小时 (1.0 天) -> 结束时间为 2024-08-17 10:52:44 UTC
    # 异常发生时间：1723806000000 (2024-08-16 11:00:00 UTC，即激活后约 7 分钟)
    # 计算得到的异常时间：应该限制在佩戴结束时间 2024-08-17 10:52:44 - 异常发生时间 11:00:00 = 23 小时 52 分 44 秒 = 1432 分钟 (大约 23.88 小时)
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 4,
        "wearDurationHours": 24.0,
        "fallOffStatus": "未脱落",
        "abnormalTime": 1723806000000,
    }
    settings = DummySettings()
    device, _, alarm = adapt_device_detail(detail, "SN-CAPPED-TEST", settings)

    # 1432 分钟
    assert alarm["abnormal_duration_minutes"] == 1432


def test_adapt_device_detail_abnormal_duration_active() -> None:
    # 模拟一个正在佩戴的异常设备。
    # 激活时间：当前时间前 2 小时
    # 佩戴时间：14 天 (336.0 小时) -> 远大于当前时间，不会被上限拦截
    # 异常时间：当前时间前 1 小时 (60 分钟)
    import time
    now_ts = time.time()
    detail = {
        "deviceName": "GS1",
        "enableTime": int((now_ts - 7200) * 1000), # 2 小时前
        "status": 4,
        "wearDurationHours": 336.0, # 14 天
        "fallOffStatus": "未脱落",
        "abnormalTime": int((now_ts - 3600) * 1000), # 1 小时前
    }
    settings = DummySettings()
    device, _, alarm = adapt_device_detail(detail, "SN-ACTIVE-TEST", settings)

    # 应该在 60 分钟左右（允许 1 分钟误差）
    assert abs(alarm["abnormal_duration_minutes"] - 60) <= 1


def test_adapt_device_detail_wear_hours_fractional() -> None:
    # 模拟一个佩戴了 16.2 分钟 (0.27 小时) 的设备，验证 wearHours 保留了浮点数精度
    detail = {
        "deviceName": "GS1",
        "enableTime": 1723805564000,
        "status": 4,
        "wearDurationHours": 0.27,
        "fallOffStatus": "未脱落",
        "abnormalTime": 1723806000000,
    }
    settings = DummySettings()
    device, _, _ = adapt_device_detail(detail, "SN-FRACTIONAL-TEST", settings)

    assert device["wearDays"] == 0
    assert device["wearHours"] == 0.27
