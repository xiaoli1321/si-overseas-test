import json
import os

def translate_openapi():
    json_path = 'apifox_openapi.json'
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 接口翻译映射表 (去除所有的 Emoji 和特殊字符)
    translation = {
        ("/api/v1/auth/login", "post"): {
            "summary": "经销商登录获取 Token",
            "description": "通过经销商账号和密码进行登录，验证通过后返回 JWT 访问令牌。",
            "tags": ["账号与鉴权"]
        },
        ("/api/v1/auth/me", "get"): {
            "summary": "获取当前登录用户信息",
            "description": "使用 Bearer Token 获取当前登录的用户基础信息及所属经销商角色。",
            "tags": ["账号与鉴权"]
        },
        ("/api/v1/agent/classify", "post"): {
            "summary": "AI 故障意图分类/对话路由",
            "description": "输入用户对故障的自然语言描述，由大模型分析并推荐应该使用的数据判定规则大类（如 Data Accuracy, Sensor Abnormal 等）。",
            "tags": ["AI 故障分类"]
        },
        ("/api/v1/devices/search/", "get"): {
            "summary": "设备 SN 模糊检索",
            "description": "通过关键字（SN 部分字段）搜索设备列表。",
            "tags": ["设备管理"]
        },
        ("/api/v1/devices/{serial_no}", "get"): {
            "summary": "查询单个设备详情",
            "description": "根据 SN 查询对应 GS1 设备的详细运行参数（佩戴时长、状态、激活时间等）。",
            "tags": ["设备管理"]
        },
        ("/api/v1/devices/batch-query", "post"): {
            "summary": "批量查询多个设备详情",
            "description": "传入 SN 列表批量拉取多台设备的基础运行数据。",
            "tags": ["设备管理"]
        },
        ("/api/v1/detections", "post"): {
            "summary": "单设备售后判定",
            "description": "根据设备数据与当前配置好的阈值对单台 SN 自动进行售后规则判定，直接生成 verdict 并创建记录。",
            "tags": ["故障判定与任务"]
        },
        ("/api/v1/detections/{record_id}", "get"): {
            "summary": "获取单设备判定结果与进度",
            "description": "通过判定记录 ID 查询此判定的运行状态（pending / processing / completed / failed）以及详细规则匹配日志与结论。",
            "tags": ["故障判定与任务"]
        },
        ("/api/v1/detections/{record_id}/retry", "post"): {
            "summary": "一键重试失败的设备判定",
            "description": "针对 status 为 failed 的检测判定记录重新触发后台引擎检测。",
            "tags": ["故障判定与任务"]
        },
        ("/api/v1/detections/batch", "post"): {
            "summary": "创建批量售后判定任务",
            "description": "批量传入设备 SN 列表，异步在后台逐一执行售后检测，返回一个异步 task_id 用于进度追踪。",
            "tags": ["故障判定与任务"]
        },
        ("/api/v1/batch-tasks/{task_id}", "get"): {
            "summary": "查询批量判定任务执行进度",
            "description": "通过 task_id 查询批量任务的整体状态，包含总数、判定成功数、判定失败数等进度数据。",
            "tags": ["故障判定与任务"]
        },
        ("/api/v1/thresholds/current", "get"): {
            "summary": "查询当前生效的售后判定阈值配置",
            "description": "获取当前经销商账号下生效的故障检测规则的各项具体阈值设定（如低血糖值限额、脱落天数限制等）。",
            "tags": ["规则与阈值配置"]
        },
        ("/api/v1/thresholds", "post"): {
            "summary": "更新并保存新的阈值配置",
            "description": "保存新的阈值规则设置，系统将自动递增版本号，后续判定将全部应用此新规则，历史数据依旧关联旧版本快照。",
            "tags": ["规则与阈值配置"]
        },
        ("/api/v1/thresholds/reset", "post"): {
            "summary": "恢复并重置阈值配置为系统默认值",
            "description": "一键重置当前经销商的所有规则阈值为系统出厂默认值。",
            "tags": ["规则与阈值配置"]
        },
        ("/api/v1/records", "get"): {
            "summary": "获取检测判定记录列表",
            "description": "查询该经销商下的所有设备检测历史记录，支持根据故障大类、建议结论、页码等条件进行筛选。",
            "tags": ["检测记录工作台"]
        },
        ("/api/v1/records/stats", "get"): {
            "summary": "获取检测历史统计数据 (看板 Dashboard)",
            "description": "统计已完成的判定记录，给出总数、通过售后数、不予换货数、处理中数的汇总数值。",
            "tags": ["检测记录工作台"]
        },
        ("/api/v1/records/export", "get"): {
            "summary": "导出检测判定历史数据 (CSV/Excel)",
            "description": "导出所有判定数据至 Excel 或 CSV 格式的文件以供下载存档。",
            "tags": ["检测记录工作台"]
        },
        ("/api/v1/records/{record_id}", "get"): {
            "summary": "查询历史记录详情",
            "description": "获取某条历史判定记录的详细属性，包含判定依据（reasons）和决策时保留的阈值快照详情。",
            "tags": ["检测记录工作台"]
        },
        ("/api/v1/records/{record_id}/feedback", "post"): {
            "summary": "提交经销商采纳/驳回判定结论反馈",
            "description": "对判定结果进行回馈：采纳（adopted）或驳回（rejected），驳回时可填写具体拒绝原因，用于持续优化系统。",
            "tags": ["检测记录工作台"]
        }
    }

    # 修改 JSON 里的 API 信息描述，并注入路径/查询参数测试值
    paths = data.get("paths", {})
    for path_str, path_item in paths.items():
        for method_str, operation in path_item.items():
            if method_str in ["get", "post", "put", "delete", "patch"]:
                key = (path_str, method_str)
                if key in translation:
                    info = translation[key]
                    operation["summary"] = info["summary"]
                    operation["description"] = info["description"]
                    operation["tags"] = info["tags"]
                
                # 注入参数级 examples
                params = operation.get("parameters", [])
                for param in params:
                    name = param.get("name")
                    if name == "serial_no":
                        param["example"] = "P2251212806JND44"
                    elif name == "keyword":
                        param["example"] = "P225121"
                    elif name == "fault_category":
                        param["example"] = "Sensor Abnormal"
                    elif name == "verdict":
                        param["example"] = "Replacement Eligible"
                    elif name == "page":
                        param["example"] = 1
                    elif name == "page_size":
                        param["example"] = 20
                    elif name == "record_id":
                        param["example"] = 1
                    elif name == "task_id":
                        param["example"] = 1

    # 注入请求体 Model 里的 JSON schema 属性的 examples 测试值
    schemas = data.get("components", {}).get("schemas", {})
    
    # 1. LoginRequest
    if "LoginRequest" in schemas:
        props = schemas["LoginRequest"].get("properties", {})
        if "email" in props:
            props["email"]["example"] = "dealer@sibionics.com"
        if "password" in props:
            props["password"]["example"] = "demo123456"

    # 2. AgentClassifyRequest
    if "AgentClassifyRequest" in schemas:
        props = schemas["AgentClassifyRequest"].get("properties", {})
        if "message" in props:
            props["message"]["example"] = "My sensor keeps showing abnormal status after warming up"

    # 3. DetectionCreateRequest
    if "DetectionCreateRequest" in schemas:
        props = schemas["DetectionCreateRequest"].get("properties", {})
        if "serial_no" in props:
            props["serial_no"]["example"] = "P2251212806JND44"
        if "fault_category" in props:
            props["fault_category"]["example"] = "Data accuracy"
        if "file_ids" in props:
            props["file_ids"]["example"] = []

    # 4. BatchDetectionCreateRequest
    if "BatchDetectionCreateRequest" in schemas:
        props = schemas["BatchDetectionCreateRequest"].get("properties", {})
        if "serial_nos" in props:
            props["serial_nos"]["example"] = ["P2251212806JND44", "P2251212812WARM", "P2251212809MRF71"]
        if "fault_category" in props:
            props["fault_category"]["example"] = "Sensor Abnormal"

    # 5. FeedbackRequest
    if "FeedbackRequest" in schemas:
        props = schemas["FeedbackRequest"].get("properties", {})
        if "feedback_status" in props:
            props["feedback_status"]["example"] = "adopted"
        if "reject_reason" in props:
            props["reject_reason"]["example"] = "Incorrect fault category classification"

    # 6. ThresholdSaveRequest
    if "ThresholdSaveRequest" in schemas:
        props = schemas["ThresholdSaveRequest"].get("properties", {})
        if "config" in props:
            props["config"]["example"] = {
                "data_accuracy": {
                    "persistently_low": {"max_glucose_24h": 7.8, "low_value": 2.8, "duration_hours": 4},
                    "no_fluctuation": {"max_value": 4.5, "max_delta": 1.0, "duration_hours": 8},
                    "sudden_fluctuation": {"delta": 3.0, "count": 3},
                    "data_deviation": {"min_pairs": 2, "deviation_mmol": 1.1},
                },
                "sensor_falling_off": {"wear_days_limit": 14},
                "sensor_abnormal": {
                    "temporary_abnormal_hours": 3,
                    "warmup_minutes": 60,
                    "waiting_recovery_hours": 3,
                },
                "application_failure": {"min_images": 2, "min_score": 5, "manual_review_score": 3},
            }

    # 过滤或修改下 OpenAPI 的大类标签展示（tags）
    data["tags"] = [
        {"name": "账号与鉴权", "description": "系统认证与令牌管理接口"},
        {"name": "AI 故障分类", "description": "利用 LLM 大模型对用户陈述进行分类识别与智能路由"},
        {"name": "设备管理", "description": "管理和检索 GS1 设备的基础属性与运行状态"},
        {"name": "故障判定与任务", "description": "单设备/批量售后检测自动化判定机制以及异步任务跟踪"},
        {"name": "规则与阈值配置", "description": "提供高度可定制的多版本规则判定参数 of 配置与回滚"},
        {"name": "检测记录工作台", "description": "售后判定历史记录的分页、统计图表、Excel 导出与采纳结果反馈接口"}
    ]

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("Successfully translated and removed emojis/special symbols from apifox_openapi.json!")

if __name__ == '__main__':
    translate_openapi()
