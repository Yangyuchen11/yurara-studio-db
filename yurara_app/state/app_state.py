# yurara_app/state/app_state.py
"""
全局应用 State。
管理：测试模式开关、全局汇率、数据库 Session 工厂。
"""
import os
import reflex as rx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import (
    Warehouse, Product, ProductColor, ProductPart, ProductPrice,
    FinanceRecord, CostItem, InventoryLog, FixedAsset, FixedAssetLog,
    ConsumableItem, ConsumableLog, CompanyBalanceItem,
    SalesOrder, SalesOrderItem, OrderRefund,
    OfflineTemplate, OfflineTemplateItem
)

TABLES_MAP = [
    ("warehouses.csv", "warehouses", Warehouse), 
    ("products.csv", "products", Product),
    ("product_colors.csv", "product_colors", ProductColor),
    ("product_parts.csv", "product_parts", ProductPart), 
    ("product_prices.csv", "product_prices", ProductPrice),
    ("finance_records.csv", "finance_records", FinanceRecord),
    ("cost_items.csv", "cost_items", CostItem),
    ("inventory_logs.csv", "inventory_logs", InventoryLog),
    ("fixed_assets.csv", "fixed_assets_detail", FixedAsset),
    ("fixed_asset_logs.csv", "fixed_asset_logs", FixedAssetLog),
    ("consumables.csv", "consumable_items", ConsumableItem),
    ("consumable_logs.csv", "consumable_logs", ConsumableLog),
    ("company_balance.csv", "company_balance_items", CompanyBalanceItem),
    ("sales_orders.csv", "sales_orders", SalesOrder),
    ("sales_order_items.csv", "sales_order_items", SalesOrderItem),
    ("order_refunds.csv", "order_refunds", OrderRefund),
    ("offline_templates.csv", "offline_templates", OfflineTemplate),
    ("offline_template_items.csv", "offline_template_items", OfflineTemplateItem),
]


