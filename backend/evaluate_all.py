import asyncio
import sys
import os
import time

# Add parent directory to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import get_settings
from src.integrations.overseas_client import OverseasCGMClient
from src.rules.engine import run_rules
from src.rules.thresholds import default_thresholds

# Mapping from user reported fault category in 资料.txt to system fault category
CATEGORY_MAPPING = {
    "48小时后血糖数据不准": "Data accuracy",
    "48小时内血糖数据不准": "Data accuracy",
    "数据准确性": "Data accuracy",
    "佩戴期间显示传感器异常": "Sensor Abnormal",
    "首次蓝牙连接不上": "Sensor Abnormal",
    "激活后蓝牙无法连接": "Sensor Abnormal",
    "脱落问题": "Sensor falling off",
    "未满14天脱落": "Sensor falling off",
    "佩戴期间异常": "Sensor Abnormal",
    "设备故障": "Sensor Abnormal",
    "其他异常": "Sensor Abnormal",
    "佩戴体验": "Sensor Abnormal"
}

# Translation dictionaries for Chinese output
VERDICT_TRANSLATION = {
    "Replacement Eligible": "符合换新 (Replacement Eligible)",
    "Not Eligible": "不符合换新 (Not Eligible)",
    "Under Review": "转人工审核 (Under Review)",
    "ERROR": "接口异常 (ERROR)"
}

SUBTYPE_TRANSLATION = {
    "Initialization Abnormal": "初始化异常 (Initialization Abnormal)",
    "No Abnormal": "无异常 (No Abnormal)",
    "Sudden Fall Off": "异常脱落 (Sudden Fall Off)",
    "Suspected Fall Off": "疑似脱落 (Suspected Fall Off)",
    "No Fall Off": "未脱落 (No Fall Off)",
    "Data Deviation Review Required": "血糖偏差待审核 (Data Deviation Review Required)",
    "No Fluctuation": "血糖无波动 (No Fluctuation)",
    "Sudden Fluctuation": "血糖骤变 (Sudden Fluctuation)",
    "Waiting Recovery": "等待恢复 (Waiting Recovery)",
    "Temporary Abnormal": "暂时异常 (Temporary Abnormal)",
    "Unsupported category": "不支持的品类 (Unsupported category)",
    "N/A": "无"
}

FALL_OFF_TRANSLATION = {
    "fallen_off": "已脱落 (fallen_off)",
    "suspected_fall_off": "疑似脱落 (suspected_fall_off)",
    "not_fallen_off": "未脱落 (not_fallen_off)",
    "N/A": "无"
}

STATUS_TRANSLATION = {
    0: "0 (未激活)",
    1: "1 (使用中)",
    2: "2 (已停用)",
    3: "3 (初始化)",
    4: "4 (初始化异常)",
    5: "5 (异常)",
    6: "6 (暂时异常)",
    7: "7 (已过期)",
}

async def evaluate_sn(client, threshold_config, user_category, sn, sem):
    sys_category = CATEGORY_MAPPING.get(user_category)
    if not sys_category:
        print(f"[-] Unknown user category '{user_category}' for SN: {sn}", flush=True)
        return None
        
    async with sem:
        max_retries = 3
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[+] Evaluating SN: {sn} (Attempt {attempt}/{max_retries}) ({user_category} -> {sys_category})", flush=True)
                
                # Fetch device info, glucose and alarm
                device = await client.get_device(sn)
                glucose = await client.get_glucose_series(sn)
                alarm = await client.get_latest_alarm(sn)
                
                # Run rule engine
                result = run_rules(
                    fault_category=sys_category,
                    device=device,
                    glucose_series=glucose,
                    alarm=alarm,
                    threshold_config=threshold_config
                )
                
                is_detected = result.verdict == "Replacement Eligible"
                print(f"[✓] SN {sn} evaluated successfully: verdict={result.verdict}, subtype={result.fault_subtype}", flush=True)
                
                return {
                    "sn": sn,
                    "user_category": user_category,
                    "sys_category": sys_category,
                    "device_status": device.get("device_status"),
                    "fall_off_status": device.get("fall_off_status"),
                    "wear_days": round(device.get("wear_days", 0.0), 2),
                    "verdict": result.verdict,
                    "fault_subtype": result.fault_subtype,
                    "reasons": "; ".join(result.reasons),
                    "is_detected": is_detected,
                    "glucose_points_count": len(glucose.get("points", [])),
                    "alarm_status": alarm.get("latest_alarm_status"),
                    "abnormal_duration": alarm.get("abnormal_duration_minutes")
                }
            except Exception as e:
                last_error = e
                if "not found" in str(e).lower():
                    break
                print(f"[!] Error on SN {sn} (Attempt {attempt}): {str(e)}. Retrying...", flush=True)
                await asyncio.sleep(2 * attempt)
                
        print(f"[!] Failed to evaluate SN {sn} after {max_retries} attempts: {str(last_error)}", flush=True)
        return {
            "sn": sn,
            "user_category": user_category,
            "sys_category": sys_category,
            "error": str(last_error),
            "is_detected": False
        }

