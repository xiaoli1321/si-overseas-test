# 故障检测开放 API 实现计划

> 面向经销商（B2B）的设备故障检测开放接口。
> 复用 web 端核心检测逻辑，覆盖 **4 大故障类型**，提供异步创建 + 轮询的集成方式。

| 项目 | 说明 |
|------|------|
| 文档版本 | v1.0 |
| 日期 | 2026-07-02 |
| 适用对象 | 后端开发、经销商对接方 |
| 依赖基线 | `backend/src` 当前 `main` 分支 |

---

## 一、背景与目标

### 1.1 业务背景

当前系统已通过 web 端 (`/api/v1/detections`) 实现了完整的设备售后故障诊断能力，诊断逻辑沉淀在 `services/detections.py` 的 `execute_detection()` 和 `rules/engine.py` 的 `run_rules()` 中。经销商目前只能通过人工登录 web 工作台使用。

为支持经销商将故障检测能力**集成到自有系统**（ERP、售后系统、小程序等），需要提供一套稳定的开放 API。

### 1.2 目标

| 目标 | 验收标准 |
|------|----------|
| 覆盖 4 大故障类型 | `Data accuracy` / `Sensor falling off` / `Sensor Abnormal` / `Application failure` 均可创建检测并返回结果 |
| 与 web 端判定结果一致 | 同一 SN + 故障类型 + 阈值配置下，开放 API 与 web 端的 `verdict` / `fault_subtype` 完全一致 |
| 复用现有核心逻辑 | 不重复实现检测算法，直接调用 `execute_detection()` / `run_rules()` |
| 提供清晰的集成路径 | 经销商可仅凭本文档完成对接（认证 → 上传 → 创建 → 轮询 → 拿结果） |
| 不影响 web 端 | 开放 API 路由独立于 `/api/v1/`，互不干扰 |

### 1.3 非目标 (Non-Goals)

- ❌ 不改造现有 web 端 `/api/v1/` 路由及其响应格式
- ❌ 不替换 JWT 为 API Key / OAuth2（本期决策：复用现有 JWT 登录）
- ❌ 不实现回调通知（Webhook / WebSocket），本期仅支持轮询
- ❌ 不实现同步阻塞检测端点（VLM 耗时不稳定，同步易超时）
- ❌ 不在本期实现独立的开放 API 限流/计量（由网关层后续承接）

---

## 二、核心设计决策

下表记录已与需求方对齐的关键决策，实现过程中**不得擅自更改**：

| 决策项 | 选定方案 | 备选（已否决） | 理由 |
|--------|----------|----------------|------|
| **鉴权方式** | 复用现有 JWT 登录 | API Key 签名 / OAuth2 client_credentials | 上线最快，鉴权链路已验证；经销商账号即 web 账号 |
| **检测模式** | 异步（创建 + 轮询） | 同步阻塞 / 两种都支持 | VLM 大模型耗时 5~60s，异步不阻塞、支持批量 |
| **图片接收** | 先上传再引用（复用 `/files/upload`） | multipart 一次性 / 外部 URL | 完全复用现有文件管理逻辑，零重复代码 |
| **命名空间** | `/openapi/v1/` | `/api/v1/open/` | 与 web 物理隔离，便于网关层单独限流/白名单 |

---

## 三、4 大故障类型详解

> 定义源：`backend/src/schemas/domain.py:14` 的 `FaultCategory` 字面量。
> 判定逻辑源：`backend/src/rules/engine.py`。

### 3.1 故障类型总览

| 编号 | fault_category | 含义 | 判定依据 | 是否需要图片 |
|------|----------------|------|----------|--------------|
| ① | `Data accuracy` | 血糖数据准确性异常 | 血糖时序曲线规则 + 可选 CGM/BGM 对比图 VLM | 可选（曲线不命中时需 4 张对比图） |
| ② | `Sensor falling off` | 传感器脱落 | 设备脱落状态 + 佩戴天数 | 否 |
| ③ | `Sensor Abnormal` | 传感器异常 | 设备状态码 + 告警时长 + 内部值 | 否 |
| ④ | `Application failure` | 贴敷/操作失败 | 用户上传凭证图 VLM 识别 | **必需**（至少 2 张） |

### 3.2 各类型子类 (fault_subtype) 与判定结果 (verdict)

