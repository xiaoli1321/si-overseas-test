import asyncio
import sys
from pathlib import Path
from sqlalchemy import text

# Ensure backend source is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal
from src.integrations.storage import get_storage_backend

# ==============================================================================
# 1. Core Unified Hierarchical Operations Report SQL
# ==============================================================================
HIERARCHICAL_MERGED_SQL = """
WITH login_stats AS (
    SELECT 
        u.id AS user_id,
        u.distributor_name,
        COUNT(a.id) AS login_count
    FROM audit_logs a
    JOIN users u ON a.user_id = u.id
    WHERE a.action = 'auth.login' AND a.status = 'success'
    GROUP BY u.id, u.distributor_name
),
query_stats AS (
    SELECT 
        u.id AS user_id,
        u.distributor_name,
        COUNT(a.id) AS query_count,
        SUM(CASE WHEN a.metadata->>'query_type' = 'batch' THEN (a.metadata->>'batch_count')::integer ELSE 0 END) AS batch_devices
    FROM audit_logs a
    JOIN users u ON a.user_id = u.id
    WHERE a.action = 'device.query'
    GROUP BY u.id, u.distributor_name
),
adoption_stats AS (
    SELECT 
        r.user_id,
        u.distributor_name,
        COUNT(CASE WHEN r.adoption_status = 'adopted' THEN 1 END) AS adopted_count,
        COUNT(CASE WHEN r.adoption_status = 'rejected' THEN 1 END) AS rejected_count
    FROM detect_records r
    JOIN users u ON r.user_id = u.id
    WHERE r.status = 'completed'
    GROUP BY r.user_id, u.distributor_name
),
threshold_stats AS (
    SELECT 
        u.id AS user_id,
        u.distributor_name,
        COUNT(a.id) AS threshold_edits
    FROM audit_logs a
    JOIN users u ON a.user_id = u.id,
    LATERAL jsonb_array_elements_text(a.metadata->'modified_fields') AS field_name
    WHERE a.action = 'threshold.modify' AND a.status = 'success'
    GROUP BY u.id, u.distributor_name
),
distributor_list AS (
    SELECT DISTINCT distributor_name
    FROM users
    WHERE distributor_name IS NOT NULL AND distributor_name != 'N/A'
),
distributor_aggregated AS (
    SELECT 
        d.distributor_name AS distributor_name,
        COALESCE(SUM(l.login_count), 0) AS login_count,
        COALESCE(SUM(q.query_count), 0) AS query_count,
        COALESCE(SUM(q.batch_devices), 0) AS batch_devices,
        COALESCE(SUM(a.adopted_count), 0) AS adopted_count,
        COALESCE(SUM(a.rejected_count), 0) AS rejected_count,
        COALESCE(SUM(t.threshold_edits), 0) AS threshold_edits
    FROM distributor_list d
    LEFT JOIN login_stats l ON d.distributor_name = l.distributor_name
    LEFT JOIN query_stats q ON d.distributor_name = q.distributor_name
    LEFT JOIN adoption_stats a ON d.distributor_name = a.distributor_name
    LEFT JOIN threshold_stats t ON d.distributor_name = t.distributor_name
    GROUP BY d.distributor_name
),
user_aggregated AS (
    SELECT 
        u.id AS user_id,
        u.username AS username,
        COALESCE(u.distributor_name, 'N/A') AS distributor_name,
        COALESCE(l.login_count, 0) AS login_count,
        COALESCE(q.query_count, 0) AS query_count,
        COALESCE(q.batch_devices, 0) AS batch_devices,
        COALESCE(a.adopted_count, 0) AS adopted_count,
        COALESCE(a.rejected_count, 0) AS rejected_count,
        COALESCE(t.threshold_edits, 0) AS threshold_edits
    FROM users u
    LEFT JOIN login_stats l ON u.id = l.user_id
    LEFT JOIN query_stats q ON u.id = q.user_id
    LEFT JOIN adoption_stats a ON u.id = a.user_id
    LEFT JOIN threshold_stats t ON u.id = t.user_id
)
SELECT 
    '经销商' AS "层级",
    distributor_name AS "主体/操作账号",
    'N/A' AS "所属经销商",
    login_count AS "登录活跃数",
    query_count AS "查询次数",
    batch_devices AS "批量查询设备数",
    adopted_count AS "诊断已采纳",
    rejected_count AS "诊断已拒绝",
    ROUND(
        (adopted_count::decimal / 
        NULLIF(adopted_count + rejected_count, 0)) * 100, 
        2
    ) AS "采纳率 (%)",
    threshold_edits AS "敏感阈值修改次数",
    distributor_name AS order_key,
    1 AS sub_order
FROM distributor_aggregated

UNION ALL

SELECT 
    '└─ 用户' AS "层级",
    username AS "主体/操作账号",
    distributor_name AS "所属经销商",
    login_count AS "登录活跃数",
    query_count AS "查询次数",
    batch_devices AS "批量查询设备数",
    adopted_count AS "诊断已采纳",
    rejected_count AS "诊断已拒绝",
    ROUND(
        (adopted_count::decimal / 
        NULLIF(adopted_count + rejected_count, 0)) * 100, 
        2
    ) AS "采纳率 (%)",
    threshold_edits AS "敏感阈值修改次数",
    distributor_name AS order_key,
    2 AS sub_order
FROM user_aggregated

ORDER BY order_key ASC, sub_order ASC;
"""

