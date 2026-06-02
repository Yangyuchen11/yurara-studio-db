FROM python:3.11-slim

LABEL "language"="python"
LABEL "framework"="reflex"

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 安装 Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# 复制源代码
COPY . .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 初始化 Reflex 应用
RUN python -m reflex init --loglevel debug || true

# 构建前端
RUN python -m reflex export --frontend-only --no-zip 2>/dev/null || true

# 设置环境变量
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV REFLEX_ENV_MODE=prod

EXPOSE 8080

# 启动 Reflex 应用
CMD ["python", "-m", "reflex", "run", "--env", "prod"]