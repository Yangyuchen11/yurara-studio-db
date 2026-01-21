import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. 获取连接字符串
# 注意：如果是本地运行 Bot，st.secrets 可能无法加载，
# 你可能需要改为从 os.getenv("DATABASE_URL") 读取，并配合 python-dotenv
try:
    SQLALCHEMY_DATABASE_URL = st.secrets["database"]["DATABASE_URL"]
except:
    # 如果找不到 secrets (例如在本地运行脚本时)，尝试从环境变量读取
    import os
    from dotenv import load_dotenv
    load_dotenv()
    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "")

# 2. 修正协议头 (Supabase 兼容性处理)
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. 创建引擎
# 建议加上 pool_pre_ping=True 以防止断连
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()