# ==============================================================================
# 2. Granular Telemetry & After-Sales Analytics SQL (Matching correct DB values)
# ==============================================================================

# A. Fault Category & Subtype Adoption Rate
ADOPTION_BY_SUBTYPE_SQL = """
WITH group_counts AS (
    SELECT 
        fault_category,
        COALESCE(fault_subtype, 'N/A') AS fault_subtype,
        COUNT(id) AS group_count,
        COUNT(CASE WHEN verdict = 'Replacement Eligible' THEN 1 END) AS eligible_count,
        COUNT(CASE WHEN adoption_status = 'adopted' THEN 1 END) AS adopted_count,
        COUNT(CASE WHEN adoption_status = 'rejected' THEN 1 END) AS rejected_count
    FROM detect_records
    WHERE status = 'completed'
    GROUP BY fault_category, fault_subtype
),
overall_total AS (
    SELECT COUNT(id) AS total_count
    FROM detect_records
    WHERE status = 'completed'
)
SELECT 
    g.fault_category AS "故障大类",
    g.fault_subtype AS "故障子类",
    g.group_count AS "诊断次数",
    ROUND((g.group_count::decimal / o.total_count) * 100, 2) AS "占总诊断比 (%)",
    ROUND((g.eligible_count::decimal / NULLIF(g.group_count, 0)) * 100, 2) AS "符合售后比例 (%)",
    g.adopted_count AS "已采纳",
    g.rejected_count AS "已拒绝",
    ROUND(
        (g.adopted_count::decimal /
        NULLIF(g.adopted_count + g.rejected_count, 0)) * 100,
        2
    ) AS "采纳率 (%)"
FROM group_counts g
CROSS JOIN overall_total o
ORDER BY g.fault_category, g.group_count DESC;
"""

# B. Overall Warranty Eligibility Ratio (Pass/Fail Ratio)
WARRANTY_ELIGIBILITY_OVERALL_SQL = """
SELECT 
    COALESCE(verdict, 'UNKNOWN') AS "售后判定结论",
    COUNT(*) AS "判定次数",
    ROUND((COUNT(*)::decimal / SUM(COUNT(*)) OVER()) * 100, 2) AS "占比 (%)"
FROM detect_records
WHERE status = 'completed'
GROUP BY verdict
ORDER BY "判定次数" DESC;
"""

# C. Warranty Eligibility Rate by Distributor (Country Proxy)
WARRANTY_ELIGIBILITY_BY_DISTRIBUTOR_SQL = """
SELECT 
    u.distributor_name AS "经销商名称",
    COUNT(r.id) AS "总诊断数",
    COUNT(CASE WHEN r.verdict = 'Replacement Eligible' THEN 1 END) AS "符合售后数",
    COUNT(CASE WHEN r.verdict = 'Not Eligible' THEN 1 END) AS "不符合售后数",
    ROUND(
        (COUNT(CASE WHEN r.verdict = 'Replacement Eligible' THEN 1 END)::decimal / 
        NULLIF(COUNT(r.id), 0)) * 100, 
        2
    ) AS "售后符合率 (%)"
FROM detect_records r
JOIN users u ON r.user_id = u.id
WHERE r.status = 'completed' AND u.distributor_name IS NOT NULL AND u.distributor_name != 'N/A'
GROUP BY u.distributor_name
ORDER BY "售后符合率 (%)" DESC;
"""