判定结果 `verdict` 为三值：`Replacement Eligible`（符合换新）/ `Not Eligible`（不符合）/ `Under Review`（人工审核）。

#### ① Data accuracy（血糖数据准确性）
- 输入：海外设备血糖时序数据（系统自动拉取，经销商无需提供）
- 自动规则（按优先级匹配，命中即出结果）：
  - `Persistently Low`（持续偏低）：24h 峰值 ≤ 阈值且存在 ≥ 4h 低值段 → `Replacement Eligible`
  - `No Fluctuation`（无波动/平线）：存在 ≥ 8h 波动 ≤ 1.0 mmol/L 的平直段 → `Replacement Eligible`
  - `Sudden Fluctuation`（突变跳点）：连续 ≥ 3 次跳变 ≥ 3.0 mmol/L → `Replacement Eligible`
- 兜底：`Data Deviation Review Required`（需提供 CGM/BGM 对比图）
- 若经销商提供 ≥4 张对比图：走 VLM 分析 CGM vs BGM 读数偏差，48h 内看绝对差、48h 外看相对差 → `Replacement Eligible` / `Not Eligible`

#### ② Sensor falling off（传感器脱落）
- 输入：设备状态（系统自动拉取）
- `Sudden Fall Off`：已脱落 + 佩戴 < 14 天 → `Replacement Eligible`
- `Suspected Fall Off`：疑似脱落 → `Not Eligible`（需先人工指导）
- `No Fall Off`：无脱落 → `Not Eligible`

#### ③ Sensor Abnormal（传感器异常）
- 输入：设备状态码 + 告警记录（系统自动拉取）
- 命中任一条件 → `Replacement Eligible`：
  - `Temporary Abnormal`：状态 6 + 异常时长 > 3h
  - `Replace Device - Init`：状态 4 + 内部值 0/1 + 佩戴 ≤ 60min
  - `Replace Device - Use`：状态 4 + 内部值 2 + 佩戴 > 60min
  - `Low Recovery Possibility`：状态 1 + 告警 2 + 异常 > 3h
  - `Initialization Abnormal`：状态 5 + 佩戴 ≤ 60min

#### ④ Application failure（贴敷/操作失败）
- 输入：**经销商必须上传 ≥2 张凭证图**
- 流程：VLM 识别图片特征 → 规则引擎按公式打分
- 评分公式：`(10×针头外露 + 8×胶布脱落 + 7×植入器损坏) × 设备存在 × (1 - 翻拍)`
- `score ≥ 7.0` → `Replacement Eligible`
- `5.0 ≤ score < 7.0` → `Under Review`
- `score < 5.0` / 设备不存在 / 翻拍 → `Not Eligible`
- 子类：`Exposed Electrodes` / `Adhesive detaching` / `Implanter damage` / `Invalid Evidence` / `Reproduced Evidence` / `No Application Failure`

---

## 四、系统架构与集成流程

### 4.1 架构分层

```
┌─────────────────────────────────────────────────────────┐
│  经销商系统 (ERP / 售后系统 / 小程序)                     │
└─────────────────────────────────────────────────────────┘
                       │ HTTPS + Bearer JWT
                       ▼
┌─────────────────────────────────────────────────────────┐
│  开放 API 层 (/openapi/v1/)   ← 本期新增                  │
│  api/openapi/*.py                                        │
│  - 薄路由，仅做参数校验 + 调 service + 包装响应           │
└─────────────────────────────────────────────────────────┘
                       │ 复用
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Service 层 (services/)            ← 完全复用，不改动     │
│  - detections.execute_detection()  检测编排               │
│  - detections.process_detection_record()  后台任务        │
│  - files.save_uploaded_file()      文件落库               │
│  - thresholds.current_threshold()  阈值快照               │
└─────────────────────────────────────────────────────────┘
                       │ 复用
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Rules 层 (rules/engine.py)       ← 完全复用，不改动     │
│  - run_rules()  确定性判定（4 大故障类型）               │
└─────────────────────────────────────────────────────────┘
                       │ 复用
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Integrations 层 (integrations/)  ← 完全复用，不改动     │
│  - overseas_client  海外设备/血糖/告警 API                │
│  - vlm (QwenVlClient)  视觉大模型                        │
└─────────────────────────────────────────────────────────┘
```

