#!/usr/bin/env bash
set -euo pipefail

# 获取项目根目录 (即 backend 的上一级目录)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="${ROOT_DIR}/backend"

# 优先读取已存在的环境变量或 .env，无则使用默认值
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/cgm_agent}"
export AUTO_CREATE_TABLES="${AUTO_CREATE_TABLES:-true}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-dev-secret-change-me}"

# 1. 如果在 Poetry 环境中且有 poetry.lock/pyproject.toml，优先使用 Poetry 启动
if command -v poetry >/dev/null 2>&1 && [ -f "backend/pyproject.toml" ]; then
  echo ">>> 检测到 Poetry 环境，使用 poetry run 启动服务..."
  cd backend
  exec poetry run uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
fi

# 2. 如果已经手动激活了虚拟环境 (如 conda, virtualenv)，直接用当前 python 启动
if [ -n "${VIRTUAL_ENV:-}" ] || [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
  echo ">>> 检测到已激活的虚拟环境 (${VIRTUAL_ENV:-$CONDA_DEFAULT_ENV})，直接启动..."
  exec python -m uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}" --app-dir backend --reload
fi

# 3. 检查是否有本地常见的 .venv 目录
if [ -f "backend/.venv/bin/python" ]; then
  echo ">>> 使用 backend/.venv 虚拟环境启动..."
  exec backend/.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}" --app-dir backend --reload
elif [ -f ".venv/bin/python" ]; then
  echo ">>> 使用根目录 .venv 虚拟环境启动..."
  exec .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}" --app-dir backend --reload
fi

# 4. 兜底方案：使用系统全局 python (需要确保已安装 uvicorn 等依赖)
echo ">>> 未检测到虚拟环境，尝试使用系统 python 启动..."
exec python -m uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}" --app-dir backend --reload

