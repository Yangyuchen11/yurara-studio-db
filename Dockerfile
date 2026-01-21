# 使用 Python 3.10 作为基础镜像 (根据你的 pycache 版本判断)
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 Python 生成 pyc 文件，并让日志实时输出
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖 (编译 psycopg2 可能需要)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目所有代码到镜像中
COPY . .

# 暴露 Streamlit 的默认端口
EXPOSE 8501

# 默认启动命令 (会被 docker-compose 覆盖)
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]