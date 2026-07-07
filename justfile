# 安装依赖
install:
    cd ./si-overseas/ && pnpm install

# 开发模式运行
dev:
    concurrently --names "backend,frontend" --prefix-colors "yellow,green" \
        "cd ./backend/ && PYTHONPATH=src uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload" \
        "cd ./si-overseas/ && pnpm run dev"

# 格式化代码
format:
    cd ./backend/ && ruff format src