**关键原则**：开放 API 是 web API 的"精简同构"——同样的 service、同样的 rules、同样的 integrations，**唯一差异是路由前缀和响应字段裁剪**。判定结果与 web 端在数学上保证一致。

### 4.2 经销商完整集成流程

```
┌─────────┐   1. POST /openapi/v1/auth/login (邮箱+密码)
│         │ ─────────────────────────────────────────────►  拿到 access_token
│         │
│         │   2. POST /openapi/v1/files/upload (multipart)   ─ 如需图片 ─┐
│         │ ─────────────────────────────────────────────►  拿到 file_id │
│ 经销商  │                                                            │ 可重复
│  系统   │   3. POST /openapi/v1/detections                          ◄──┘
│         │      { serialNo, faultCategory, fileIds: [...] }
│         │ ─────────────────────────────────────────────►  拿到 detectionId (status=processing)
│         │
│         │   4. GET /openapi/v1/detections/{detectionId}  (轮询, 建议 3~5s 间隔)
│         │ ─────────────────────────────────────────────►  status: processing → completed/failed
│         │
│         │   5. (completed) 读取 verdict / faultSubtype / evidence
└─────────┘
```

---

## 五、API 接口定义

> 所有端点统一响应包络：`{ "code": 0, "message": "success", "data": {...} }`
> 错误响应：`code` 非 0，`message` 为错误描述，`data` 为 null。

### 5.1 端点清单

| # | 方法 | 路径 | 说明 | 鉴权 |
|---|------|------|------|------|
| 1 | POST | `/openapi/v1/auth/login` | 账号密码登录，换取 JWT | 否 |
| 2 | POST | `/openapi/v1/files/upload` | 上传凭证图片，返回 file_id | 是 |
| 3 | POST | `/openapi/v1/detections` | 创建单设备故障检测任务 | 是 |
| 4 | GET  | `/openapi/v1/detections/{id}` | 查询检测任务状态与结果 | 是 |

---

### 5.2 接口 1：登录获取 Token

**请求**
```http
POST /openapi/v1/auth/login
Content-Type: application/json

{
  "email": "dealer@sibionics.com",
  "password": "******"
}
```

