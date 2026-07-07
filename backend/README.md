# Overseas CGM AI Servdesk Backend - 详细参考指南

本指南包含 FastAPI 后端的详细配置项说明、四大诊断规则计算公式、VLM 双组图像检测接口协议以及测试运行步骤。

---

## ⚙️ 1. 环境配置文件详解 (`config.yaml`)

后端核心配置统一由 `config.yaml` 管理，环境差异通过 `.env` / 环境变量注入（如 `${DASHSCOPE_API_KEY}` 等）。

### 📦 配置文件选择机制
系统在启动时，默认加载 `config.yaml`。可通过 `CONFIG_FILE` 环境变量指定其他路径。

配置加载后，其中的参数将自动与 Pydantic 字段进行映射。以下为各配置段的详细定义与作用说明：

### app (应用基础配置)
*   `log_level`: 日志输出级别。可选 `DEBUG`, `INFO`, `WARNING`, `ERROR`。
*   `upload_dir`: 上传截图及凭证文件的本地保存路径（默认为 `uploads`）。
*   `cors_origins`: 跨域允许的来源列表，格式为数组（开发环境下设为 `["*"]`）。
*   `database_url`: 异步数据库连接字符串（`postgresql+asyncpg://...`）。
*   `auto_create_tables`: 布尔值。为 `true` 时，应用启动时会自动检测数据库表结构并执行 seeding 数据导入。

### security (认证配置)
*   `jwt_secret_key`: 签发与校验 JWT Token 的 Secret。字符长度必须大于 32 位以确保安全性。
*   `jwt_algorithm`: 加密算法，默认为 `HS256`。
*   `access_token_expire_minutes`: Token 过期时长，单位为分钟（默认 `480`，即 8 小时）。

### thresholds.default_profile.rules (规则引擎阈值定义)
此部分包含了诊断规则引擎的核心阈值参数：

*   **inaccuracy (数据准确性类规则)**:
    *   `lowPersist.belowMmol`: 持续偏低判定的阈值限值（默认 `2.8` mmol/L）。
    *   `lowPersist.minHours`: 处于偏低区间的最短累计时长（默认 `4` 小时）。
    *   `lowPersist.max24hMmol`: 24小时血糖最大峰值的上限（默认 `7.8` mmol/L），超过此峰值则不判定为持续偏低。
    *   `noFluctuation.floorMmol`: 无波动检测的最大值限度（默认 `4.5` mmol/L）。
    *   `noFluctuation.minHours`: 血糖曲线保持无波动的最小时长（默认 `8` 小时）。
    *   `noFluctuation.maxSwingMmol`: 最大波动允许差值（默认 `1.0` mmol/L），低于此变化量被视为无波动。
    *   `jump.deltaMmol`: 判定为单步异常跳变的相邻点差值阈值（默认 `3.0` mmol/L）。
    *   `jump.consecutive`: 达到判定标准的连续突变点的最小个数（默认 `3` 个）。
*   **deviceAbnormal (传感器故障类规则)**:
    *   `temporaryAbnormalHours`: 临时异常（状态码 6）在判定为故障换新前所需要持续的最短时间，单位为小时（默认 `3` 小时）。
    *   `warmupMinutes`: 设备激活后的预热期阈值，单位为分钟（默认 `60` 分钟）。预热期内发生状态异常（4或5）直接归为初始化异常。
    *   `waitingRecoveryHours`: 等待恢复离线状态的时间限制（默认 `3` 小时）。
*   **detachment (传感器脱落规则)**:
    *   `wearDays`: 判定突发脱落所允许的设备最大佩戴天数（默认 `14` 天）。在此天数内发生 `fallen_off` 则准予换新。
*   **applicationFailure (App软件故障判定得分)**:
    *   `afterSalesScore`: 经过 VLM 分析识别后，准予自动售后换新的最低置信度得分（满分 10，默认 `8`）。
    *   `manualReviewScore`: 进入人工客服二次审核的最低置信度得分（默认 `5`）。低于 5 分直接驳回换新申请。

---

## 📊 2. 血糖图像 VLM 校验与数据比对逻辑

当设备曲线数据不符合常规阈值检测规则，而客服上传了对比截图时，系统会启动 VLM 双组比对算法：

