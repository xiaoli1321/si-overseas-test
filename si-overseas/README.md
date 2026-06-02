# SIBIONICS 海外 CGM 智能售后客服前端 (SI Overseas Fault Detect Demo)

本项目是基于 **Vue 3** + **TypeScript** + **Vite** 构建的海外 CGM 智能售后客服系统的原型前端。该系统利用 Vue 3 接管状态控制并与后端 FastAPI 接口对接，实现智能售后检测流程。

---

## 🎨 还原设计与 Legacy HTML 挂载机制

为了保持与原始设计图、原有系统页面视觉规范和动画微交互的 100% 绝对对齐，前端项目在重构时采用了创新的**视觉还原机制**：

1.  **静态资源还原 (`index_aligned_to_doc...html`)**：
    项目运行时会读取并挂载预设的原始 HTML 文档中的 DOM 骨架和基础 CSS 规则，确保包括阴影、布局卡片、折叠面板等底层样式与原有静态视觉完全吻合。
2.  **Vue 接管交互与动态渲染**：
    在 `src/legacy/LegacyOriginalApp.vue` 和 `src/legacy/originalHtml.ts` 中，通过脚本自动提取骨架中需要保留的部分，并利用 Vue 3 的模板（SFC）和状态控制器接管交互行为，实现从静态页面向动态单页面应用（SPA）的无缝升级。
3.  **样式注入 (`src/main.ts`)**：
    在 `main.ts` 入口文件中，系统会在 Vue 应用实例挂载（mount）之前，优先将原始页面的全局 `<style>` 样式表和自定义 CSS 变量注入至页面的 `<head>` 中，确保全组件共享风格。

---

## 📁 页面视图 (`src/views/`) 与核心组件介绍

系统各页面和路由按以下逻辑流转：

### 1. LoginView (`/`)
*   **功能**：客服人员和系统管理员的登录入口。
*   **特性**：为了测试与演示方便，登录界面已预填了默认测试账户（邮箱 `christest@sibionics.com`，密码 `password123`），可直接点击登录。

### 2. AgentChatView (`/chat`)
*   **功能**：客服 AI 问诊助手。
*   **技术细节**：通过调用后端 `/api/v1/agent` 大模型接口，对客服录入的用户故障申诉进行意图分类识别，当识别出故障符合售后标准时，界面会动态生成一个高亮引导卡片（例如提示“该用户疑似传感器脱落，请点击进入检测”）。

### 3. FaultQueryView (`/fault-query/:categoryKey`)
*   **功能**：特定故障类型的设备录入与 SN 检索工作台。
*   **特性**：
    *   支持录入单个设备 SN 并通过后端获取最新的佩戴天数、状态码等详细指标。
    *   支持粘贴多行文本解析并匹配唯一的 SN 候補。
    *   当录入单个 SN 时，系统会自动将客服引导至单设备流页面；录入多个 SN 时，会自动跳转到批量多设备流。

### 4. DetectFlowView (`/detect/:sn`)
*   **功能**：单设备售后诊断详情展示与判决面板。
*   **特性**：
    *   自动渲染从海外接口拉取或 Mock 生成的连续血糖曲线图表。
    *   显示当前设备规则判定结果。如果自动规则未能通过，界面将展示截图凭证上传模块，并显示 VLM 的识别判定。
    *   显示规范化的诊断文案模板，并提供“生成换新单”及“驳回售后申请”的操作按钮。

### 5. MultiDetectView (`/multi-detect/:batchId`)
*   **功能**：多设备批量诊断工作区。
*   **特性**：将当前批次（`batchId`）下的所有设备组织成检测队列，实时渲染后端异步扫描的进度和单个设备的诊断结论，支持客服一键批量归档。

### 6. ThresholdsView (`/thresholds`)
*   **功能**：判定阈值治理后台。
*   **特性**：展示并允许管理员修改数据准确性、脱落、异常等指标的阈值数值，支持版本号下发更新。

### 7. 核心布局组件 `AppShell.vue`
*   **功能**：系统主框架侧边栏与头部导航区。
*   **特性**：集成了当前活动的诊断会话计数器（Session Manager），能智能将同一批次的检测设备进行分组，只在头部工具栏显示分组后的活跃任务个数。

---

## ⚙️ 开发阶段 API 代理配置

前端与后端通过统一的 API 连接。在 `vite.config.ts` 中配置了代理规则，开发环境下，本地发送的所有 `/api/*` 请求都会被自动代理到本地运行的端口为 `8000` 的后端接口中：

```typescript
// vite.config.ts 代理配置段
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',  // 指向后端 Uvicorn 运行地址
      changeOrigin: true,
    },
  },
}
```

---

## 🚀 本地开发操作指南

### 1. 前置环境要求
确保本地机器已安装 Node.js (推荐 v20.x 或以上版本) 和 npm。

### 2. 初始化项目依赖
在 `si-overseas` 目录下运行安装命令：
```bash
npm install
```

### 3. 运行本地开发服务器
启动 Vite 开发服务器：
```bash
npm run dev
```
启动成功后，浏览器会自动打开或打印如下地址：
`http://localhost:5173/`

### 4. 代码质量与类型检查
在提交代码前，建议运行 TypeScript 静态检查以消除潜在隐患：
```bash
npm run typecheck
```

### 5. 运行单元测试
项目使用 Vitest 测试框架，以校验工具函数及 Legacy HTML 提取逻辑的正确性：
```bash
npm test
```

---

## 📦 打包与静态部署步骤

### 1. 执行静态资源打包
在 `si-overseas` 目录下执行构建：
```bash
npm run build
```
打包生成的可部署静态资源会被输出到 `si-overseas/dist/` 文件夹下。

### 2. Nginx 反向代理与重定向配置

由于使用的是基于单页面应用（SPA）的浏览器路由（`vue-router` 的 History 模式），为了防止直接刷新浏览器子路由页面时返回 404 错误，必须确保 Nginx 服务将所有的路由请求都 fallback 回退到 `index.html`。

以下是推荐的 Nginx 配置文件 `nginx.conf` 样例：
```nginx
server {
    listen       80;
    server_name  localhost;

    # 指向打包出来的 dist 静态资源目录
    root   /usr/share/nginx/html/dist;
    index  index.html index.htm;

    location / {
        # 尝试匹配请求文件，若没有则重定向回 index.html 让 vue-router 接管路由
        try_files $uri $uri/ /index.html;
    }

    # 开发及生产环境下，将后端 API 请求反向代理至真实的 FastAPI 后端
    location /api {
        proxy_pass http://backend-api-service:8000; # 对应后端实际的服务名或 IP
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
通过上述配置即可确保应用不管是本地直连，还是生产部署都能够正常处理页面流转和跨域请求。
