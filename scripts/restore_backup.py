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

    with engine.begin() as conn:
        print("🔄 正在配置外键约束...")
        if "postgres" in str(engine.url):
            conn.execute(text("SET session_replication_role = 'replica';"))
        elif "sqlite" in str(engine.url):
            conn.execute(text("PRAGMA foreign_keys = OFF;"))

        print("🏗️ 正在重建数据库结构...")
        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)

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
                            df_import.to_sql(table_name, conn, if_exists='append', index=False)
                            inserted_total += len(df_import)
                            print(f"  ✅ 导入 {table_name}: {len(df_import)} 行")
                        else:
                            print(f"  ℹ️ {table_name}: 0 行（跳过）")
                else:
                    print(f"  ⚠️ 备份中无 {file_name}")

            if inserted_total == 0:
                raise ValueError("❌ 备份文件中未找到任何有效的表格数据！")

        print("🔧 正在校正序列号...")
        if "postgres" in str(engine.url):
            conn.execute(text("SET session_replication_role = 'origin';"))
            for _, table_name, _ in TABLES_MAP:
                try:
                    conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), coalesce(max(id),0) + 1, false) FROM {table_name};"))
                except Exception:
                    pass
        elif "sqlite" in str(engine.url):
            conn.execute(text("PRAGMA foreign_keys = ON;"))

    print("\n🎉 全部数据导入成功！")

if __name__ == "__main__":
    target_zip = sys.argv[1] if len(sys.argv) > 1 else "backups/yurara_complete_backup.zip"
    target_url = sys.argv[2] if len(sys.argv) > 2 else None
    restore_database(target_zip, target_url)