### VLM 校验输入数据协议 (Input JSON Payload)
大模型系统接收 4 张经过 Base64 编码或保存在对象存储中的截图，在分析后，后端期望模型返回如下 JSON 格式：
```json
{
  "glucose_readings": [
    {"value": 5.4, "device_type": "CGM", "unit": "mmol/L", "is_valid": true, "is_reproduced": false},
    {"value": 6.8, "device_type": "BGM", "unit": "mmol/L", "is_valid": true, "is_reproduced": false},
    {"value": 4.1, "device_type": "CGM", "unit": "mmol/L", "is_valid": true, "is_reproduced": false},
    {"value": 6.5, "device_type": "BGM", "unit": "mmol/L", "is_valid": true, "is_reproduced": false}
  ]
}
```

### 规则计算与公式

后端 `src/rules/engine.py` 会将识别出的数据两两配对进行比对判断（第一组：图片0与图片1；第二组：图片2与图片3）。

1.  **单位换算**: 若图片中的 `unit` 识别为 `"mg/dL"` 或 `"mgdl"`，则统一将数值除以 `18.0` 转换为 `mmol/L`。
2.  **绝对偏差判定 (BGM 血糖值值低于或等于 4.2 mmol/L 时)**:
    *   公式：$$\text{AbsDiff} = | \text{CGM} - \text{BGM} |$$
    *   校验规则：当且仅当 $\text{AbsDiff} \ge \text{data\_accuracy\_abs\_threshold}$（默认 `0.83` mmol/L）时，判定该组存在异常偏差。
3.  **相对偏差判定 (BGM 血糖值大于 4.2 mmol/L 时)**:
    *   公式：$$\text{RelPct} = \frac{| \text{CGM} - \text{BGM} |}{\text{BGM}}$$
    *   校验规则：当且仅当 $\text{RelPct} \ge \text{data\_accuracy\_rel\_threshold}$（默认 `20\%` 即 `0.20`）时，判定该组存在异常偏差。
4.  **防作弊校验**: 若任意一张照片的 `is_reproduced` 为 `true`（表示是大屏幕翻拍或造假图片），系统将直接返回不通过，故障子类设为 `Fraud Detected`。
5.  **换新最终判定**: 必须 **两组比对数据全部** 满足绝对或相对异常偏差判定，且未检测到作弊情况时，才会判定为符合换新 `Replacement Eligible`。

---

## 🏃 3. 详细部署与运行操作步骤

### 本地环境配置 (Conda/Poetry)

1.  **前置准备**：确保本地已安装 Python 3.12 及 Poetry 包管理工具。
2.  **安装依赖包**：
    ```bash
    cd backend
    poetry install
    ```
3.  **准备配置文件**：
    拷贝环境变量模板：
    ```bash
    cp .env.example .env
    ```
    修改其中的配置项：
    *   将 `DATABASE_URL` 改为您本地的 PostgreSQL 连接配置。
    *   配置百炼 VLM 密钥 `DASHSCOPE_API_KEY="您的阿里百炼API秘钥"`。

4.  **更新数据库并初始化种子数据**：
    ```bash
    PYTHONPATH=. poetry run alembic upgrade head
    ```
    该操作会在数据库内创建全部表结构，并灌入默认登录用户：
    *   用户名：`christest@sibionics.com`
    *   密码：`password123`
    *   角色：`manager`

5.  **启动后端调试服务器**：
    ```bash
    bash scripts/run-local.sh
    ```
    * 终端日志会输出 `Uvicorn running on http://0.0.0.0:8000`。
    * 服务已启动 reload 热更新，修改 Python 代码后服务会自动重载。

---

## 🧪 4. 测试集与质量验证指南

项目通过 Pytest 提供了近乎完整的自动化测试套件：

### 运行全部测试用例
```bash
poetry run pytest
```

### 运行特定测试文件
*   **诊断规则引擎算法测试**：验证四大类型规则边界值、血糖比对偏差公式等核心计算逻辑。
    ```bash
    poetry run pytest tests/test_rules.py
    ```
*   **大模型意图分类及 VLM 测试**：
    ```bash
    poetry run pytest tests/test_detection_vlm_refs.py
    ```
*   **诊断会话流程管理测试**：验证批次任务的状态转移逻辑。
    ```bash
    poetry run pytest tests/test_device_detection_resume.py
    ```
