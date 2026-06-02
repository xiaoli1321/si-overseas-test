# SIBIONICS 海外 CGM AI 售后客服系统 — 部署手册

---

## 前置条件

- Docker & Docker Compose（服务器）
- 阿里云德国 RDS PostgreSQL（已分配）
- 阿里云百炼 DashScope API Key
- 域名（如 `test-overseas-agent.sisensing.com`）解析到服务器 IP

---

## 部署流程

### 1. 克隆项目

```bash
git clone <repo-url> si-overseas-backend
cd si-overseas-backend
```

### 2. 配置环境变量

```bash
# 预发布
cp .env.staging.example .env.staging
# 生产
cp .env.prod.example .env.prod
```

编辑 `.env.staging` 或 `.env.prod`，至少填写以下变量：

| 变量                    | 说明                                    |
| ----------------------- | --------------------------------------- |
| `DATABASE_URL`          | RDS 连接串（已填写阿里云德国 RDS 地址） |
| `JWT_SECRET_KEY`        | JWT 签名密钥，至少 32 字符              |
| `DASHSCOPE_API_KEY`     | 阿里云百炼 API Key                      |
| `OVERSEAS_API_USERNAME` | 海外设备 API 用户名                     |
| `OVERSEAS_API_PASSWORD` | 海外设备 API 密码                       |
| `PREVIEW_ALLOWED_HOSTS` | 前端域名白名单，逗号分隔                |

### 3. 构建镜像

```bash
sudo bash build.sh
```

构建两个镜像：`si-overseas-backend:latest`、`si-overseas-frontend:latest`。

> 如修改了代码，需要重新执行此步骤。

### 4. 启动服务

**预发布：**

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

- 前端 `http://<服务器IP>:8090`
- 后端 `http://<服务器IP>:8000`（Swagger: `/docs`）

**生产：**

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

- 前端 `http://<服务器IP>:80`
- 后端不暴露端口到宿主机

首次启动时 `AUTO_CREATE_TABLES=true` 自动建表、数据迁移并写入种子数据（默认测试账号 `christest@sibionics.com` / `password123`），等价于 Alembic migrate + seed。生产环境首次部署完成后建议将 `AUTO_CREATE_TABLES` 改为 `false`，后续表结构变更通过 Alembic 管理。

### 5. 放行安全组

在阿里云安全组添加入方向规则：

| 环境   | 端口                       | 协议 | 授权对象              |
| ------ | -------------------------- | ---- | --------------------- |
| 预发布 | 8090（前端）、8000（后端） | TCP  | `0.0.0.0/0` 或运维 IP |
| 生产   | 80（前端）                 | TCP  | `0.0.0.0/0` 或 CDN IP |

### 6. 验证

```bash
# 健康检查（返回 200 OK）
curl -I http://<服务器IP>:<端口>/
curl http://<服务器IP>:<端口>/health
# API 文档
curl http://<服务器IP>:8000/docs
```

域名指向服务器后，前端 `preview.allowedHosts` 通过 `PREVIEW_ALLOWED_HOSTS` 环境变量配置，无需修改代码。

---

## 常用操作

### 重启

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging restart
```

### 查看日志

```bash
# 所有服务
docker compose -f docker-compose.staging.yml logs -f
# 单个服务
docker compose -f docker-compose.staging.yml logs -f backend
docker compose -f docker-compose.staging.yml logs -f frontend
```

### 重建单个服务

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --no-deps --force-recreate <service>
```

---

## 环境变量参考

### 数据库

| 变量                 | 预发布         | 生产     | 说明                                                                      |
| -------------------- | -------------- | -------- | ------------------------------------------------------------------------- |
| `DATABASE_URL`       | （RDS 连接串） | 同       | asyncpg 连接串，格式: `postgresql+asyncpg://user:pass@host:port/dbname`   |
| `DB_SCHEMA`          | `staging`      | `public` | PostgreSQL schema。通过 pydantic-settings `server_settings` 机制设置      |
| `AUTO_CREATE_TABLES` | `true`         | `true`   | 启动时自动建表并播种数据。首次部署后建议改为 `false`，后续用 Alembic 管理 |

### 认证

| 变量             | 说明                       |
| ---------------- | -------------------------- |
| `JWT_SECRET_KEY` | JWT 签名密钥，至少 32 字符 |

### Vision LLM (Qwen-VL)

| 变量                | 默认值                                                                          | 说明                                 |
| ------------------- | ------------------------------------------------------------------------------- | ------------------------------------ |
| `DASHSCOPE_API_KEY` | —                                                                               | 通义千问多模态接口 API Key           |
| `VLM_BASE_URL`      | `https://ws-q1u9plrwjmlp9bwu.eu-central-1.maas.aliyuncs.com/compatible-mode/v1` | 多模态模型 Endpoint Base URL         |
| `INTENT_MODEL`      | `deepseek-v4-flash`                                                             | 意图识别所使用的文本大模型名称       |
| `VLM_MODEL`         | `qwen3.5-flash`                                                                 | 视觉分析多模态大模型名称             |
| `VLM_ENABLED`       | `true`                                                                          | VLM 图像分析开关，`false` 走离线模拟 |
| `VLM_MAX_RETRIES`   | `2`                                                                             | 接口失败重试次数                     |