**响应 `data`**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIs...",
  "tokenType": "bearer",
  "expiresIn": 28800,
  "distributor": {
    "id": "12",
    "name": "XX Distributor",
    "type": "Distributor"
  }
}
```

> 复用 `services/auth.py:login()`，JWT 过期时间 8 小时（`access_token_expire_minutes`）。

---

### 5.3 接口 2：上传凭证图片

**请求**
```http
POST /openapi/v1/files/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <二进制图片>
```

**响应 `data`**
```json
{
  "fileId": "file-83eee325e6314658a4cf9ce3f3a5ad71",
  "filename": "sensor_photo_01.jpg",
  "mimeType": "image/jpeg",
  "fileSize": 245678
}
```

> 复用 `services/files.py:save_uploaded_file()`。
> 约束：单文件 ≤ 10MB；仅接受 `image/*` 类型。

---

### 5.4 接口 3：创建故障检测任务（异步）

**请求**
```http
POST /openapi/v1/detections
Authorization: Bearer <token>
Content-Type: application/json

{
  "serialNo": "P2251212806JND44",
  "faultCategory": "Application failure",
  "fileIds": ["file-83eee325e6314658a4cf9ce3f3a5ad71", "file-9b2c..."]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `serialNo` | string | 是 | 设备序列号，自动转大写 |
| `faultCategory` | string | 是 | 枚举：`Data accuracy` / `Sensor falling off` / `Sensor Abnormal` / `Application failure` |
| `fileIds` | string[] | 否 | 凭证图片 ID 列表。`Application failure` 必填 ≥2 张；`Data accuracy` 曲线不命中时需 ≥4 张 |

**响应 `data`**（立即返回，此时检测在后台进行）
```json
{
  "detectionId": "1001",
  "serialNo": "P2251212806JND44",
  "faultCategory": "Application failure",
  "status": "processing",
  "createdAt": "2026-07-02T08:30:00Z"
}
```

> 内部流程：`create_detection()` 建记录 → `background_tasks.add_task(process_detection_record)` → 返回。
> `status` 取值：`processing`（进行中）/ `completed`（完成）/ `failed`（失败）。

---

### 5.5 接口 4：查询检测结果（轮询）

**请求**
```http
GET /openapi/v1/detections/{detectionId}
Authorization: Bearer <token>
```

**响应 `data`**（status=processing 时，verdict 等字段为 null）
```json
{
  "detectionId": "1001",
  "serialNo": "P2251212806JND44",
  "faultCategory": "Application failure",
  "status": "completed",
  "verdict": "Replacement Eligible",
  "faultSubtype": "Exposed Electrodes",
  "issueDetected": true,
  "reasonSummary": "Vision score 10.0 was calculated... Matched scenario: Exposed Electrodes with confidence 10.0/10.",
  "thresholdVersion": 3,
  "createdAt": "2026-07-02T08:30:00Z",
  "completedAt": "2026-07-02T08:30:18Z",
  "evidence": {
    "matchedRules": ["application_failure.exposed_electrodes"],
    "vision": {
      "score": 10.0,
      "finalScenario": "Exposed Electrodes",
      "finalConfidence": 10.0,
      "features": {
        "isCgmDevicePresent": true,
        "isReproducedPhoto": false,
        "needleExposed": true,
        "adhesiveDetached": false,
        "implanterDamage": false
      }
    }
  },
  "errorMessage": null
}
```

**各故障类型的 evidence 结构差异**（与 web 端 `schemas/evidence.py` 完全一致）：

| fault_category | evidence 关键字段 |
|----------------|-------------------|
| `Data accuracy` | `device`, `glucoseSeriesUrl`, `dataAccuracyDetails`（含 persistently_low/no_fluctuation/sudden_fluctuation 详情及触发时段） |
| `Sensor falling off` | `device`（含 wearDays, fallOffStatus） |
| `Sensor Abnormal` | `device`, `alarm`（含 latestAlarmStatus, abnormalDurationMinutes, abnormalStartedAt） |
| `Application failure` | `device`, `vision`（含 score, scenarios, features）, `implantationScanner` |

> 轮询建议：首次创建后等待 3s 开始轮询，间隔 3~5s，VLM 类型最长可能 60s。建议设置总超时 120s。

---

## 六、数据模型与变更

### 6.1 复用现有表（无需 schema 变更）

| 表 | 用途 |
|----|------|
| `users` | 经销商账号（已有 `role=dealer`） |
| `distributors` | 经销商主体 |
| `detect_records` | 检测记录（开放 API 创建的记录与 web 端共用此表） |
| `uploaded_files` | 上传文件（含归属 user_id） |
| `thresholds` | 阈值配置（按 user_id 生效） |
| `audit_logs` | 审计日志 |

**结论：本期无数据库迁移，零 schema 变更。** 这是因为开放 API 本质上是现有检测能力的另一个入口，数据模型完全一致。

### 6.2 数据隔离

- 开放 API 创建的 `detect_records` 自动绑定当前 JWT 用户的 `user_id`
- 文件归属校验沿用 `validate_file_ownership()`，跨账号 file_id 直接拒绝（返回 `42201`）
- 经销商只能查询/操作自己的检测记录，与 web 端数据隔离规则完全一致

---

## 七、实现任务分解

### 7.1 新增文件清单

```
backend/src/
├── api/
│   └── openapi/                      ← 新增目录
│       ├── __init__.py
│       ├── auth.py                   ← 登录端点（薄封装）
│       ├── files.py                  ← 文件上传端点（薄封装）
│       └── detections.py             ← 检测创建 + 查询端点
├── schemas/
│   └── openapi.py                    ← 新增：开放 API 专用响应模型
└── (main.py 注册新路由)
```

### 7.2 任务清单（按依赖顺序）

#### 任务 1：Schema 定义（`schemas/openapi.py`）
- 定义 `OpenApiLoginRequest`, `OpenApiTokenResponse`
- 定义 `OpenApiFileUploadResponse`（精简版，只暴露 `fileId/filename/mimeType/fileSize`）
- 定义 `OpenApiDetectionCreateRequest`（复用 `FaultCategory` 枚举）
- 定义 `OpenApiDetectionResponse`（精简版，相比 web 的 `record_to_frontend` 裁掉 `presentation`/`dealerId` 等内部字段，只保留集成方需要的）
- **验收**：Pydantic 模型可通过 `model_validate` 从 `DetectRecord` ORM 对象构造

#### 任务 2：响应转换函数（`schemas/openapi.py`）
- 新增 `record_to_openapi(record: DetectRecord) -> dict`，复用 `DetectRecord` 字段，输出 5.5 节格式
- **验收**：`status=processing` 时 verdict/faultSubtype 为 null；`status=completed` 时完整返回 evidence

#### 任务 3：API 路由（`api/openapi/*.py`）
- `auth.py`：`POST /auth/login` → 调 `services.auth.login`，响应用 `OpenApiTokenResponse`
- `files.py`：`POST /files/upload` → 调 `services.files.save_uploaded_file`，响应用 `OpenApiFileUploadResponse`
- `detections.py`：
  - `POST /detections` → 调 `create_detection` + `background_tasks.add_task(process_detection_record)`（**与 web 端 `api/detections.py:42-50` 完全一致的业务调用**）
  - `GET /detections/{id}` → 调 `repositories.store.get_record`，用 `record_to_openapi` 输出
- 所有路由 `router = APIRouter(...)`，**不带 prefix**（prefix 由 main.py 统一加 `/openapi/v1`）
- **验收**：4 个端点均可在 Swagger `/openapi/v1/docs` 看到；鉴权依赖沿用 `get_current_user`

#### 任务 4：主应用注册（`main.py`）
```python
from src.api.openapi import auth, files, detections

app.include_router(auth.router, prefix="/openapi/v1")
app.include_router(files.router, prefix="/openapi/v1")
app.include_router(detections.router, prefix="/openapi/v1")
```
- **验收**：`/health` 与现有 `/api/v1/*` 路由不受影响

#### 任务 5：审计日志
- 开放 API 的创建/上传操作同样调 `record_audit_event`，`action` 用 `openapi.detection.create` / `openapi.file.upload` 以便与 web 区分来源
- **验收**：`audit_logs` 表可按 action 前缀区分 web vs openapi 流量

#### 任务 6：测试
- `tests/test_openapi_auth.py`：登录成功/失败
- `tests/test_openapi_detection.py`：
  - 单设备 4 种 fault_category 各创建一次，断言 status 流转
  - `Application failure` 无图片 → 返回 Under Review（`Insufficient Images`）
  - 跨账号查询 → `40401`
  - file_id 跨账号 → `42201`
  - **关键回归**：同一 SN + 配置，开放 API 与 web API 的 verdict 完全一致
- **验收**：`PYTHONPATH=. pytest tests/test_openapi_*` 全绿

#### 任务 7：接口文档与示例
- 在 `backend/README.md` 或独立 `docs/open-api/` 增加经销商对接指引
- 提供一个最小可运行的 Python `requests` 示例脚本
- **验收**：新成员仅凭文档可跑通"登录→上传→创建→轮询→拿结果"

---

## 八、复用关系对照表

> 说明开放 API 与 web API 在每一层的对应关系，证明"判定逻辑零分叉"。

| 能力点 | web API (`/api/v1/`) | 开放 API (`/openapi/v1/`) | 是否复用同一实现 |
|--------|----------------------|---------------------------|------------------|
| 登录 | `api/auth.py` → `services.auth.login` | `api/openapi/auth.py` → **`services.auth.login`** | ✅ 同一函数 |
| 当前用户 | `get_current_user` (deps.py) | **`get_current_user`** | ✅ 同一依赖 |
| 文件上传 | `api/files.py` → `services.files.save_uploaded_file` | `api/openapi/files.py` → **`services.files.save_uploaded_file`** | ✅ 同一函数 |
| 文件归属校验 | `services.detections.validate_file_ownership` | **`validate_file_ownership`** | ✅ 同一函数 |
| 创建检测记录 | `services.detections.create_detection` | **`create_detection`** | ✅ 同一函数 |
| 后台执行 | `process_detection_record` → `execute_detection` | **`process_detection_record`** | ✅ 同一任务 |
| 海外数据拉取 | `integrations.get_cgm_client()` | **同上**（在 execute_detection 内部） | ✅ 同一客户端 |
| VLM 分析 | `integrations.vlm.QwenVlClient` | **同上**（在 execute_detection 内部） | ✅ 同一客户端 |
| 规则判定 | `rules.engine.run_rules` | **同上**（在 execute_detection 内部） | ✅ 同一引擎 |
| 阈值快照 | `services.thresholds.current_threshold` | **同上**（在 execute_detection 内部） | ✅ 同一函数 |
| 证据链校验 | `schemas/evidence.py` 各 Evidence 模型 | **同上**（在 execute_detection 内部） | ✅ 同一模型 |
| **唯一差异** | 响应用 `record_to_frontend`（含 presentation 等内部字段） | 响应用 `record_to_openapi`（裁剪为集成方字段） | ⚠️ 仅响应组装不同 |

> **一致性保证**：因为 `execute_detection` → `run_rules` 这条核心链路被两个 API 完全共享，所以对于相同的 `(serial_no, fault_category, file_ids, user_id)`，两个 API 产出的 `verdict` / `fault_subtype` / `matched_rules` 在数学上保证一致。差异只可能在并发时序（海外 API 缓存、VLM 随机性）导致，这与 web 端自身重试的差异范围相同。

---

## 九、错误码与异常处理

沿用项目现有错误码（`architecture-guidelines.md`）：

| code | HTTP | 场景 |
|------|------|------|
| `40001` | 400 | 参数校验失败（如 faultCategory 非法、serialNo 为空） |
| `40101` | 401 | token 缺失/过期/无效 |
| `40401` | 404 | detectionId 不存在或跨账号 |
| `42201` | 422 | 业务校验失败（如 file_id 不存在/跨账号、Application failure 图片不足） |
| `50001` | 500 | 系统异常（VLM 超时、海外 API 不可达等，记录会落为 `status=failed`） |

**检测失败的处理**：后台任务异常会被 `process_detection_record` 捕获，记录 `status=failed` + `errorMessage`。经销商轮询时会拿到 `status=failed`，可读取 `errorMessage`，并建议提供"重试"端点（见 7.1 后续迭代）。

---

## 十、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| VLM 大模型耗时波动（5~60s） | 经销商轮询体验差 | 文档明确建议轮询间隔 3~5s、总超时 120s；后续可加 Webhook |
| 经销商用账号密码对接，密码泄露 | 安全风险 | 文档建议经销商申请专用对接账号、密码不落代码；后续可加 IP 白名单 |
| 海外 API 限流/不可达 | 检测失败率升高 | 已有重试机制；`status=failed` 时 errorMessage 可读；建议经销商实现重试 |
| 开放 API 与 web 共用 `detect_records` 表 | 数据混杂 | `audit_logs.action` 用 `openapi.` 前缀区分；必要时后续加 `source` 字段 |
| 复用 JWT 导致开放 API 与 web 共享 token 配额 | 无实际影响（当前无 token 限流） | 监控即可，后续网关层处理 |

---

## 十一、后续迭代（本期不做，仅记录）

1. **Webhook 回调**：检测完成后主动 POST 经销商回调地址，免轮询
2. **API Key / OAuth2**：替代账号密码，更安全的机器对机器鉴权
3. **批量检测端点**：`POST /openapi/v1/detections/batch`，复用 `create_batch_detection`
4. **重试端点**：`POST /openapi/v1/detections/{id}/retry`，复用 `retry_record`
5. **限流与计量**：按经销商维度 QPS 限制、调用次数统计
6. **沙箱环境**：提供 mock 数据的测试环境，经销商免消耗真实 VLM 配额

---

## 十二、验收 Checklist

实现完成后逐项确认：

- [ ] 4 个端点（login / upload / create / query）均可用，Swagger 文档完整
- [ ] 4 大故障类型均可创建检测任务并返回结果
- [ ] `Application failure` 不带图片时返回 `Under Review` + `Insufficient Images`
- [ ] `Data accuracy` 自动规则命中（如平线）时无需图片即可出结果
- [ ] 同一 SN + 配置下，开放 API 与 web API verdict 一致（回归测试通过）
- [ ] 跨账号访问 detectionId / file_id 正确返回 40401 / 42201
- [ ] `audit_logs` 中 openapi 流量可按 action 前缀识别
- [ ] `/api/v1/*` 现有路由全部回归通过，web 端无任何影响
- [ ] 新增测试 `PYTHONPATH=. pytest tests/test_openapi_*` 全绿
- [ ] `pre-commit run --all-files` 通过
- [ ] 经销商对接文档 + requests 示例脚本可跑通完整流程
