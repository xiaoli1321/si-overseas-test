from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.exceptions import InvalidParamsError, NotFoundError
from src.integrations.overseas_client import is_bluetooth_name, validate_bluetooth_name

CUSTOMER_EMAIL = "christest@sibionics.com"
NOW = datetime(2026, 4, 18, 12, 0, tzinfo=UTC)


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def _device(
    sn: str,
    status: str,
    activated_at: str,
    wear_days: int,
    wear_hours: int,
    last_data_at: str,
    has_service_card: bool,
    category: str,
    subtype: str,
    expected: str,
    notes: str,
    device_name: str = "",
) -> dict[str, Any]:
    status_code = 1
    if status == "abnormal":
        status_code = 6 if "Temporary" in subtype else 4
    if "Initialization" in subtype:
        status_code = 5
    fall_off_status = (
        "fallen_off" if category == "Sensor falling off" else "not_fallen_off"
    )
    return {
        "email": CUSTOMER_EMAIL,
        "sn": sn,
        "type": "GS1",
        "status": status,
        "activatedAt": activated_at,
        "wearDays": wear_days,
        "wearHours": wear_hours,
        "lastDataAt": last_data_at,
        "hasServiceCard": has_service_card,
        "fault": {
            "faultCategory": category,
            "faultSubtype": subtype,
            "expectedAfterSales": expected,
            "notes": notes,
        },
        "deviceName": device_name,  # 蓝牙名称（AA 开头）
        "serial_no": sn,
        "device_type": "GS1",
        "device_status": status_code,
        "activation_status": "activated",
        "activated_at": _dt(activated_at),
        "wear_days": wear_days + wear_hours / 24,
        "latest_upload_at": _dt(last_data_at),
        "service_card_status": "valid" if has_service_card else "missing",
        "fall_off_status": fall_off_status,
    }


