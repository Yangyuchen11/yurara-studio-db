# ==========================================
# Yurara Studio - Reflex 版 Dockerfile
# 适用于 Zeabur 自托管 Docker 部署
# ==========================================

# 阶段 1: 构建前端（Node.js + Bun）
FROM node:20-slim AS frontend-builder

WORKDIR /app

# 安装 Bun（Reflex 使用 Bun 作为前端包管理器）
RUN npm install -g bun

# 复制依赖文件
COPY requirements.txt .
COPY rxconfig.py .

# 安装 Python（用于运行 reflex export）
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*
RUN pip3 install reflex --break-system-packages

# 复制完整代码
COPY . .

# 初始化并构建前端静态资源
RUN reflex init --loglevel debug || true
RUN reflex export --frontend-only --no-zip 2>/dev/null || true


# ==========================================
# 阶段 2: 生产镜像
# ==========================================
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Reflex 后端端口
ENV PORT=8080

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 复制前端构建产物（如果有）
COPY --from=frontend-builder /app/.web /app/.web 2>/dev/null || true

# 暴露端口
# 8080: Reflex 后端（API + WebSocket）
# 3000: Reflex 前端（开发模式）
EXPOSE 8080
EXPOSE 3000

# 启动命令：Reflex 生产模式（前后端合并）
# --backend-host 0.0.0.0 使容器可被外部访问
CMD ["reflex", "run", "--env", "prod", "--backend-host", "0.0.0.0", "--backend-port", "8080"]