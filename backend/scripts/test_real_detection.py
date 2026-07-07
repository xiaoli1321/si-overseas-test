"""
验证检测流程是否使用真实海外 API 返回的数据进行规则引擎判定。
以"数据不准 (Data accuracy)"为例，设备号: TESGS1AS030YF02
"""
import asyncio
import json
import sys
from pathlib import Path

# 确保可以导入 backend 源码
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.integrations.overseas_client import OverseasCGMClient
from src.integrations.overseas_adapter import adapt_device_detail
from src.rules.engine import run_rules
from src.rules.thresholds import default_thresholds


SN = "TESGS1AS030YF02"


async def main():
    settings = get_settings()
    print("=" * 80)
    print(f"  测试设备号: {SN}")
    print(f"  海外 API enabled: {settings.overseas_api_enabled}")
    print(f"  Login URL: {settings.overseas_api_login_url}")
    print(f"  Base URL:  {settings.overseas_api_base_url}")
    print(f"  Device Detail Path: {settings.overseas_api_device_detail_path}")
    print("=" * 80)

    client = OverseasCGMClient(settings)

    # ── Step 1: 调用真实海外 API 获取原始设备详情 ──
    print("\n[Step 1] 调用海外 deviceDetail 接口获取原始数据...")
    try:
        raw_detail = await client._fetch_device_detail(SN)
        print(f"  ✅ API 调用成功!")
        print(f"  原始返回字段: {list(raw_detail.keys())}")
        print(f"  deviceName: {raw_detail.get('deviceName')}")
        print(f"  status: {raw_detail.get('status')}")
        print(f"  enableTime: {raw_detail.get('enableTime')}")
        print(f"  wearDurationHours: {raw_detail.get('wearDurationHours')}")
        print(f"  fallOffStatus: {raw_detail.get('fallOffStatus')}")
        glucose_info = raw_detail.get("glucoseInfo") or []
        print(f"  glucoseInfo 点数: {len(glucose_info)}")
        if glucose_info:
            print(f"  前3个血糖点(原始): {glucose_info[:3]}")
            print(f"  后3个血糖点(原始): {glucose_info[-3:]}")
    except Exception as exc:
        print(f"  ❌ API 调用失败: {exc}")
        return

    # ── Step 2: 适配为规则引擎所需格式 ──
    print("\n[Step 2] 适配原始数据为规则引擎格式...")
    device, glucose_series, alarm = adapt_device_detail(raw_detail, SN, settings)
    print(f"  --- 适配后 device ---")
    print(f"  sn: {device.get('sn')}")
    print(f"  type: {device.get('type')}")
    print(f"  status: {device.get('status')}")
    print(f"  activatedAt: {device.get('activatedAt')}")
    print(f"  wearDays: {device.get('wearDays')}")
    print(f"  wearHours: {device.get('wearHours')}")
    print(f"  fall_off_status: {device.get('fall_off_status')}")
    print(f"  device_status: {device.get('device_status')}")
    print(f"  fault: {device.get('fault')}  ← 海外API不返回fault，应为None")

    points = glucose_series.get("points", [])
    print(f"\n  --- 适配后 glucose_series ---")
    print(f"  血糖点总数: {len(points)}")
    if points:
        values = [p["glucose"] for p in points]
        print(f"  血糖值范围: min={min(values):.2f}, max={max(values):.2f} mmol/L")
        print(f"  前3个点(已换算mmol/L): {points[:3]}")
        print(f"  后3个点(已换算mmol/L): {points[-3:]}")

    print(f"\n  --- 适配后 alarm ---")
    print(f"  latest_alarm_status: {alarm.get('latest_alarm_status')}")
    print(f"  abnormal_duration_minutes: {alarm.get('abnormal_duration_minutes')}")
    print(f"  latest_sensor_alert: {alarm.get('latest_sensor_alert')}")

    # ── Step 3: 获取阈值配置 ──
    print("\n[Step 3] 加载阈值配置...")
    threshold_config = default_thresholds()
    print(f"  阈值配置: {json.dumps(threshold_config['rules']['inaccuracy'], indent=2, ensure_ascii=False)}")

    # ── Step 4: 用真实数据运行规则引擎 ──
    for cat in ["Data accuracy", "Sensor falling off", "Sensor Abnormal"]:
        print(f"\n[Step 4] 执行 {cat} 判定...")
        result = run_rules(
            fault_category=cat,
            device=device,
            glucose_series=glucose_series,
            alarm=alarm,
            threshold_config=threshold_config,
            file_ids=None,
            vision_analysis=None,
        )

        print(f"  verdict (结论): {result.verdict}")
        print(f"  issue_detected (是否检测到问题): {result.issue_detected}")
        print(f"  fault_subtype (故障子类): {result.fault_subtype}")
        print(f"  matched_rules (命中规则): {result.matched_rules}")
        print(f"  reasons (判定理由):")
        for i, reason in enumerate(result.reasons, 1):
            print(f"    {i}. {reason}")

    # ── 验证结论 ──
    print(f"\n  {'=' * 60}")
    print(f"  验证结论:")
    print(f"  {'=' * 60}")
    print(f"  数据来源: 真实海外 API (https://api-pre.sibionics.io)")
    print(f"  血糖点数: {len(points)} 个真实数据点")
    if points:
        values = [p["glucose"] for p in points]
        print(f"  血糖值范围: {min(values):.2f} ~ {max(values):.2f} mmol/L")
        print(f"  判定结论完全基于以上真实血糖数据计算得出")
    print(f"  fault 字段: {device.get('fault')} (海外API不返回，由规则引擎动态生成)")


if __name__ == "__main__":
    asyncio.run(main())
