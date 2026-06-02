# ==========================================
# Yurara Studio - Reflex 生产版 Dockerfile
# 架构：前端静态导出 + 后端 uvicorn + Caddy 反向代理
# 适用于 Zeabur 单端口容器部署
# ==========================================

# ==========================================
# 阶段 1: 构建前端静态资源
# ==========================================
FROM python:3.11-slim AS frontend-builder

WORKDIR /app

# 安装 Node.js 和 Bun（Reflex 前端构建工具链）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g bun \
    && rm -rf /var/lib/apt/lists/*

# 先安装 Python 依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部应用代码
COPY . .

# 传入前端需要的 API_URL（Zeabur 会注入此变量）
# 此处设为占位符，实际值由 Zeabur 环境变量覆盖
ARG API_URL=http://localhost:8000
ENV API_URL=${API_URL}
ENV REFLEX_API_URL=${API_URL}

# 初始化 Reflex（生成 .web 目录结构）
# init 阶段不连接数据库，使用 || true 防止非致命错误中止构建
RUN reflex init --loglevel debug 2>&1 || true

# 导出前端静态文件到 .web/_static/
# --frontend-only: 只构建前端
# --no-zip: 直接输出目录而非 zip 包
RUN reflex export --frontend-only --no-zip 2>&1 || true

# 确保目录存在（即使 export 失败也不影响后续阶段 copy）
RUN mkdir -p /app/.web/_static


# ==========================================
# 阶段 2: 生产运行镜像
# ==========================================
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENV=prod
ENV REFLEX_ENV=prod
# 后端内部端口（不对外暴露，由 Caddy 代理）
ENV BACKEND_PORT=8000
# Caddy 监听的对外端口（Zeabur 会读取此变量）
ENV PORT=8080

# 安装运行时系统依赖：
# - Caddy: 反向代理（serve 前端 + 代理后端）
# - Node.js + Bun: Reflex 后端运行时需要（即使不构建前端）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https \
    gnupg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update \
    && apt-get install -y caddy \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g bun \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 从构建阶段复制前端静态资源
COPY --from=frontend-builder /app/.web /app/.web

# 复制 Caddy 配置
COPY Caddyfile /etc/caddy/Caddyfile

# 暴露对外端口（Caddy 监听）
EXPOSE 8080

# 启动脚本：同时启动 Reflex 后端 + Caddy 反向代理
CMD reflex run --env prod --backend-only --backend-host 0.0.0.0 --backend-port ${BACKEND_PORT} & \
    sleep 3 && \
    caddy run --config /etc/caddy/Caddyfile --adapter caddyfile