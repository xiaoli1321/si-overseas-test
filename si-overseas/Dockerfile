# ==============================================================================
# SIBIONICS 海外 CGM AI 前端 — pnpm 构建 + Vite Preview 运行
# ==============================================================================
# 构建阶段
FROM node:20-alpine AS builder
RUN npm install -g pnpm
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# 运行阶段 — 只安装运行时依赖（--prod 跳过 devDeps）
FROM node:20-alpine AS runner
RUN npm install -g pnpm
WORKDIR /app
COPY package.json pnpm-lock.yaml vite.config.ts ./
RUN pnpm install --frozen-lockfile --prod
COPY --from=builder /app/dist ./dist
EXPOSE 4173
CMD ["pnpm", "preview", "--configLoader", "bundle"]
