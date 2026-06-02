#!/bin/sh
set -e

echo "=========================================="
echo "  Yurara Studio - Production Startup"
echo "=========================================="
echo "ENV:          ${ENV}"
echo "PORT:         ${PORT}"
echo "BACKEND_PORT: ${BACKEND_PORT}"
echo "API_URL:      ${API_URL}"
echo "DATABASE_URL: ${DATABASE_URL:+[set]}"

# 检查 .web 静态目录是否存在
if [ -d "/app/.web/_static" ] && [ "$(ls -A /app/.web/_static 2>/dev/null)" ]; then
    echo "[OK] Frontend static files found."
else
    echo "[WARN] .web/_static is empty or missing - frontend may not load correctly."
fi

# 启动 Reflex 后端（后台运行）
echo "Starting Reflex backend on port ${BACKEND_PORT:-8000}..."
reflex run --env prod --backend-only --backend-host 0.0.0.0 --backend-port "${BACKEND_PORT:-8000}" &
REFLEX_PID=$!
echo "Reflex backend PID: $REFLEX_PID"

# 等待后端启动
echo "Waiting 5s for backend to initialize..."
sleep 5

# 检查后端进程是否还在运行
if kill -0 "$REFLEX_PID" 2>/dev/null; then
    echo "[OK] Reflex backend is running."
else
    echo "[ERROR] Reflex backend crashed! Check logs above."
    exit 1
fi

# 启动 Caddy（前台运行，作为容器主进程）
echo "Starting Caddy on port ${PORT:-8080}..."
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
