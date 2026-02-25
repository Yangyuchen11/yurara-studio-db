# ==========================================
# 阶段 1: 基础镜像与环境配置
# ==========================================
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ==========================================
# 阶段 2: 安装系统依赖
# ==========================================
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# 阶段 3: 安装 Python 依赖
# ==========================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# 阶段 4: 复制代码与启动配置
# ==========================================
COPY . .

# 暴露 Streamlit 端口 (改成 8080 迎合 Zeabur)
EXPOSE 8080

# 默认启动命令 (改成 8080 迎合 Zeabur)
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]