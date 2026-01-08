import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 优先尝试从 secrets 获取云端数据库地址，没有则使用本地 SQLite
try:
    # 在 secrets.toml 中配置 [connections.postgresql] dialect="postgresql" ...
    # 或者直接存一个字符串:
    # [database]
    # url = "postgresql://..."
    SQLALCHEMY_DATABASE_URL = st.secrets["database"]["url"]
    # Postgres 需要这个参数
    connect_args = {} 
except:
    # 本地回退方案
    SQLALCHEMY_DATABASE_URL = "sqlite:///./database.db"
    connect_args = {"check_same_thread": False}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()