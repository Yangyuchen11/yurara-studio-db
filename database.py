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
            if "is_budget" not in columns:
                try:
                    conn.execute(text("ALTER TABLE cost_items ADD COLUMN is_budget BOOLEAN DEFAULT FALSE;"))
                    conn.execute(text("UPDATE cost_items SET is_budget = TRUE WHERE supplier = '预算设定';"))
                    print("[Migration] Added column is_budget to cost_items and set defaults")
                except Exception as e:
                    print(f"[Migration] Failed to add is_budget: {e}")

    if "finance_records" in inspector.get_table_names():
        fr_columns = [c["name"] for c in inspector.get_columns("finance_records")]
        if "related_cost_id" not in fr_columns:
            with engine.begin() as conn:
                try:
                    conn.execute(text("ALTER TABLE finance_records ADD COLUMN related_cost_id INTEGER;"))
                    print("[Migration] Added column related_cost_id to finance_records")
                except Exception as e:
                    print(f"[Migration] Failed to add related_cost_id: {e}")

    # 自愈修复：历史商品成本待付款未标记 is_budget 或单价为 0 的项
    try:
        from models import CostItem, FinanceRecord, CompanyBalanceItem
        from sqlalchemy.orm import Session
        with Session(engine) as session:
            pending_frs = session.query(FinanceRecord).filter(
                FinanceRecord.category == "商品成本待付款",
                FinanceRecord.related_item_id.isnot(None)
            ).all()
            healed_count = 0
            for fr in pending_frs:
                ci = session.query(CostItem).filter(CostItem.id == fr.related_item_id).first()
                if ci and (not ci.is_budget or not ci.unit_price or ci.unit_price <= 0.001):
                    liab = session.query(CompanyBalanceItem).filter(
                        CompanyBalanceItem.finance_record_id == fr.id
                    ).first()
                    ci.is_budget = True
                    if not ci.quantity or ci.quantity <= 0.001:
                        ci.quantity = 1.0
                    if (not ci.unit_price or ci.unit_price <= 0.001) and liab and liab.amount:
                        ci.unit_price = float(liab.amount) / ci.quantity
                    session.add(ci)
                    healed_count += 1
            if healed_count > 0:
                session.commit()
                print(f"[Migration] Self-healed {healed_count} pending cost items to budget with amounts.")
    except Exception as e:
        print(f"[Migration] Self-healing pending cost items error: {e}")

    # 自愈修复：清除由于 Pandas CSV 导入推断为浮点数而错误追加的 '.0' 后缀
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            for tbl, col in [
                ("sales_orders", "final_order_no"),
                ("sales_orders", "order_no"),
                ("cost_items", "order_no"),
                ("presale_order_bindings", "final_order_no"),
                ("presale_order_bindings", "deposit_order_no"),
            ]:
                try:
                    conn.execute(text(f"""
                        UPDATE {tbl} 
                        SET {col} = substr({col}, 1, length({col}) - 2) 
                        WHERE {col} LIKE '%.0';
                    """))
                except Exception:
                    pass
            print("[Migration] Checked and cleaned any .0 suffixes in order numbers.")
    except Exception as e:
        print(f"[Migration] Clean .0 suffixes error: {e}")
    # 自愈修复：确保基础流动资金现金账户存在（如日元临时现金账户）
    try:
        from models import CompanyBalanceItem
        from sqlalchemy.orm import Session
        with Session(engine) as session:
            jpy_cash_acc = session.query(CompanyBalanceItem).filter(
                CompanyBalanceItem.category == "asset",
                CompanyBalanceItem.name == "流动资金-日元临时现金账户"
            ).first()
            if not jpy_cash_acc:
                session.add(CompanyBalanceItem(
                    name="流动资金-日元临时现金账户",
                    category="asset",
                    amount=0.0,
                    currency="JPY",
                    asset_type="现金"
                ))
                session.commit()
                print("[Migration] Added missing '流动资金-日元临时现金账户' to company_balance_items.")
    except Exception as e:
        print(f"[Migration] Check/add JPY temporary cash account error: {e}")

    # 寄售管理全面升级迁移：补充 consignment_items 新列并自动将历史店铺名称建档
    try:
        from models import ConsignmentShop, ConsignmentItem, InventoryLog
        from sqlalchemy.orm import Session

        # 先确保新表存在（兼容单独调用 migrate_db 的场景）
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        if "consignment_items" in inspector.get_table_names():
            cons_cols = [c["name"] for c in inspector.get_columns("consignment_items")]
            alter_stmts = [
                ("shop_id", "INTEGER"),
                ("warehouse_id", "INTEGER"),
                ("part_name", "VARCHAR"),
                ("sold_qty", "INTEGER DEFAULT 0"),
                ("returned_qty", "INTEGER DEFAULT 0"),
                ("unit_price", "FLOAT DEFAULT 0.0"),
                ("currency", "VARCHAR DEFAULT 'CNY'"),
                ("status", "VARCHAR DEFAULT '寄售中'"),
            ]
            with engine.begin() as conn:
                for col_name, col_def in alter_stmts:
                    if col_name not in cons_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE consignment_items ADD COLUMN {col_name} {col_def};"))
                            print(f"[Migration] Added column {col_name} to consignment_items")
                        except Exception as col_err:
                            print(f"[Migration] Failed to add {col_name} to consignment_items: {col_err}")

        with Session(engine) as session:
            items = session.query(ConsignmentItem).all()
            shop_cache = {s.name: s for s in session.query(ConsignmentShop).all()}
            updated_cnt = 0
            for ci in items:
                changed = False
                s_name = (ci.shop_name or "").strip() or "默认寄售店"
                if ci.shop_name != s_name:
                    ci.shop_name = s_name
                    changed = True
                if not ci.shop_id:
                    shop_obj = shop_cache.get(s_name)
                    if not shop_obj:
                        shop_obj = ConsignmentShop(name=s_name, currency=ci.currency or "CNY")
                        session.add(shop_obj)
                        session.flush()
                        shop_cache[s_name] = shop_obj
                    ci.shop_id = shop_obj.id
                    changed = True
                if not ci.warehouse_id and ci.inventory_log_id:
                    inv_log = session.query(InventoryLog).filter(InventoryLog.id == ci.inventory_log_id).first()
                    if inv_log and inv_log.warehouse_id:
                        ci.warehouse_id = inv_log.warehouse_id
                        changed = True
                    if inv_log and inv_log.part_name and not ci.part_name:
                        ci.part_name = inv_log.part_name
                        changed = True
                if ci.sold_qty is None:
                    ci.sold_qty = max(0, (ci.quantity or 0) - (ci.remaining_qty or 0))
                    changed = True
                if ci.returned_qty is None:
                    ci.returned_qty = 0
                    changed = True
                # 对历史手动调整过 remaining_qty 的记录同步 sold_qty（仅在 sold+returned=0 且 remaining < quantity 时补齐）
                if ci.sold_qty == 0 and ci.returned_qty == 0 and (ci.remaining_qty or 0) < (ci.quantity or 0):
                    ci.sold_qty = max(0, (ci.quantity or 0) - (ci.remaining_qty or 0))
                    changed = True
                expected_status = (
                    "已结清" if (ci.remaining_qty or 0) <= 0
                    else ("部分结算" if ((ci.sold_qty or 0) > 0 or (ci.returned_qty or 0) > 0) else "寄售中")
                )
                if not ci.status or ci.status != expected_status:
                    ci.status = expected_status
                    changed = True
                if not ci.currency:
                    ci.currency = "CNY"
                    changed = True
                if changed:
                    updated_cnt += 1
            if updated_cnt > 0:
                session.commit()
                print(f"[Migration] Backfilled {updated_cnt} consignment items and shops.")
    except Exception as e:
        print(f"[Migration] Consignment upgrade migration error: {e}")
