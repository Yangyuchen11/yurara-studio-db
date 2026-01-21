import pandas as pd
import os
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# === 1. 导入新的模型结构 ===
# 确保你的 models.py 已经是更新后的版本（包含 ProductPrice）
from models import (
    Base, Product, ProductPrice, ProductColor,
    InventoryLog, FinanceRecord, CostItem,
    FixedAsset, FixedAssetLog, ConsumableItem, ConsumableLog,
    CompanyBalanceItem, PreShippingItem, SystemSetting
)

# === 2. 数据库连接设置 ===
# 尝试从 secrets 读取，如果失败则使用默认值（请根据实际情况调整）
try:
    # 这里的逻辑主要是为了获取连接字符串，与 app.py 保持一致
    db_url = st.secrets["database"]["DATABASE_URL"]
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
except FileNotFoundError:
    # 如果本地没有 secrets.toml，请手动在此处填入你的数据库连接串
    print("⚠️ 未找到 secrets.toml，尝试使用本地 SQLite...")
    db_url = "sqlite:///./yurara_studio.db"

print(f"🔗 连接数据库: {db_url}")
engine = create_engine(db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def clean_nan(val):
    """辅助函数：处理 pandas 读取的 NaN 值，转为 None 或 0"""
    if pd.isna(val):
        return None
    return val

def clean_float(val):
    """辅助函数：处理价格，NaN 转 0.0"""
    if pd.isna(val):
        return 0.0
    return float(val)

def migrate():
    session = SessionLocal()
    data_dir = "old_data"  # CSV 文件所在的文件夹

    if not os.path.exists(data_dir):
        print(f"❌ 错误：找不到 '{data_dir}' 文件夹。请创建该文件夹并将备份的 CSV 文件放入其中。")
        return

    print("♻️  正在重置数据库表结构 (Drop & Create)...")
    try:
        # ⚠️ 注意：这会清空当前数据库！确保你已经有 CSV 备份！
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        print("✅ 表结构已重建（包含 ProductPrice 表）。")
    except Exception as e:
        print(f"❌ 重置表结构失败: {e}")
        return

    # ==========================================
    # 1. 迁移 Products (最关键的拆分步骤)
    # ==========================================
    products_csv = os.path.join(data_dir, "products.csv")
    if os.path.exists(products_csv):
        print("📦 正在迁移 Products 及拆分价格...")
        df = pd.read_csv(products_csv)
        
        count = 0
        for _, row in df.iterrows():
            # A. 创建产品基础信息 (保留 ID 以维持关联)
            new_prod = Product(
                id=row['id'],
                name=row['name'],
                total_quantity=clean_float(row.get('total_quantity', 0)),
                marketable_quantity=clean_float(row.get('marketable_quantity', 0)),
                target_platform=clean_nan(row.get('target_platform')),
                # 注意：这里不再传入 price_weidian 等字段
            )
            session.add(new_prod)
            
            # B. 拆分价格到 ProductPrice 表
            # 定义映射关系: (旧列名, 平台代码, 币种)
            price_map = [
                ('price_weidian', 'weidian', 'CNY'),
                ('price_booth', 'booth', 'JPY'),
                ('price_offline_jp', 'offline_jp', 'JPY'),
                ('price_offline_cn', 'offline_cn', 'CNY'),
                ('price_instagram', 'instagram', 'JPY'),
                ('price_other_jpy', 'other_jpy', 'JPY'),
                ('price_other', 'other', 'CNY')
            ]
            
            for col, platform, curr in price_map:
                if col in row and clean_float(row[col]) > 0:
                    new_price = ProductPrice(
                        product_id=row['id'],
                        platform=platform,
                        currency=curr,
                        price=clean_float(row[col])
                    )
                    session.add(new_price)
            count += 1
        print(f"   -> 完成 {count} 个产品的迁移。")
    else:
        print("⚠️ 未找到 products.csv，跳过产品迁移。")

    # ==========================================
    # 2. 迁移其他普通表 (直接映射)
    # ==========================================
    
    # 定义通用迁移配置
    # (CSV文件名, 模型类, 需要日期的字段列表)
    simple_tables = [
        ("product_colors.csv", ProductColor, []),
        ("finance_records.csv", FinanceRecord, ['date']),
        ("cost_items.csv", CostItem, []),
        ("inventory_logs.csv", InventoryLog, ['date']),
        ("fixed_assets.csv", FixedAsset, ['purchase_date']),
        ("fixed_asset_logs.csv", FixedAssetLog, ['date']),
        ("consumables.csv", ConsumableItem, ['purchase_date']),
        ("consumable_logs.csv", ConsumableLog, ['date']),
        ("company_balance.csv", CompanyBalanceItem, []),
        ("pre_shipping_items.csv", PreShippingItem, ['created_date']),
        ("system_settings.csv", SystemSetting, [])
    ]

    for csv_name, ModelClass, date_cols in simple_tables:
        file_path = os.path.join(data_dir, csv_name)
        if os.path.exists(file_path):
            print(f"📄 正在迁移 {csv_name} ...")
            try:
                df = pd.read_csv(file_path)
                # 过滤掉 CSV 中有但模型里没有的列 (防止报错)
                valid_cols = [c.name for c in ModelClass.__table__.columns]
                
                # 处理空数据框
                if df.empty:
                    print(f"   -> {csv_name} 为空，跳过。")
                    continue

                records = []
                for _, row in df.iterrows():
                    row_data = {}
                    for col in valid_cols:
                        if col in row:
                            val = row[col]
                            # 特殊处理日期
                            if col in date_cols and isinstance(val, str):
                                try:
                                    val = datetime.strptime(val, '%Y-%m-%d').date()
                                except:
                                    val = None
                            # 特殊处理空值
                            if pd.isna(val):
                                val = None
                            row_data[col] = val
                    
                    records.append(ModelClass(**row_data))
                
                if records:
                    session.add_all(records)
                    print(f"   -> 导入 {len(records)} 条记录。")
            except Exception as e:
                print(f"❌ 导入 {csv_name} 失败: {e}")
        else:
            print(f"⚪ 跳过 {csv_name} (文件不存在)")

    # ==========================================
    # 3. 提交事务
    # ==========================================
    print("💾 正在提交更改...")
    try:
        # 对于 Postgres，需要重置自增 ID 序列
        if "postgres" in str(engine.url):
            print("🔧 正在重置 Postgres ID 序列...")
            # 获取所有表名
            table_names = [
                "products", "product_prices", "product_colors", "cost_items", 
                "inventory_logs", "finance_records", "company_balance_items",
                "fixed_assets_detail", "fixed_asset_logs", "consumable_items",
                "consumable_logs", "pre_shipping_items"
            ]
            for tbl in table_names:
                try:
                    # 将序列值设为当前最大 ID + 1
                    sql = text(f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), coalesce(max(id),0) + 1, false) FROM {tbl};")
                    session.execute(sql)
                except Exception as ex:
                    # 有些表可能没有 id 或序列，忽略错误
                    pass
        
        session.commit()
        print("🎉🎉🎉 数据迁移成功！所有数据已导入新数据库结构。")
    except Exception as e:
        session.rollback()
        print(f"❌ 提交失败，已回滚: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    # 二次确认
    print("⚠️  警告：此操作将【清空】当前配置的数据库，并从 'old_data' 文件夹恢复数据。")
    print("⚠️  请确保你已经更新了 models.py 并且备份了数据。")
    confirm = input("确认要执行吗？(输入 yes 继续): ")
    if confirm.lower() == "yes":
        migrate()
    else:
        print("已取消。")