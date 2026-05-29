import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

# 从环境变量读取数据库连接字符串
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "")

# 修正协议头 (Supabase / PostgreSQL 兼容性处理)
if not SQLALCHEMY_DATABASE_URL:
    # 编译期/测试无环境变量时，回落为内存 SQLite 以防止 rfc1738 崩溃
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
else:
    if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# 创建引擎（pool_pre_ping=True 防止断连）
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()