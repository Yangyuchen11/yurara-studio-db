# ==========================================
# 阶段 1: 基础镜像与环境配置
# ==========================================
# 使用 Python 3.10 slim 版本，体积小，节省云服务器存储和内存
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
# 1. 防止 Python 生成 .pyc 字节码文件，减少镜像体积
ENV PYTHONDONTWRITEBYTECODE=1
# 2. 确保日志未缓冲，直接输出到控制台 (对 AWS CloudWatch/Logs 监控至关重要)
ENV PYTHONUNBUFFERED=1

# ==========================================
# 阶段 2: 安装系统依赖
# ==========================================
# 安装编译所需的库 (gcc, libpq-dev) 和用于健康检查的 curl
# 并在安装后立即清理 apt 缓存，减小镜像体积
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# 阶段 3: 安装 Python 依赖
# ==========================================
# 先只复制 requirements.txt，利用 Docker 缓存机制
# 只有当 requirements.txt 变动时，才会重新执行 pip install
COPY requirements.txt .

# 安装依赖，--no-cache-dir 避免保存 pip 缓存，节省空间
RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# 阶段 4: 复制代码与启动配置
# ==========================================
# 复制项目所有代码到镜像中
# 注意：建议配合 .dockerignore 文件排除不需要的文件
COPY . .

# 暴露 Streamlit 端口
EXPOSE 8501

# 添加健康检查 (Healthcheck)
# AWS 负载均衡器或 Docker Compose 可以通过此检查判断服务是否卡死
# 如果 8501 端口无法响应，容器会被标记为 unhealthy 并可能自动重启
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 默认启动命令
# 注意：在 docker-compose.yml 中，'bot' 服务会覆盖此命令
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]