# D. Joint Breakdown: Distributor + Fault Category
DISTRIBUTOR_FAULT_BREAKDOWN_SQL = """
WITH group_counts AS (
    SELECT 
        u.distributor_name,
        r.fault_category,
        COALESCE(r.fault_subtype, 'N/A') AS fault_subtype,
        COUNT(r.id) AS group_count,
        COUNT(CASE WHEN r.verdict = 'Replacement Eligible' THEN 1 END) AS eligible_count,
        COUNT(CASE WHEN r.adoption_status = 'adopted' THEN 1 END) AS adopted_count,
        COUNT(CASE WHEN r.adoption_status = 'rejected' THEN 1 END) AS rejected_count
    FROM detect_records r
    JOIN users u ON r.user_id = u.id
    WHERE r.status = 'completed' AND u.distributor_name IS NOT NULL AND u.distributor_name != 'N/A'
    GROUP BY u.distributor_name, r.fault_category, r.fault_subtype
),
distributor_totals AS (
    SELECT 
        u.distributor_name,
        COUNT(r.id) AS total_count
    FROM detect_records r
    JOIN users u ON r.user_id = u.id
    WHERE r.status = 'completed' AND u.distributor_name IS NOT NULL AND u.distributor_name != 'N/A'
    GROUP BY u.distributor_name
)
SELECT 
    g.distributor_name AS "经销商名称",
    g.fault_category AS "故障大类",
    g.fault_subtype AS "故障子类",
    g.group_count AS "诊断次数",
    ROUND((g.group_count::decimal / t.total_count) * 100, 2) AS "占该商户总诊断比 (%)",
    ROUND((g.eligible_count::decimal / NULLIF(g.group_count, 0)) * 100, 2) AS "符合售后比例 (%)",
    g.adopted_count AS "已采纳",
    g.rejected_count AS "已拒绝",
    ROUND(
        (g.adopted_count::decimal /
        NULLIF(g.adopted_count + g.rejected_count, 0)) * 100,
        2
    ) AS "采纳率 (%)"
FROM group_counts g
JOIN distributor_totals t ON g.distributor_name = t.distributor_name
ORDER BY g.distributor_name, g.fault_category, g.group_count DESC;
"""

DEVICE_QUERY_SOURCE_FAULT_SQL = """
SELECT 
    COALESCE(u.distributor_name, 'N/A') AS distributor_name,
    COALESCE(a.metadata->>'entry_source', 'N/A') AS entry_source,
    COALESCE(a.metadata->>'fault_category', 'N/A') AS fault_category,
    COUNT(a.id) AS query_count,
    SUM(COALESCE((a.metadata->>'query_count')::integer, 1)) AS total_devices
FROM audit_logs a
LEFT JOIN users u ON a.user_id = u.id
WHERE a.action = 'device.query'
GROUP BY u.distributor_name, a.metadata->>'entry_source', a.metadata->>'fault_category'
ORDER BY distributor_name, query_count DESC;
"""

