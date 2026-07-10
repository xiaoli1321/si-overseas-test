from copy import deepcopy
import math
from typing import Any

DATA_DEVIATION_REQUIRED_PAIR_COUNT = 2
APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT = 2

DEFAULT_THRESHOLD_PROFILE: dict[str, Any] = {
    "version": 1,
    "savedAt": None,
    "rules": {
        "inaccuracy": {
            "lowPersist": {"belowMmol": 2.8, "minHours": 4, "max24hMmol": 7.8},
            "noFluctuation": {"floorMmol": 4.5, "minHours": 8, "maxSwingMmol": 1.0},
            "jump": {"deltaMmol": 3.0, "consecutive": 3},
            "deviation": {
                "within48hDeviationMmol": 7.0,
                "within48hPairCount": 2,
                "within48hQualifiedPairCount": 2,
                "after48hDeviationRangePct": 20,
                "after48hDeviationRangeBoundary": 4.4,
                "after48hDeviationMmol": 0.83,
                "after48hPairCount": 2,
                "after48hQualifiedPairCount": 2,
                "after48hWearDays": 2,
            },
        },
        # warmupMinutes: 设备激活后预热时长阈值（分钟），status=4 结合 ast 内部值区分初始化/使用期异常，status=5 在此时长内判定为初始化异常
        # waitingRecoveryHours: 传感器异常等待恢复时长阈值（小时），status=1+ast=2 超过此时长判定为恢复可能性很小
        "deviceAbnormal": {
            "wearDays": 0,
            "temporaryAbnormalHours": 3,
            "warmupMinutes": 60,
            "waitingRecoveryHours": 3,
        },
        "detachment": {"detachedStatusValue": 1, "wearDays": 14},
        "applicationFailure": {
            "photoCount": 2,
            "afterSalesScore": 7.0,
            "manualReviewScore": 5.0,
        },
    },
}


def default_thresholds() -> dict[str, Any]:
    from src.core.config import get_settings

    profile = get_settings().default_threshold_profile
    if profile:
        return normalize_threshold_profile(profile)
    return normalize_threshold_profile(DEFAULT_THRESHOLD_PROFILE)


def openapi_threshold_template() -> dict[str, Any]:
    """Return the copy-and-edit threshold template exposed to OpenAPI clients."""
    profile = default_thresholds()
    profile.pop("version", None)
    profile.pop("savedAt", None)

    rules = profile.get("rules", {})
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
    return profile


