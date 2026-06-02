#!/bin/sh

echo "=========================================="
echo "  Yurara Studio - Production Startup"
echo "=========================================="
echo "ENV:          ${ENV}"
echo "PORT:         ${PORT}"
echo "API_URL:      ${API_URL}"
echo "DATABASE_URL: ${DATABASE_URL:+[set]}"

# 检查 .web 目录是否存在（前端预构建产物）
if [ -d "/app/.web" ]; then
    echo "[OK] .web directory found."
else
    echo "[WARN] .web directory missing - frontend may rebuild at startup."
fi

echo "Starting Reflex in production mode on port ${PORT:-8080}..."

# 直接运行 reflex（前后端统一在同一端口）
exec reflex run \
    --env prod \
    --backend-host 0.0.0.0 \
    --backend-port "${PORT:-8080}"
