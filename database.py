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

def migrate_db(engine):
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "cost_items" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("cost_items")]
        with engine.begin() as conn:
            if "actual_qty" not in columns:
                try:
                    conn.execute(text("ALTER TABLE cost_items ADD COLUMN actual_qty FLOAT DEFAULT 0.0;"))
                    print("[Migration] Added column actual_qty to cost_items")
                except Exception as e:
                    print(f"[Migration] Failed to add actual_qty: {e}")
            if "actual_unit_price" not in columns:
                try:
                    conn.execute(text("ALTER TABLE cost_items ADD COLUMN actual_unit_price FLOAT DEFAULT 0.0;"))
                    print("[Migration] Added column actual_unit_price to cost_items")
                except Exception as e:
                    print(f"[Migration] Failed to add actual_unit_price: {e}")

    if "finance_records" in inspector.get_table_names():
        fr_columns = [c["name"] for c in inspector.get_columns("finance_records")]
        if "related_cost_id" not in fr_columns:
            with engine.begin() as conn:
                try:
                    conn.execute(text("ALTER TABLE finance_records ADD COLUMN related_cost_id INTEGER;"))
                    print("[Migration] Added column related_cost_id to finance_records")
                except Exception as e:
                    print(f"[Migration] Failed to add related_cost_id: {e}")