"""
查询 4 个 SN 的海外 API 设备血糖数据概览。
SN: TESGS1AS030YF01, TESGS1AS030YF02, TESGS1AS030YF03, TESGS1AS030YF04
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.integrations.overseas_client import OverseasCGMClient
from src.integrations.overseas_adapter import adapt_device_detail


SNS = [
    "TESGS1AS030YF01",
    "TESGS1AS030YF02",
    "TESGS1AS030YF03",
    "TESGS1AS030YF04",
]


async def main():
    settings = get_settings()
    client = OverseasCGMClient(settings)

    for sn in SNS:
        print("=" * 80)
        print(f"  SN: {sn}")
        print("=" * 80)
        try:
            raw_detail = await client._fetch_device_detail(sn)

            # Basic device info
            print(f"  deviceName: {raw_detail.get('deviceName')}")
            print(f"  status: {raw_detail.get('status')}")
            print(f"  enableTime: {raw_detail.get('enableTime')}")
            print(f"  wearDurationHours: {raw_detail.get('wearDurationHours')}")
            print(f"  fallOffStatus: {raw_detail.get('fallOffStatus')}")
            print(f"  abnormalTime: {raw_detail.get('abnormalTime')}")

            # Glucose info
            glucose_info = raw_detail.get("glucoseInfo") or []
            print(f"  glucoseInfo 点数: {len(glucose_info)}")

            if glucose_info:
                # Extract raw values
                raw_values = []
                for p in glucose_info:
                    v = p.get("v")
                    if v is not None:
                        try:
                            raw_values.append(float(str(v)))
                        except (ValueError, TypeError):
                            pass

                if raw_values:
                    print(f"  血糖值(原始): min={min(raw_values):.2f}, max={max(raw_values):.2f}, avg={sum(raw_values)/len(raw_values):.2f}")
                    print(f"  有效数据点数: {len(raw_values)}")
                    print(f"  前5个原始数据点: {glucose_info[:5]}")
                    print(f"  后5个原始数据点: {glucose_info[-5:]}")

            # Run through adapter
            device, glucose_series, alarm = adapt_device_detail(raw_detail, sn, settings)
            points = glucose_series.get("points", [])
            if points:
                values = [p["glucose"] for p in points]
                print(f"\n  适配后血糖 (mmol/L): min={min(values):.2f}, max={max(values):.2f}, avg={sum(values)/len(values):.2f}")
                print(f"  适配后数据点数: {len(points)}")
                print(f"  设备状态: status={device.get('status')}, device_status={device.get('device_status')}")
                print(f"  佩戴天数: {device.get('wear_days'):.2f} 天 ({device.get('wearDays')}天{device.get('wearHours')}小时)")
                print(f"  脱落状态: {device.get('fall_off_status')}")
                print(f"  告警状态: alarm_status={alarm.get('latest_alarm_status')}, abnormal_min={alarm.get('abnormal_duration_minutes')}")
            else:
                print("\n  ⚠ 适配后没有血糖数据点")

        except Exception as exc:
            print(f"  ❌ 查询失败: {type(exc).__name__}: {exc}")

        print()


if __name__ == "__main__":
    asyncio.run(main())
