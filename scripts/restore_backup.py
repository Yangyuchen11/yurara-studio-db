import os
import sys
import io
import zipfile
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# 添加根目录到 path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from yurara_app.state.app_state import TABLES_MAP
from database import Base

def restore_database(zip_path: str, database_url: str = None):
    if not os.path.exists(zip_path):
        print(f"❌ 找不到备份文件: {zip_path}")
        sys.exit(1)
        
    db_url = database_url or os.getenv("DATABASE_URL", "")
    if not db_url:
        print("❌ 未提供 DATABASE_URL 且环境变量中不存在")
        sys.exit(1)

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://") and "+psycopg2" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    print(f"📦 准备从 {zip_path} 恢复数据...")
    print(f"🎯 目标数据库: {db_url.split('@')[-1] if '@' in db_url else db_url}")

    engine = create_engine(db_url, pool_pre_ping=True)

    with open(zip_path, "rb") as f:
        data = f.read()

    # 1. 结构重建
    print("🏗️ 正在重建数据库结构...")
    with engine.begin() as conn:
        if "postgres" in str(engine.url):
            try:
                conn.execute(text("SET session_replication_role = 'replica';"))
            except Exception:
                pass
        elif "sqlite" in str(engine.url):
            conn.execute(text("PRAGMA foreign_keys = OFF;"))

        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)

    # 2. 逐表导入数据（每张表独立提交事务，确保真实落盘）
    print("📥 正在导入数据...")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zip_files = {os.path.basename(name): name for name in zf.namelist() if not name.endswith('/')}
        print(f"📂 发现 {len(zip_files)} 个数据文件")
        inserted_total = 0
        for file_name, table_name, model_cls in TABLES_MAP:
            if file_name in zip_files:
                with zf.open(zip_files[file_name]) as zf_file:
                    df_import = pd.read_csv(zf_file, encoding='utf-8-sig')
                    if not df_import.empty:
                        if model_cls and hasattr(model_cls, "__table__"):
                            valid_cols = [c.name for c in model_cls.__table__.columns]
                            df_import = df_import[[col for col in df_import.columns if col in valid_cols]]
                        
                        with engine.begin() as conn:
                            if "postgres" in str(engine.url):
                                try:
                                    conn.execute(text("SET session_replication_role = 'replica';"))
                                except Exception:
                                    pass
                            df_import.to_sql(table_name, conn, if_exists='append', index=False)
                        
                        inserted_total += len(df_import)
                        print(f"  ✅ 导入 {table_name}: {len(df_import)} 行")
                    else:
                        print(f"  ℹ️ {table_name}: 0 行（跳过）")
            else:
                print(f"  ⚠️ 备份中无 {file_name}")

        if inserted_total == 0:
            raise ValueError("❌ 备份文件中未找到任何有效的表格数据！")

    # 3. 恢复约束与校正自增序列
    print("🔧 正在恢复约束并校正序列号...")
    if "postgres" in str(engine.url):
        with engine.connect() as conn:
            try:
                conn.execute(text("SET session_replication_role = 'origin';"))
                conn.commit()
            except Exception:
                pass

            for _, table_name, model_cls in TABLES_MAP:
                # 仅对拥有 id 列的表校正序列，跳过如 system_settings 等无 id 表
                if model_cls and hasattr(model_cls, "__table__") and "id" in model_cls.__table__.columns:
                    try:
                        conn.execute(text(f"""
                            DO $$
                            DECLARE
                                seq_name text;
                                max_id bigint;
                            BEGIN
                                seq_name := pg_get_serial_sequence('{table_name}', 'id');
                                IF seq_name IS NOT NULL THEN
                                    EXECUTE 'SELECT coalesce(max(id), 0) FROM {table_name}' INTO max_id;
                                    IF max_id > 0 THEN
                                        PERFORM setval(seq_name, max_id, true);
                                    END IF;
                                END IF;
                            END $$;
                        """))
                        conn.commit()
                    except Exception as e:
                        print(f"  ⚠️ 校正序列号跳过 {table_name}: {e}")
    elif "sqlite" in str(engine.url):
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = ON;"))

    print("\n🎉 全部数据导入成功并已持久化落盘！")

if __name__ == "__main__":
    target_zip = sys.argv[1] if len(sys.argv) > 1 else "backups/yurara_complete_backup.zip"
    target_url = sys.argv[2] if len(sys.argv) > 2 else None
    restore_database(target_zip, target_url)
