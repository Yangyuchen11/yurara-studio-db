# yurara_app/state/app_state.py
"""
全局应用 State。
管理：测试模式开关、全局汇率、数据库 Session 工厂。
"""
import os
import reflex as rx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


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
    def set_exchange_rate(self, rate: float):
        """更新全局汇率并写入数据库。"""
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