async def main():
    settings = get_settings()
    client = OverseasCGMClient(settings)
    threshold_config = default_thresholds()
    
    # Read backend/资料.txt
    data_path = "/home/q2li/computer_project/agent_project/backend/资料.txt"
    if not os.path.exists(data_path):
        data_path = "backend/资料.txt"
        
    records = []
    with open(data_path, "r", encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                user_category = parts[0].strip()
                sn = parts[1].strip()
                records.append((user_category, sn))
                
    print(f"Loaded {len(records)} SNs to evaluate.")
    sem = asyncio.Semaphore(2)
    
    tasks = [evaluate_sn(client, threshold_config, cat, sn, sem) for cat, sn in records]
    results = await asyncio.gather(*tasks)
    results = [r for r in results if r is not None]
    
    success_count = sum(1 for r in results if r.get("is_detected"))
    total_count = len(results)
    accuracy = (success_count / total_count * 100) if total_count > 0 else 0
    
    print(f"\nEvaluation Complete! Total SNs: {total_count}, Detected: {success_count}, Accuracy: {accuracy:.2f}%")
    
    report_path = "/home/q2li/computer_project/agent_project/backend/evaluation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 真实设备规则引擎故障检测率评估报告\n\n")
        f.write(f"- **评估测试设备总数**: {total_count}\n")
        f.write(f"- **规则自动检出故障并判定换新 (Replacement Eligible)**: {success_count}\n")
        f.write(f"- **系统检测覆盖率 (自动换新率)**: {accuracy:.2f}%\n\n")
        
        f.write("## 详细评估数据对比表 (中文翻译版)\n\n")
        f.write("| 序号 | 序列号 (SN) | 用户反馈故障大类 | 系统映射故障大类 | 佩戴天数 | 设备状态码 | 脱落状态 | 系统判定结论 | 故障子类型 | 检测结果 | 判定理由 (英文原版) |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        
        for idx, r in enumerate(results, 1):
            if "error" in r:
                f.write(f"| {idx} | `{r['sn']}` | {r['user_category']} | {r['sys_category']} | 无 (N/A) | 无 (N/A) | 无 (N/A) | {VERDICT_TRANSLATION['ERROR']} | 无 (N/A) | ❌ 接口错误 ({r['error']}) | N/A |\n")
            else:
                detection_str = "✅ 成功检测" if r["is_detected"] else "❌ 未检出"
                if r["verdict"] == "Under Review":
                    detection_str = "⚠️ 转人工审核"
                
                status_str = STATUS_TRANSLATION.get(r["device_status"], str(r["device_status"]))
                fall_str = FALL_OFF_TRANSLATION.get(r["fall_off_status"], str(r["fall_off_status"]))
                verdict_str = VERDICT_TRANSLATION.get(r["verdict"], r["verdict"])
                subtype_str = SUBTYPE_TRANSLATION.get(r["fault_subtype"], r["fault_subtype"])
                
                f.write(f"| {idx} | `{r['sn']}` | {r['user_category']} | {r['sys_category']} | {r['wear_days']} | {status_str} | {fall_str} | {verdict_str} | {subtype_str} | {detection_str} | {r['reasons']} |\n")
                
    print(f"Saved evaluation report to {report_path}")

if __name__ == "__main__":
    asyncio.run(main())