MOCK_DEVICES: dict[str, dict[str, Any]] = {
    item["sn"]: item
    for item in [
        _device(
            "P2251212806JND44",
            "abnormal",
            "2026-04-12 09:30",
            6,
            5,
            "2026-04-18 08:12",
            True,
            "Data accuracy",
            "Persistent Low Glucose Detected",
            "Replacement Eligible",
            "Curve stays below the low-glucose rule window with an active service card.",
            device_name="AA250862SE",
        ),
        _device(
            "P2251212814SWL27",
            "abnormal",
            "2026-04-13 10:10",
            5,
            2,
            "2026-04-18 07:55",
            False,
            "Data accuracy",
            "Persistent Low Glucose Detected",
            "Not Eligible",
            "Persistent low pattern detected but no service card on file blocks replacement.",
            device_name="AA250862SE",
        ),
        _device(
            "P2251212807KPD52",
            "abnormal",
            "2026-04-10 11:00",
            8,
            2,
            "2026-04-18 07:42",
            True,
            "Data accuracy",
            "No Fluctuation Detected",
            "Replacement Eligible",
            "Flat glucose curve exceeds the no-fluctuation duration rule.",
            device_name="AA260901AB",
        ),
        _device(
            "P2251212815TXM35",
            "abnormal",
            "2026-04-17 18:30",
            0,
            14,
            "2026-04-18 08:20",
            True,
            "Data accuracy",
            "No Fluctuation Detected",
            "Not Eligible",
            "Flat curve duration is below the no-fluctuation replacement window.",
        ),
        _device(
            "P2251212816UYN48",
            "abnormal",
            "2026-04-11 16:45",
            6,
            18,
            "2026-04-18 10:30",
            True,
            "Data accuracy",
            "Glucose Jump Pattern Detected",
            "Replacement Eligible",
            "Repeated jump pattern with active service card qualifies for replacement.",
        ),
        _device(
            "P2251212808LQE63",
            "abnormal",
            "2026-04-14 15:10",
            4,
            3,
            "2026-04-18 09:05",
            False,
            "Data accuracy",
            "Glucose Jump Pattern Detected",
            "Not Eligible",
            "Jump pattern falls outside the replacement rule window.",
        ),
        _device(
            "P2251212823BFV10",
            "wearing",
            "2026-04-18 05:20",
            0,
            6,
            "2026-04-18 11:25",
            True,
            "Data accuracy",
            "Data Deviation Detected",
            "Replacement Eligible",
            "Two paired CGM/BGM image groups confirm the data-deviation replacement path with an active service card.",
        ),
        _device(
            "P2251212824CGW21",
            "wearing",
            "2026-04-18 06:40",
            0,
            5,
            "2026-04-18 11:45",
            False,
            "Data accuracy",
            "Data Deviation Detected",
            "Not Eligible",
            "Two paired CGM/BGM image groups show data deviation, but no service card on file blocks replacement.",
        ),
        _device(
            "P2251212809MRF71",
            "abnormal",
            "2026-04-11 08:45",
            7,
            4,
            "2026-04-17 19:20",
            True,
            "Sensor falling off",
            "Fall-out detected",
            "Replacement Eligible",
            "Telemetry and abnormal status match the fall-out replacement path.",
        ),
        _device(
            "P2251212817VZP56",
            "abnormal",
            "2026-04-02 09:00",
            15,
            1,
            "2026-04-18 06:10",
            False,
            "Sensor falling off",
            "Fall-out detected",
            "Not Eligible",
            "Fall-out reported after the wear window expired and no service card on file.",
        ),
        _device(
            "P2251212810NSG88",
            "abnormal",
            "2026-04-18 07:40",
            0,
            1,
            "2026-04-18 08:41",
            True,
            "Sensor Abnormal",
            "Initialization abnormality",
            "Replacement Eligible",
            "Abnormal status occurs during initialization with an active service card.",
        ),
        _device(
            "P2251212818WAQ64",
            "abnormal",
            "2026-04-18 06:15",
            0,
            2,
            "2026-04-18 08:20",
            False,
            "Sensor Abnormal",
            "Initialization abnormality",
            "Not Eligible",
            "Initialization abnormality without a service card blocks replacement.",
        ),
        _device(
            "P2251212819XBR72",
            "abnormal",
            "2026-04-15 13:20",
            3,
            0,
            "2026-04-18 09:18",
            True,
            "Sensor Abnormal",
            "Probe failure",
            "Replacement Eligible",
            "Probe failure confirmed with an active service card on file.",
        ),
        _device(
            "P2251212811PTH96",
            "abnormal",
            "2026-04-16 10:20",
            2,
            6,
            "2026-04-18 06:55",
            False,
            "Sensor Abnormal",
            "Probe failure",
            "Not Eligible",
            "Probe failure with no service card on file blocks replacement.",
        ),
        _device(
            "P2251212820YCS85",
            "abnormal",
            "2026-04-17 22:00",
            0,
            11,
            "2026-04-18 09:02",
            True,
            "Sensor Abnormal",
            "Temporary sensor abnormality",
            "Replacement Eligible",
            "Temporary abnormality persisted past the 3-hour observation window and escalated to replacement.",
        ),
        _device(
            "P2251212821ZDT93",
            "abnormal",
            "2026-04-18 04:30",
            0,
            4,
            "2026-04-18 08:35",
            True,
            "Sensor Abnormal",
            "Temporary sensor abnormality",
            "Not Eligible",
            "Temporary abnormality cleared within the 3-hour window, no replacement needed.",
        ),
        _device(
            "P2251212813RVK19",
            "wearing",
            "2026-04-18 12:00",
            0,
            0,
            "2026-04-18 12:02",
            True,
            "Application failure",
            "Application failure",
            "Replacement Eligible",
            "Photo evidence confirms the application-failure replacement path.",
        ),
        _device(
            "P2251212822AEU09",
            "wearing",
            "2026-04-18 09:15",
            0,
            2,
            "2026-04-18 11:20",
            False,
            "Application failure",
            "Application failure",
            "Not Eligible",
            "Application failure photo evidence does not meet the replacement rule.",
        ),
    ]
}


def frontend_device(device: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": device["email"],
        "sn": device["sn"],
        "type": device["type"],
        "status": device["status"],
        "activatedAt": device["activatedAt"],
        "wearDays": device["wearDays"],
        "wearHours": device["wearHours"],
        "lastDataAt": device["lastDataAt"],
        "hasServiceCard": device["hasServiceCard"],
        "fault": device["fault"],
    }