# Web and OpenAPI use the same detect_records table. `source` is therefore the
# authoritative channel for result metrics. Login events use channel metadata;
# old events without it are treated as Web for backwards-compatible reports.
CHANNEL_COMPARISON_SQL = """
WITH detection_stats AS (
    SELECT
        r.user_id,
        COALESCE(NULLIF(r.source, ''), 'web') AS channel,
        COUNT(*) AS submitted_count,
        COUNT(*) FILTER (WHERE r.status = 'completed') AS completed_count,
        COUNT(*) FILTER (
            WHERE r.status = 'completed' AND r.verdict = 'Replacement Eligible'
        ) AS eligible_count,
        COUNT(*) FILTER (
            WHERE r.status = 'completed' AND r.adoption_status = 'adopted'
        ) AS adopted_count,
        COUNT(*) FILTER (
            WHERE r.status = 'completed' AND r.adoption_status = 'rejected'
        ) AS rejected_count
    FROM detect_records r
    GROUP BY r.user_id, COALESCE(NULLIF(r.source, ''), 'web')
),
login_stats AS (
    SELECT
        a.user_id,
        COALESCE(a.metadata->>'channel', 'web') AS channel,
        COUNT(*) AS login_count
    FROM audit_logs a
    WHERE a.action = 'auth.login' AND a.status = 'success'
    GROUP BY a.user_id, COALESCE(a.metadata->>'channel', 'web')
),
channel_users AS (
    SELECT user_id, channel FROM detection_stats
    UNION
    SELECT user_id, channel FROM login_stats
)
SELECT
    COALESCE(u.distributor_name, 'N/A') AS distributor_name,
    cu.channel,
    COALESCE(SUM(l.login_count), 0) AS login_count,
    COALESCE(SUM(d.submitted_count), 0) AS submitted_count,
    COALESCE(SUM(d.completed_count), 0) AS completed_count,
    COALESCE(SUM(d.eligible_count), 0) AS eligible_count,
    COALESCE(SUM(d.adopted_count), 0) AS adopted_count,
    COALESCE(SUM(d.rejected_count), 0) AS rejected_count,
    ROUND(
        COALESCE(SUM(d.eligible_count), 0)::decimal /
        NULLIF(COALESCE(SUM(d.completed_count), 0), 0) * 100,
        2
    ) AS eligibility_rate,
    ROUND(
        COALESCE(SUM(d.adopted_count), 0)::decimal /
        NULLIF(COALESCE(SUM(d.adopted_count), 0) + COALESCE(SUM(d.rejected_count), 0), 0) * 100,
        2
    ) AS adoption_rate
FROM channel_users cu
JOIN users u ON u.id = cu.user_id
LEFT JOIN detection_stats d ON d.user_id = cu.user_id AND d.channel = cu.channel
LEFT JOIN login_stats l ON l.user_id = cu.user_id AND l.channel = cu.channel
GROUP BY u.distributor_name, cu.channel
ORDER BY distributor_name, cu.channel;
"""

OPENAPI_OPERATION_QUALITY_SQL = """
SELECT
    COALESCE(u.distributor_name, 'N/A') AS distributor_name,
    a.action,
    COUNT(*) AS call_count,
    COUNT(*) FILTER (WHERE a.status = 'success') AS success_count,
    COUNT(*) FILTER (WHERE a.status <> 'success') AS failure_count,
    ROUND(
        COUNT(*) FILTER (WHERE a.status = 'success')::decimal /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) AS success_rate
FROM audit_logs a
LEFT JOIN users u ON u.id = a.user_id
WHERE a.action LIKE 'openapi.%'
GROUP BY u.distributor_name, a.action
ORDER BY distributor_name, a.action;
"""

# ==============================================================================
# 3. New Granular Threshold Modifications SQL
# ==============================================================================

THRESHOLD_RANK_SQL = """
SELECT 
    field_name,
    COUNT(*) AS modification_count
FROM audit_logs a,
LATERAL jsonb_array_elements_text(a.metadata->'modified_fields') AS field_name
WHERE a.action = 'threshold.modify' AND a.status = 'success'
GROUP BY field_name
ORDER BY modification_count DESC;
"""

THRESHOLD_DISTRIBUTOR_SQL = """
SELECT 
    COALESCE(u.distributor_name, 'N/A') AS distributor_name,
    field_name,
    COUNT(*) AS modification_count
FROM audit_logs a
JOIN users u ON a.user_id = u.id,
LATERAL jsonb_array_elements_text(a.metadata->'modified_fields') AS field_name
WHERE a.action = 'threshold.modify' AND a.status = 'success'
GROUP BY u.distributor_name, field_name
ORDER BY distributor_name, modification_count DESC;
"""

# (Removed THRESHOLD_USER_SQL per user request)


def translate_field(name: str) -> str:
    if not name or name == "N/A":
        return name
    FIELD_CN = {
        "rules.inaccuracy.lowPersist.belowMmol": "准确度低值持续偏差限制",
        "rules.sensorAbnormal.lowPersist.belowMmol": "探头异常低值持续异常限制",
        "rules.sensorFallingOff.durationHours": "探头脱落判定时间窗口",
        "rules.inaccuracy.max24hMmol": "24h最大偏差值",
        "rules.inaccuracy.qualifiedRatio": "比对合格率比例",
        "rules.inaccuracy.pairCount": "最小比对对数"
    }
    if name in FIELD_CN:
        return f"{name} ({FIELD_CN[name]})"
    return name