def normalize_threshold_profile(profile_or_config: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(profile_or_config)
    rules = config.get("rules")
    if not isinstance(rules, dict):
        return config

    inaccuracy = rules.get("inaccuracy")
    if isinstance(inaccuracy, dict):
        deviation = inaccuracy.get("deviation")
        if isinstance(deviation, dict):
            # Evidence collection counts are a product rule, not configurable
            # thresholds.  Normalizing old stored profiles here prevents a
            # historical value from changing today's four-image requirement.
            deviation["within48hPairCount"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT
            deviation["within48hQualifiedPairCount"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT
            deviation["after48hPairCount"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT
            deviation["after48hQualifiedPairCount"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT

    application = rules.get("applicationFailure")
    if isinstance(application, dict):
        application["photoCount"] = APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT

    return config


def to_rule_config(profile_or_config: dict[str, Any]) -> dict[str, Any]:
    if "data_accuracy" in profile_or_config:
        # Some callers (and older records) already hold the internal rule
        # shape. Keep that compatibility path, while still enforcing the same
        # system-managed evidence requirement at execution time.
        config = deepcopy(profile_or_config)
        deviation = config.get("data_accuracy", {}).get("data_deviation")
        if isinstance(deviation, dict):
            deviation["min_pairs"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT
            deviation["within48hPairCount"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT
            deviation["within48hQualifiedPairCount"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT
            deviation["after48hPairCount"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT
            deviation["after48hQualifiedPairCount"] = DATA_DEVIATION_REQUIRED_PAIR_COUNT
        application = config.get("application_failure")
        if isinstance(application, dict):
            application["min_images"] = APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT
        return config

    normalized = normalize_threshold_profile(profile_or_config)
    rules = normalized.get("rules", normalized)
    inaccuracy = rules["inaccuracy"]
    abnormal = rules.get("deviceAbnormal", {})
    detachment = rules.get("detachment", {})
    application = rules.get("applicationFailure", {})

    return {
        "data_accuracy": {
            "persistently_low": {
                "max_glucose_24h": inaccuracy["lowPersist"]["max24hMmol"],
                "low_value": inaccuracy["lowPersist"]["belowMmol"],
                "duration_hours": inaccuracy["lowPersist"]["minHours"],
            },
            "no_fluctuation": {
                "max_value": inaccuracy["noFluctuation"]["floorMmol"],
                "max_delta": inaccuracy["noFluctuation"]["maxSwingMmol"],
                "duration_hours": inaccuracy["noFluctuation"]["minHours"],
            },
            "sudden_fluctuation": {
                "delta": inaccuracy["jump"]["deltaMmol"],
                "count": inaccuracy["jump"]["consecutive"],
            },
            "data_deviation": {
                "min_pairs": inaccuracy.get("deviation", {}).get(
                    "within48hPairCount", 2
                ),
                "deviation_mmol": inaccuracy.get("deviation", {}).get(
                    "within48hDeviationMmol", 7.0
                ),
                "within48hDeviationMmol": inaccuracy.get("deviation", {}).get(
                    "within48hDeviationMmol", 7.0
                ),
                "within48hPairCount": inaccuracy.get("deviation", {}).get(
                    "within48hPairCount", 2
                ),
                "within48hQualifiedPairCount": inaccuracy.get("deviation", {}).get(
                    "within48hQualifiedPairCount", 2
                ),
                "after48hDeviationRangePct": inaccuracy.get("deviation", {}).get(
                    "after48hDeviationRangePct", 20.0
                ),
                "after48hDeviationRangeBoundary": inaccuracy.get("deviation", {}).get(
                    "after48hDeviationRangeBoundary", 4.4
                ),
                "after48hDeviationMmol": inaccuracy.get("deviation", {}).get(
                    "after48hDeviationMmol", 0.83
                ),
                "after48hPairCount": inaccuracy.get("deviation", {}).get(
                    "after48hPairCount", 2
                ),
                "after48hQualifiedPairCount": inaccuracy.get("deviation", {}).get(
                    "after48hQualifiedPairCount", 2
                ),
                "after48hWearDays": inaccuracy.get("deviation", {}).get(
                    "after48hWearDays", 2
                ),
            },
        },
        "sensor_falling_off": {"wear_days_limit": detachment.get("wearDays", 14)},
        "sensor_abnormal": {
            "temporary_abnormal_hours": abnormal.get("temporaryAbnormalHours", 3),
            "warmup_minutes": abnormal.get("warmupMinutes", 60),
            "waiting_recovery_hours": abnormal.get("waitingRecoveryHours", 3),
        },
        "application_failure": {
            "min_images": application.get("photoCount", 2),
            "min_score": application.get("manualReviewScore", 5),
            "after_sales_score": application.get("afterSalesScore", 8),
        },
    }


def validate_threshold_profile(profile_or_config: dict[str, Any]) -> dict[str, Any]:
    """Validate an externally supplied profile before it becomes an async task."""
    if not isinstance(profile_or_config, dict):
        raise ValueError("thresholdConfig must be an object")

    # Open API callers may omit these fields.  Supplying a different value is
    # rejected instead of silently accepting a setting that can never apply.
    rules = profile_or_config.get("rules")
    if isinstance(rules, dict):
        deviation = rules.get("inaccuracy", {}).get("deviation", {})
        fixed_deviation_fields = (
            "within48hPairCount",
            "within48hQualifiedPairCount",
            "after48hPairCount",
            "after48hQualifiedPairCount",
        )
        if isinstance(deviation, dict):
            for field in fixed_deviation_fields:
                if field in deviation and deviation[field] != DATA_DEVIATION_REQUIRED_PAIR_COUNT:
                    raise ValueError(f"inaccuracy.deviation.{field} is system-managed and fixed at 2")
        application = rules.get("applicationFailure", {})
        if (
            isinstance(application, dict)
            and "photoCount" in application
            and application["photoCount"] != APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT
        ):
            raise ValueError("applicationFailure.photoCount is system-managed and fixed at 2")

    normalized = normalize_threshold_profile(profile_or_config)
    try:
        rule_config = to_rule_config(normalized)
    except (KeyError, TypeError) as exc:
        raise ValueError("thresholdConfig is missing required rule fields") from exc

    def require_finite_numbers(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                require_finite_numbers(nested)
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("thresholdConfig rule values must be numbers")
        if not math.isfinite(float(value)):
            raise ValueError("thresholdConfig rule values must be finite")

    require_finite_numbers(rule_config)
    application = rule_config["application_failure"]
    if application["min_images"] < 0:
        raise ValueError("applicationFailure.photoCount cannot be negative")
    if not 0 <= application["min_score"] <= application["after_sales_score"] <= 10:
        raise ValueError("applicationFailure scores must be between 0 and 10")
    return normalized


def frontend_threshold_profile(
    config: dict[str, Any], version: int, saved_at: str | None
) -> dict[str, Any]:
    if "rules" in config:
        profile = normalize_threshold_profile(config)
    else:
        profile = default_thresholds()
    profile["version"] = version
    profile["savedAt"] = saved_at
    return profile