class MockCGMClient:
    async def get_device(self, serial_no: str) -> dict[str, Any] | list[dict[str, Any]]:
        """
        按 SN 或蓝牙名称查询设备。
        - SN：返回单个 dict
        - 蓝牙名称（AA 开头）：校验格式，返回 list[dict]
        """
        term = serial_no.strip().upper()
        if is_bluetooth_name(term):
            validated = validate_bluetooth_name(term)
            results = await self.get_devices_by_name(validated)
            return [r[0] for r in results]
        device = MOCK_DEVICES.get(term)
        if not device:
            raise NotFoundError(f"Device {serial_no} was not found.")
        return dict(device)

    async def get_devices_by_name(
        self, device_name: str
    ) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
        """
        按蓝牙名称查询，返回匹配的所有设备的适配数据元组列表 (device, glucose, alarm)。
        用于当真实接口不可用时的 fallback mock。
        """
        name_upper = device_name.strip().upper()
        matched = [
            sn
            for sn, dev in MOCK_DEVICES.items()
            if dev.get("deviceName", "").upper() == name_upper
        ]
        if not matched:
            raise NotFoundError(f"No devices found for Bluetooth name '{device_name}'.")

        results: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for sn in matched:
            device_dict = dict(MOCK_DEVICES[sn])
            glucose = await self.get_glucose_series(sn)
            alarm = await self.get_latest_alarm(sn)
            # 将 datetime 转换为 ISO 字符串，与 adapt_device_detail 输出一致
            adapted_glucose = {
                "points": [
                    {
                        "glucose": p["glucose"],
                        "timestamp": p["timestamp"].isoformat()
                        if isinstance(p["timestamp"], datetime)
                        else str(p["timestamp"]),
                        "alarm_status": p["alarm_status"],
                        "effective": p.get("effective", True),
                    }
                    for p in glucose.get("points", [])
                ],
                "timezone": glucose.get("timezone", "UTC"),
            }
            adapted_alarm = {
                "latest_alarm_status": alarm["latest_alarm_status"],
                "abnormal_duration_minutes": alarm["abnormal_duration_minutes"],
                "latest_sensor_alert": alarm["abnormal_started_at"].isoformat()
                if isinstance(alarm.get("abnormal_started_at"), datetime)
                else str(alarm.get("abnormal_started_at", "")),
            }
            results.append((device_dict, adapted_glucose, adapted_alarm))
        return results

    async def search_devices(self, keyword: str) -> list[dict[str, Any]]:
        """
        搜索设备。蓝牙名称精确匹配，返回 list；SN 指定含内容匹配。
        """
        needle = keyword.strip().upper()
        if not needle:
            return []
        if is_bluetooth_name(needle):
            validated = validate_bluetooth_name(needle)
            matched = [
                dict(dev)
                for dev in MOCK_DEVICES.values()
                if dev.get("deviceName", "").upper() == validated
            ]
            return matched
        return [dict(device) for sn, device in MOCK_DEVICES.items() if needle in sn]

    async def search_device_terms(self, terms: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen = set()
        for term in terms:
            for device in await self.search_devices(term):
                if device["sn"] in seen:
                    continue
                seen.add(device["sn"])
                results.append(device)
        return results

    async def batch_get_devices(self, serial_nos: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for sn in serial_nos:
            result = await self.get_device(sn)
            # get_device 对蓝牙名称返回 list，对 SN 返回 dict
            devices = result if isinstance(result, list) else [result]
            for device in devices:
                device_sn = device.get("sn", "").upper()
                if device_sn and device_sn not in seen:
                    seen.add(device_sn)
                    results.append(device)
        return results

    async def get_glucose_series(
        self, serial_no: str, _: datetime | None = None, __: datetime | None = None
    ) -> dict[str, Any]:
        device = await self.get_device(serial_no)
        subtype = device["fault"]["faultSubtype"]
        expected = device["fault"]["expectedAfterSales"]
        if "Persistent Low" in subtype:
            values = [2.7] * (10 if expected == "Replacement Eligible" else 6) + [7.4]
        elif "No Fluctuation" in subtype:
            values = [4.2] * (18 if expected == "Replacement Eligible" else 8)
        elif "Jump" in subtype:
            values = (
                [5.0, 8.8, 4.1, 8.7, 4.2, 8.6]
                if expected == "Replacement Eligible"
                else [5.0, 6.0, 4.8]
            )
        else:
            values = [5.6, 5.8, 6.0, 6.1, 5.9, 6.2]
        points = [
            {
                "timestamp": NOW - timedelta(minutes=30 * (len(values) - index)),
                "glucose": value,
                "unit": "mmol/L",
                "alarm_status": 2
                if device["fault"]["faultCategory"] == "Sensor Abnormal"
                else 0,
                "sensor_internal_value": 2
                if device["fault"]["faultCategory"] == "Sensor Abnormal"
                else 0,
            }
            for index, value in enumerate(values)
        ]
        return {"serial_no": device["sn"], "points": points}

    async def get_latest_alarm(self, serial_no: str) -> dict[str, Any]:
        device = await self.get_device(serial_no)
        subtype = device["fault"]["faultSubtype"]
        expected = device["fault"]["expectedAfterSales"]
        duration = 240 if expected == "Replacement Eligible" else 60
        if "Temporary" not in subtype:
            duration = 30
        return {
            "serial_no": device["sn"],
            "latest_alarm_status": 2
            if device["fault"]["faultCategory"] == "Sensor Abnormal"
            else 0,
            "latest_sensor_internal_value": 2
            if device["fault"]["faultCategory"] == "Sensor Abnormal"
            else 0,
            "abnormal_started_at": NOW - timedelta(minutes=duration),
            "abnormal_duration_minutes": duration,
            "raw_device_status": device["device_status"],
        }

    async def get_abnormal_duration(self, serial_no: str) -> int:
        alarm = await self.get_latest_alarm(serial_no)
        return int(alarm["abnormal_duration_minutes"])

    async def close(self) -> None:
        pass