### 批量判定

| 变量                 | 默认值 | 说明                             |
| -------------------- | ------ | -------------------------------- |
| `BATCH_MAX_SERIALS`  | `50`   | 单次批量最大序列号数量           |
| `BATCH_CONCURRENCY`  | `5`    | 判定时最大并发数（保护后台服务） |
| `TASK_STALE_MINUTES` | `30`   | 会话异常超时挂起判定限制分钟数   |

### 文件存储

| 变量                            | 默认值                          | 说明                                          |
| ------------------------------- | ------------------------------- | --------------------------------------------- |
| `FILE_STORAGE_BACKEND`          | `local`                         | `local` = 本地文件系统; `oss` = 阿里云 OSS    |
| `UPLOAD_DIR`                    | `uploads`                       | 本地存储路径                                  |
| `OSS_ENDPOINT`                  | `oss-eu-central-1.aliyuncs.com` | OSS Endpoint                                  |
| `OSS_BUCKET`                    | `si-agent-overseas-test`        | OSS 存储桶名称                                |
| `OSS_ACCESS_KEY_ID`             | —                               | OSS Access Key ID                             |
| `OSS_ACCESS_KEY_SECRET`         | —                               | OSS Access Key Secret                         |
| `OSS_KEY_PREFIX`                | `si-overseas`                   | OSS 对象键前缀                                |
| `OSS_PUBLIC_BASE_URL`           | —                               | OSS 公网访问基础 URL（留空则使用 signed URL） |
| `OSS_USE_SIGNED_URL`            | `true`                          | 是否使用签名 URL                              |
| `OSS_SIGNED_URL_EXPIRE_SECONDS` | `600`                           | 签名 URL 有效期（秒）                         |

### LangSmith 追踪

| 变量                   | 默认值        | 说明                                                       |
| ---------------------- | ------------- | ---------------------------------------------------------- |
| `LANGCHAIN_TRACING_V2` | `true`        | 启用 LangSmith 追踪（自动收集 LangChain + LLM 调用）       |
| `LANGCHAIN_PROJECT`    | `si-overseas` | LangSmith 项目名                                           |
| `LANGCHAIN_API_KEY`    | —             | LangSmith API Key（从 <https://smith.langchain.com> 获取） |

### 海外设备 API

| 变量                               | 默认值                                             | 说明                                     |
| ---------------------------------- | -------------------------------------------------- | ---------------------------------------- |
| `OVERSEAS_API_ENABLED`             | `true`                                             | 是否启用海外真实 API                     |
| `OVERSEAS_API_LOGIN_URL`           | `https://cgm.sibionics.io/center/admin/user/login` | 登录接口地址（获取 access_token）        |
| `OVERSEAS_API_BASE_URL`            | `https://cgm-ce.sisensing.com`                     | 设备详情接口基地址                       |
| `OVERSEAS_API_DEVICE_DETAIL_PATH`  | `/system/expand/oversea/deviceDetail`              | 设备详情接口路径                         |
| `OVERSEAS_API_USERNAME`            | —                                                  | API 登录用户名                           |
| `OVERSEAS_API_PASSWORD`            | —                                                  | API 登录密码                             |

### 前端

| 变量                    | 预发布默认值                        | 生产默认值                     | 说明                       |
| ----------------------- | ----------------------------------- | ------------------------------ | -------------------------- |
| `PORT`                  | `8090`                              | `80`                           | 宿主机映射端口             |
| `PROXY_TARGET`          | `http://backend:8000`               | 同                             | API 代理目标（容器内 DNS） |
| `PREVIEW_ALLOWED_HOSTS` | `test-overseas-agent.sisensing.com` | `overseas-agent.sisensing.com` | 域名白名单，逗号分隔       |

### 日志

| 变量        | 预发布  | 生产   |
| ----------- | ------- | ------ |
| `LOG_LEVEL` | `DEBUG` | `INFO` |

---

## 架构说明

```bash
浏览器 ──:8090/80 ──▶ 前端容器 (vite preview :4173)
                         │
                         │ 代理 /api/*  (PROXY_TARGET)
                         ▼
后端容器 (uvicorn :8000) ──▶ 阿里云德国 RDS
```

- 前端通过 Vite Preview 内置代理将 `/api` 请求转发到后端容器，浏览器只需访问前端端口
- 数据库使用阿里云德国 RDS，不在 Docker Compose 中管理
- 上传文件存储在阿里云 OSS 中（`FILE_STORAGE_BACKEND=oss`）
- 健康检查端点：`HEAD /`、`GET /`、`GET /health`