async def run_query(db, sql):
    result = await db.execute(text(sql))
    return result.fetchall()

REPORT_DIR = "si-overseas/reports"


async def _upload_report(filename: str, content: str, content_type: str = "text/markdown; charset=utf-8") -> str:
    """Upload a report file to storage (OSS or local) and return its URL/path."""
    settings = get_settings()
    storage = get_storage_backend(settings)
    key = f"{REPORT_DIR}/{filename}"
    
    # Save a local copy for direct local access
    local_dir = Path(__file__).parent / "outputs"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / filename
    
    encoding = "utf-8-sig" if filename.endswith(".csv") else "utf-8"
    
    with open(local_path, "w", encoding=encoding) as f:
        f.write(content)
    print(f"Local copy saved to: {local_path}")
    
    obj = await storage.save_bytes(key=key, data=content.encode(encoding), content_type=content_type)
    url = await storage.get_download_url(obj.object_key)
    if url:
        print(f"  → {url}")
    else:
        print(f"  → {obj.object_key}")
    return url or obj.object_key

async def main():
    async with AsyncSessionLocal() as db:
        print("Running unified hierarchical query...")
        rows = await run_query(db, HIERARCHICAL_MERGED_SQL)
        
        # 1. Format Markdown Table for Tree Report
        table_lines = []
        for r in rows:
            rate_str = f"{r[8]:.2f}%" if r[8] is not None else "-"
            if r[0] == "经销商":
                table_lines.append(
                    f"| **{r[0]}** | **{r[1]}** | {r[2]} | **{r[3]}** | **{r[4]}** | **{r[5]}** | **{r[6]}** | **{r[7]}** | **{rate_str}** | **{r[9]}** |"
                )
            else:
                table_lines.append(
                    f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} | {rate_str} | {r[9]} |"
                )
        unified_md_table = "\n".join(table_lines)
        
        # Run New Granular Queries
        print("Running granular after-sales queries...")
        rows_subtype_adopt = await run_query(db, ADOPTION_BY_SUBTYPE_SQL)
        rows_eligibility_overall = await run_query(db, WARRANTY_ELIGIBILITY_OVERALL_SQL)
        rows_eligibility_distributor = await run_query(db, WARRANTY_ELIGIBILITY_BY_DISTRIBUTOR_SQL)
        rows_dist_fault_breakdown = await run_query(db, DISTRIBUTOR_FAULT_BREAKDOWN_SQL)
        rows_query_source_fault = await run_query(db, DEVICE_QUERY_SOURCE_FAULT_SQL)
        
        # Run Threshold Queries
        print("Running threshold modification queries...")
        rows_threshold_rank = await run_query(db, THRESHOLD_RANK_SQL)
        rows_threshold_dist = await run_query(db, THRESHOLD_DISTRIBUTOR_SQL)

        print("Running Web/OpenAPI channel queries...")
        rows_channel_comparison = await run_query(db, CHANNEL_COMPARISON_SQL)
        rows_openapi_quality = await run_query(db, OPENAPI_OPERATION_QUALITY_SQL)
        
        # Format subtype adoption table
        md_subtype_adopt = []
        for r in rows_subtype_adopt:
            rate = f"{r[7]:.2f}%" if r[7] is not None else "-"
            p_rate = f"{r[4]:.2f}%" if r[4] is not None else "-"
            md_subtype_adopt.append(f"| {r[0]} | `{r[1]}` | {r[2]} | {r[3]:.2f}% | **{p_rate}** | {r[5]} | {r[6]} | **{rate}** |")
        md_subtype_adopt_table = "\n".join(md_subtype_adopt)
        
        # Format eligibility overall table
        md_elig_overall = []
        for r in rows_eligibility_overall:
            verdict_cn = "符合售后标准 (Replacement Eligible)" if r[0] == "Replacement Eligible" else ("不符合售后标准 (Not Eligible)" if r[0] == "Not Eligible" else r[0])
            md_elig_overall.append(f"| **{verdict_cn}** | {r[1]} | **{r[2]:.2f}%** |")
        md_elig_overall_table = "\n".join(md_elig_overall)
        
        # Format eligibility distributor table
        md_elig_dist = []
        for r in rows_eligibility_distributor:
            rate = f"{r[4]:.2f}%" if r[4] is not None else "-"
            md_elig_dist.append(f"| **{r[0]}** | {r[1]} | {r[2]} | {r[3]} | **{rate}** |")
        md_elig_dist_table = "\n".join(md_elig_dist)
        
        # Format joint distributor + fault breakdown table
        md_dist_fault = []
        for r in rows_dist_fault_breakdown:
            p_rate = f"{r[5]:.2f}%" if r[5] is not None else "-"
            adopt_rate_str = f"{r[8]:.2f}%" if r[8] is not None else "-"
            md_dist_fault.append(f"| {r[0]} | **{r[1]}** | `{r[2]}` | {r[3]} | {r[4]:.2f}% | **{p_rate}** | {r[6]} | {r[7]} | **{adopt_rate_str}** |")
        md_dist_fault_table = "\n".join(md_dist_fault)

        # Format device query by source & category table
        ENTRY_SOURCE_CN = {
            "shortcut": "自己点 (快捷入口)",
            "recommendation": "通过问答选择 (推荐入口)",
            "N/A": "N/A"
        }
        md_query_source_fault = []
        for r in rows_query_source_fault:
            source_cn = ENTRY_SOURCE_CN.get(r[1], r[1])
            md_query_source_fault.append(f"| {r[0]} | {source_cn} | **{r[2]}** | {r[3]} | {r[4]} |")
        md_query_source_fault_table = "\n".join(md_query_source_fault)

        # Format threshold rank table
        md_threshold_rank = []
        for r in rows_threshold_rank:
            translated = translate_field(r[0])
            md_threshold_rank.append(f"| {translated} | **{r[1]}** |")
        md_threshold_rank_table = "\n".join(md_threshold_rank)

        # Format threshold distributor table
        md_threshold_dist = []
        for r in rows_threshold_dist:
            translated = translate_field(r[1])
            md_threshold_dist.append(f"| {r[0]} | {translated} | **{r[2]}** |")
        md_threshold_dist_table = "\n".join(md_threshold_dist)

        CHANNEL_CN = {"web": "Web", "openapi": "OpenAPI"}
        md_channel_comparison = []
        for r in rows_channel_comparison:
            eligibility_rate = f"{r[8]:.2f}%" if r[8] is not None else "-"
            adoption_rate = f"{r[9]:.2f}%" if r[9] is not None else "-"
            md_channel_comparison.append(
                f"| {r[0]} | {CHANNEL_CN.get(r[1], r[1])} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {eligibility_rate} | {r[6]} | {r[7]} | {adoption_rate} |"
            )
        md_channel_comparison_table = "\n".join(md_channel_comparison)

        md_openapi_quality = []
        for r in rows_openapi_quality:
            success_rate = f"{r[5]:.2f}%" if r[5] is not None else "-"
            md_openapi_quality.append(
                f"| {r[0]} | `{r[1]}` | {r[2]} | {r[3]} | {r[4]} | {success_rate} |"
            )
        md_openapi_quality_table = "\n".join(md_openapi_quality)

        # (Removed threshold user table format per user request)

        # Write clean tables only to report_tables.md
        clean_report = f"""# 海外 CGM 运营指标汇总数据表

本文件包含系统提取并整理后的各项大宽表与细化分析表。

---

## 1. 经销商-用户层级合并表
展示从经销商宏观到个人用户微观的活跃、查询、采纳及阈值修改行为。

| 层级 | 主体/操作账号 | 所属经销商 | 登录活跃数 | 查询次数 | 批量查询设备数 | 诊断已采纳 | 诊断已拒绝 | 采纳率 (%) | 敏感阈值修改次数 |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
{unified_md_table}

---

## 2. 故障大类及子类采纳率分析
分析售后系统各个诊断分支结论 of 诊断次数、占比、售后符合率以及采纳与拒绝比例，衡量判定引擎在细分业务上的稳定性。

| 故障大类 | 故障子类 | 诊断次数 | 占总诊断比 (%) | 符合售后比例 (%) | 诊断已采纳数 | 诊断已拒绝数 | 采纳率 (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
{md_subtype_adopt_table}

---

## 3. 售后符合率与判定通过率
衡量有多少诊断记录最终落入“符合换新政策”或“不予换新”的比例。

### 3.1 总体售后判定符合分布
| 售后判定结论 | 判定次数 | 占比 (%) |
| :--- | :---: | :---: |
{md_elig_overall_table}

### 3.2 经销商渠道售后符合率
| 经销商名称 | 总诊断数 | 符合售后数 | 不符合售后数 | 售后符合率 (通过率) (%) |
| :--- | :---: | :---: | :---: | :---: |
{md_elig_dist_table}

---

## 4. 经销商与故障类型交叉诊断统计
展示不同商户在各类故障大类与小类上的诊断频次、在其总诊断中的占比、符合换新通过率、已采纳数、已拒绝数以及采纳率。

| 经销商名称 | 故障大类 | 故障子类 | 诊断次数 | 占该商户总诊断比 (%) | 符合售后比例 (%) | 已采纳数 | 已拒绝数 | 采纳率 (%) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
{md_dist_fault_table}

---

## 5. 设备查询入口与故障类型统计
展示用户入口来源与对应选择的故障类型统计数据。

| 经销商名称 | 查询入口来源 | 故障大类类型 | 查询次数 (按钮触发) | 累计查询设备数 (SN数) |
| :--- | :--- | :--- | :---: | :---: |
{md_query_source_fault_table}

---

## 6. 敏感阈值修改统计
展示用户调整敏感判定参数的频次与分布，辅助分析各层级对诊断阈值的偏好。

### 6.1 阈值字段调整频次排名
| 阈值判定字段 | 修改次数 |
| :--- | :---: |
{md_threshold_rank_table}

### 6.2 经销商渠道阈值调整分布
| 经销商名称 | 阈值判定字段 | 修改次数 |
| :--- | :--- | :---: |
{md_threshold_dist_table}

---

## 7. Web 与 OpenAPI 渠道对比
以 `detect_records.source` 作为检测业务渠道的唯一口径；登录仅统计一次通用 `auth.login` 事件，避免与 `openapi.auth.login` 审计记录重复计数。

| 经销商名称 | 渠道 | 登录次数 | 检测提交数 | 已完成检测 | 符合售后数 | 符合率 (%) | 已采纳 | 已拒绝 | 采纳率 (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
{md_channel_comparison_table}

---

## 8. OpenAPI 运行质量
仅统计 `openapi.*` 审计事件，用于观察接口调用、轮询和失败率；不与 Web 设备查询次数混合。

| 经销商名称 | API 操作 | 调用次数 | 成功次数 | 失败次数 | 成功率 (%) |
| :--- | :--- | :---: | :---: | :---: | :---: |
{md_openapi_quality_table}
"""
        await _upload_report("report_tables.md", clean_report)
        print("Uploaded report_tables.md with granular tables successfully!")

        # ==============================================================================
        # Write Excel-friendly Consolidated CSV File
        # ==============================================================================
        csv_sections = []

        # 1. Hierarchical Table
        csv_lines = [
            "1. 经销商-用户层级合并表",
            "层级,主体/操作账号,所属经销商,登录活跃数,查询次数,批量查询设备数,诊断已采纳,诊断已拒绝,采纳率 (%),敏感阈值修改次数"
        ]
        for r in rows:
            rate = f"{r[8]:.2f}%" if r[8] is not None else "-"
            csv_lines.append(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]},{r[7]},{rate},{r[9]}")
        csv_sections.append("\n".join(csv_lines))

        # 2. Granular Adoption Table
        csv_lines = [
            "2. 故障大类及子类采纳率分析",
            "故障大类,故障子类,诊断次数,占总诊断比 (%),符合售后比例 (%),已采纳数,已拒绝数,采纳率 (%)"
        ]
        for r in rows_subtype_adopt:
            rate = f"{r[7]:.2f}%" if r[7] is not None else "-"
            p_rate = f"{r[4]:.2f}%" if r[4] is not None else "-"
            csv_lines.append(f"{r[0]},{r[1]},{r[2]},{r[3]:.2f}%,{p_rate},{r[5]},{r[6]},{rate}")
        csv_sections.append("\n".join(csv_lines))

        # 3. Overall Warranty Eligibility Table
        csv_lines = [
            "3.1 总体售后判定符合分布",
            "售后判定结论,判定次数,占比 (%)"
        ]
        for r in rows_eligibility_overall:
            verdict_cn = "符合售后标准" if r[0] == "Replacement Eligible" else ("不符合售后标准" if r[0] == "Not Eligible" else r[0])
            csv_lines.append(f"{verdict_cn},{r[1]},{r[2]:.2f}%")
        csv_sections.append("\n".join(csv_lines))

        # 4. Distributor Warranty Pass Rate Table
        csv_lines = [
            "3.2 经销商渠道售后符合率",
            "经销商名称,总诊断数,符合售后数,不符合售后数,售后符合率 (通过率) (%)"
        ]
        for r in rows_eligibility_distributor:
            rate = f"{r[4]:.2f}%" if r[4] is not None else "-"
            csv_lines.append(f"{r[0]},{r[1]},{r[2]},{r[3]},{rate}")
        csv_sections.append("\n".join(csv_lines))

        # 5. Distributor Joint Fault Breakdown Table
        csv_lines = [
            "4. 经销商与故障类型交叉诊断统计",
            "经销商名称,故障大类,故障子类,诊断次数,占该商户总诊断比 (%),符合售后比例 (%),已采纳数,已拒绝数,采纳率 (%)"
        ]
        for r in rows_dist_fault_breakdown:
            p_rate = f"{r[5]:.2f}%" if r[5] is not None else "-"
            adopt_rate_str = f"{r[8]:.2f}%" if r[8] is not None else "-"
            csv_lines.append(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]:.2f}%,{p_rate},{r[6]},{r[7]},{adopt_rate_str}")
        csv_sections.append("\n".join(csv_lines))

        # 6. Device Query Source & Category Table
        csv_lines = [
            "5. 设备查询入口与故障类型统计",
            "经销商名称,查询入口来源,故障大类类型,查询次数 (按钮触发),累计查询设备数 (SN数)"
        ]
        for r in rows_query_source_fault:
            source_cn = ENTRY_SOURCE_CN.get(r[1], r[1])
            csv_lines.append(f"{r[0]},{source_cn},{r[2]},{r[3]},{r[4]}")
        csv_sections.append("\n".join(csv_lines))

        # 7. Threshold Rank Table
        csv_lines = [
            "6.1 阈值字段调整频次排名",
            "阈值判定字段,修改次数"
        ]
        for r in rows_threshold_rank:
            translated = translate_field(r[0])
            csv_lines.append(f"{translated},{r[1]}")
        csv_sections.append("\n".join(csv_lines))

        # 8. Threshold Distributor Table
        csv_lines = [
            "6.2 经销商渠道阈值调整分布",
            "经销商名称,阈值判定字段,修改次数"
        ]
        for r in rows_threshold_dist:
            translated = translate_field(r[1])
            csv_lines.append(f"{r[0]},{translated},{r[2]}")
        csv_sections.append("\n".join(csv_lines))

        # 9. Channel Comparison Table
        csv_lines = [
            "7. Web 与 OpenAPI 渠道对比",
            "经销商名称,渠道,登录次数,检测提交数,已完成检测,符合售后数,符合率 (%),已采纳,已拒绝,采纳率 (%)",
        ]
        for r in rows_channel_comparison:
            eligibility_rate = f"{r[8]:.2f}%" if r[8] is not None else "-"
            adoption_rate = f"{r[9]:.2f}%" if r[9] is not None else "-"
            csv_lines.append(
                f"{r[0]},{CHANNEL_CN.get(r[1], r[1])},{r[2]},{r[3]},{r[4]},{r[5]},{eligibility_rate},{r[6]},{r[7]},{adoption_rate}"
            )
        csv_sections.append("\n".join(csv_lines))

        # 10. OpenAPI Operation Quality Table
        csv_lines = [
            "8. OpenAPI 运行质量",
            "经销商名称,API 操作,调用次数,成功次数,失败次数,成功率 (%)",
        ]
        for r in rows_openapi_quality:
            success_rate = f"{r[5]:.2f}%" if r[5] is not None else "-"
            csv_lines.append(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{success_rate}")
        csv_sections.append("\n".join(csv_lines))

        # (Removed threshold user CSV section per user request)

        combined_csv_content = "\n\n".join(csv_sections)
        await _upload_report("operations_analytics_report.csv", combined_csv_content, "text/csv; charset=utf-8-sig")
        print("Uploaded operations_analytics_report.csv successfully!")

if __name__ == "__main__":
    asyncio.run(main())