def _build_engine(is_test: bool):
    """根据 is_test 参数构建 SQLAlchemy Engine。"""
    if is_test:
        return create_engine(
            "sqlite:///yurara_test_env.db",
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
    else:
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url:
            db_url = "sqlite:///:memory:"
        else:
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return create_engine(db_url, pool_pre_ping=True)


# 模块级缓存引擎，避免重复创建
_engines: dict = {}


def get_cached_engine(is_test: bool):
    """缓存并返回 Engine，防止连接池耗尽。"""
    key = "test" if is_test else "prod"
    if key not in _engines:
        _engines[key] = _build_engine(is_test)
    return _engines[key]


class AppState(rx.State):
    """全局应用状态。"""

    # --- 测试模式开关 ---
    test_mode: bool = False

    # --- 全局汇率（100 JPY 兑 CNY） ---
    exchange_rate_100: float = 4.8

    # --- Toast 消息队列 ---
    toast_message: str = ""
    toast_icon: str = ""

    # --- 危险操作：清空数据口令确认 ---
    delete_confirm_code: str = ""

    # ===================== 属性计算 =====================

    @rx.var
    def exchange_rate(self) -> float:
        """返回实际汇率（1 JPY → CNY）。"""
        return self.exchange_rate_100 / 100.0

    @rx.var
    def env_label(self) -> str:
        return "🧪 测试环境" if self.test_mode else "🟢 正式环境"

    # ===================== 数据库会话工厂 =====================

    def get_db(self):
        """
        在 event handler 中调用，获取一个数据库 Session。
        调用方负责在 finally 块中关闭 session。
        """
        engine = get_cached_engine(self.test_mode)
        Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return Session()

    # ===================== 事件处理器 =====================

    @rx.event
    def set_exchange_rate(self, rate_val: str):
        """更新全局汇率并写入数据库。"""
        try:
            rate = float(rate_val)
        except ValueError:
            return
        if rate < 0.01:
            rate = 0.01
        self.exchange_rate_100 = rate

        # 持久化到数据库
        db = self.get_db()
        try:
            from models import SystemSetting
            setting = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate").first()
            if setting:
                setting.value = str(rate)
            else:
                setting = SystemSetting(key="exchange_rate", value=str(rate))
                db.add(setting)
            db.commit()
            self.toast_message = f"汇率已更新: {rate}"
            self.toast_icon = "💾"
        except Exception as e:
            db.rollback()
        finally:
            db.close()

    @rx.event
    def load_exchange_rate(self):
        """从数据库加载当前汇率。"""
        db = self.get_db()
        try:
            from models import SystemSetting
            setting = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate").first()
            if setting:
                self.exchange_rate_100 = float(setting.value)
        except Exception:
            pass
        finally:
            db.close()

    @rx.event
    def toggle_test_mode(self, value: bool):
        """切换测试/正式环境，切换时复制真实数据到沙盒。"""
        if value == self.test_mode:
            return

        if value:
            # 进入测试环境：复制真实数据到 SQLite
            import pandas as pd
            from database import Base
            from models import (
                Warehouse, Product, ProductColor, ProductPart, ProductPrice,
                FinanceRecord, CostItem, InventoryLog, FixedAsset, FixedAssetLog,
                ConsumableItem, ConsumableLog, CompanyBalanceItem,
                SalesOrder, SalesOrderItem, OrderRefund,
                OfflineTemplate, OfflineTemplateItem,
            )
            TABLES = [
                ("warehouses", Warehouse), ("products", Product),
                ("product_colors", ProductColor), ("product_parts", ProductPart),
                ("product_prices", ProductPrice), ("finance_records", FinanceRecord),
                ("cost_items", CostItem), ("inventory_logs", InventoryLog),
                ("fixed_assets_detail", FixedAsset), ("fixed_asset_logs", FixedAssetLog),
                ("consumable_items", ConsumableItem), ("consumable_logs", ConsumableLog),
                ("company_balance_items", CompanyBalanceItem), ("sales_orders", SalesOrder),
                ("sales_order_items", SalesOrderItem), ("order_refunds", OrderRefund),
                ("offline_templates", OfflineTemplate), ("offline_template_items", OfflineTemplateItem),
            ]
            real_engine = get_cached_engine(False)
            test_engine = get_cached_engine(True)

            # 重建沙盒
            Base.metadata.drop_all(bind=test_engine)
            Base.metadata.create_all(bind=test_engine)

            real_db = sessionmaker(bind=real_engine)()
            try:
                for table_name, model_cls in TABLES:
                    try:
                        df = pd.read_sql(real_db.query(model_cls).statement, real_db.bind)
                        if not df.empty:
                            df.to_sql(table_name, test_engine, if_exists="append", index=False)
                    except Exception:
                        pass
            finally:
                real_db.close()

        self.test_mode = value

    @rx.event
    def clear_toast(self):
        self.toast_message = ""
        self.toast_icon = ""

    @rx.event
    def download_backup_zip(self):
        """触发客户端从后端自定义 API 路由下载全量备份 ZIP。"""
        url = f"{rx.config.get().api_url}/backup?test_mode={str(self.test_mode).lower()}"
        return rx.download(url)

    @rx.event
    async def handle_backup_restore(self, files: list[rx.UploadFile]):
        """处理上传的备份 ZIP 并事务化恢复整个数据库表结构。"""
        if not files:
            yield rx.toast("请先选择备份 ZIP 文件！", level="warning")
            return
            
        file = files[0]
        data = await file.read()
        
        engine = get_cached_engine(self.test_mode)
        
        from sqlalchemy import text
        import zipfile
        import io
        import pandas as pd
        from database import Base
        
        try:
            with engine.begin() as conn:
                # 临时关闭外键约束校验
                if "postgres" in str(engine.url):
                    conn.execute(text("SET session_replication_role = 'replica';"))
                elif "sqlite" in str(engine.url):
                    conn.execute(text("PRAGMA foreign_keys = OFF;"))
                
                # 干净重构所有表结构并重置自增 ID
                Base.metadata.drop_all(bind=conn)
                Base.metadata.create_all(bind=conn)
                
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for file_name, table_name, _ in TABLES_MAP:
                        if file_name in zf.namelist():
                            with zf.open(file_name) as f:
                                df_import = pd.read_csv(f, encoding='utf-8-sig')
                                if not df_import.empty:
                                    df_import.to_sql(table_name, conn, if_exists='append', index=False)
                
                # 恢复外键约束并自增校正序列
                if "postgres" in str(engine.url):
                    conn.execute(text("SET session_replication_role = 'origin';"))
                    for _, table_name, _ in TABLES_MAP:
                        try:
                            conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), coalesce(max(id),0) + 1, false) FROM {table_name};"))
                        except Exception:
                            pass
                elif "sqlite" in str(engine.url):
                    conn.execute(text("PRAGMA foreign_keys = ON;"))
                    
            yield rx.toast("✅ 数据全量导入恢复成功！")
            yield rx.redirect(self.router.page.path)
            
        except Exception as e:
            yield rx.toast(f"❌ 备份导入失败: {e}", level="error")

    @rx.event
    def set_delete_confirm_code(self, val: str):
        self.delete_confirm_code = val

    @rx.event
    def clear_environment_data(self):
        """事务性级联删除当前激活环境下的所有业务记录。"""
        if self.delete_confirm_code != "DELETE":
            return rx.toast("请输入 DELETE 以确认！", level="warning")
            
        db = self.get_db()
        try:
            # 严格按照从属级联顺序删除
            db.query(ProductPart).delete()
            db.query(ProductPrice).delete()
            db.query(ProductColor).delete()
            
            db.query(CostItem).delete()
            db.query(FixedAsset).delete()
            db.query(ConsumableItem).delete()
            db.query(SalesOrderItem).delete()
            db.query(OrderRefund).delete()
            
            db.query(InventoryLog).delete()
            db.query(FixedAssetLog).delete()
            db.query(ConsumableLog).delete()
            db.query(CompanyBalanceItem).delete()
            
            db.query(Product).delete()
            db.query(FinanceRecord).delete()
            db.query(SalesOrder).delete()
            db.query(Warehouse).delete()
            
            db.query(OfflineTemplateItem).delete()
            db.query(OfflineTemplate).delete()
            
            db.commit()
            self.delete_confirm_code = ""
            
            yield rx.toast("🧹 数据已清空！表结构及系统设置已保留。")
            yield rx.redirect(self.router.page.path)
            
        except Exception as e:
            db.rollback()
            yield rx.toast(f"清空数据失败: {e}", level="error")
        finally:
            db.close()
