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

    # --- 全局汇率字典（key=货币代码, value=1单位该货币对CNY的比值）---
    # 例如：{"JPY": 0.048, "USD": 7.25}
    rates_map: dict[str, float] = {"JPY": 0.048}

    # --- 汇率加载状态 ---
    rates_fetching: bool = False

    # --- Toast 消息队列 ---
    toast_message: str = ""
    toast_icon: str = ""

    # --- 危险操作：清空数据口令确认 ---
    delete_confirm_code: str = ""

    # --- 导航栏折叠状态 ---
    sidebar_collapsed: bool = False

    # --- 新增货币对话框输入字段 ---
    new_currency_code: str = ""
    new_currency_rate: str = ""



    # ===================== 属性计算 =====================

    @rx.var
    def exchange_rate(self) -> float:
        """向后兼容：返回 JPY→CNY 的实际汇率（1 JPY）。"""
        return self.rates_map.get("JPY", 0.048)

    @rx.var
    def exchange_rate_100(self) -> float:
        """向后兼容：返回 100 JPY → CNY 的汇率值（用于 UI 显示）。"""
        return self.rates_map.get("JPY", 0.048) * 100.0

    @rx.var
    def sorted_rates(self) -> list[dict[str, str]]:
        """用于 UI 渲染 of 已配置汇率列表（排除 CNY 本身）。"""
        result = []
        for code in sorted(self.rates_map.keys()):
            rate = self.rates_map[code]
            rate_100 = rate * 100
            reverse_rate = 1.0 / rate if rate > 0 else 0.0
            result.append({
                "currency": code,
                "rate_str": f"{rate_100:.4f}",  # 以"100单位外币=X CNY"显示
                "reverse_rate_str": f"{reverse_rate:.4f}",  # 以"1 CNY = X 外币"显示
            })
        return result

    @rx.var
    def all_currencies(self) -> list[str]:
        """所有可用货币代号列表（包含 CNY 及所有已登记的汇率货币）。"""
        return ["CNY"] + sorted(list(self.rates_map.keys()))

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


    @rx.event
    def set_currency_rate(self, currency: str, rate_per_100: str):
        """更新指定货币的汇率（以"100单位外币=X CNY"为输入单位）并写入数据库。"""
        currency = currency.strip().upper()
        if not currency or currency == "CNY":
            return
        try:
            rate_100 = float(rate_per_100)
        except (ValueError, TypeError):
            return
        if rate_100 < 0.0001:
            rate_100 = 0.0001

        new_rate = rate_100 / 100.0
        new_map = dict(self.rates_map)
        new_map[currency] = new_rate
        self.rates_map = new_map

        db = self.get_db()
        try:
            from models import SystemSetting
            key = f"rate_CNY_per_{currency}_100"
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if setting:
                setting.value = str(rate_100)
            else:
                setting = SystemSetting(key=key, value=str(rate_100),
                                        description=f"100 {currency} → CNY 汇率")
                db.add(setting)
            # 同步写旧格式（向后兼容）
            if currency == "JPY":
                old = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate").first()
                if old:
                    old.value = str(rate_100)
                else:
                    db.add(SystemSetting(key="exchange_rate", value=str(rate_100)))
            db.commit()
            self.toast_message = f"✅ 汇率已更新: 100 {currency} = {rate_100:.4f} CNY"
            self.toast_icon = "💾"
        except Exception as e:
            db.rollback()
            self.toast_message = f"❌ 汇率保存失败: {e}"
            self.toast_icon = "⚠️"
        finally:
            db.close()

    @rx.event
    def add_new_currency_from_dialog(self):
        """通过看板对话框新增货币登记，调用 set_currency_rate 并清空输入状态。"""
        code = self.new_currency_code.strip().upper()
        rate = self.new_currency_rate.strip()
        if not code:
            self.toast_message = "⚠️ 请填写货币代号"
            self.toast_icon = "⚠️"
            return
        if not rate:
            self.toast_message = "⚠️ 请填写汇率"
            self.toast_icon = "⚠️"
            return
        self.set_currency_rate(code, rate)
        self.new_currency_code = ""
        self.new_currency_rate = ""

    @rx.event
    def set_new_currency_code(self, val: str):
        self.new_currency_code = val

    @rx.event
    def set_new_currency_rate(self, val: str):
        self.new_currency_rate = val

    @rx.event
    def remove_currency_rate(self, currency: str):

        """移除一个非 JPY 货币的汇率配置（JPY 是核心货币，不可移除）。"""
        if currency in ("CNY", "JPY"):
            return
        new_map = {k: v for k, v in self.rates_map.items() if k != currency}
        self.rates_map = new_map
        db = self.get_db()
        try:
            from models import SystemSetting
            key = f"rate_CNY_per_{currency}_100"
            db.query(SystemSetting).filter(SystemSetting.key == key).delete()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @rx.event
    async def fetch_live_rates(self):
        """从 Google Finance 抓取所有已配置货币的实时汇率并更新。"""
        if self.rates_fetching:
            return
        self.rates_fetching = True
        try:
            import httpx
            import re
            currencies_to_fetch = [c for c in self.rates_map.keys() if c != "CNY"]
            if not currencies_to_fetch:
                self.toast_message = "⚠️ 无需获取汇率（仅有 CNY）"
                self.toast_icon = "⚠️"
                return

            updated = {}
            async with httpx.AsyncClient(timeout=10.0) as client:
                for currency in currencies_to_fetch:
                    try:
                        url = f"https://www.google.com/finance/quote/{currency}-CNY"
                        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                        resp = await client.get(url, headers=headers, follow_redirects=True)
                        if resp.status_code == 200:
                            # 匹配 Google Finance 页面中的汇率数字
                            match = re.search(rf'([\d\.]+)\s*,\s*"\s*{currency}\s*/\s*CNY\s*"', resp.text)
                            if not match:
                                match = re.search(r'data-last-price="([\d\.]+)"', resp.text)
                            if not match:
                                match = re.search(r'class="YMlKec fxKbKc">([\d\.]+)<', resp.text)
                            if not match:
                                match = re.search(r'"[\d\.]+" data-currency-code', resp.text)
                            if match:
                                live_rate = float(match.group(1))
                                updated[currency] = live_rate
                    except Exception:
                        pass

            if updated:
                new_map = dict(self.rates_map)
                new_map.update(updated)
                self.rates_map = new_map
                # 批量写入数据库
                db = self.get_db()
                try:
                    from models import SystemSetting
                    for currency, rate in updated.items():
                        rate_100 = rate * 100.0
                        key = f"rate_CNY_per_{currency}_100"
                        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                        if setting:
                            setting.value = str(rate_100)
                        else:
                            setting = SystemSetting(key=key, value=str(rate_100),
                                                    description=f"100 {currency} → CNY 实时汇率")
                            db.add(setting)
                        if currency == "JPY":
                            old = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate").first()
                            if old:
                                old.value = str(rate_100)
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()

                names = ", ".join(f"{c}={v:.6f}" for c, v in updated.items())
                self.toast_message = f"🌐 实时汇率已更新: {names}"
                self.toast_icon = "✅"
            else:
                self.toast_message = "⚠️ 未能获取到实时汇率，请检查网络连接"
                self.toast_icon = "⚠️"
        except Exception as e:
            self.toast_message = f"❌ 获取实时汇率失败: {e}"
            self.toast_icon = "❌"
        finally:
            self.rates_fetching = False

    @rx.event
    def load_all_rates(self):
        """从数据库加载所有货币汇率（同时兼容旧的 exchange_rate key）。"""
        db = self.get_db()
        try:
            from models import SystemSetting
            new_map = {}
            # 读取所有新格式汇率
            settings = db.query(SystemSetting).filter(
                SystemSetting.key.like("rate_CNY_per_%")
            ).all()
            for s in settings:
                # key 格式: rate_CNY_per_JPY_100
                parts = s.key.split("_")
                if len(parts) >= 5:
                    currency_code = parts[3]  # e.g. "JPY"
                    try:
                        rate_100 = float(s.value)
                        new_map[currency_code] = rate_100 / 100.0
                    except ValueError:
                        pass
            # 兼容旧格式（如果新格式没有 JPY，则从旧 key 读取）
            if "JPY" not in new_map:
                old = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate").first()
                if old:
                    try:
                        new_map["JPY"] = float(old.value) / 100.0
                    except ValueError:
                        new_map["JPY"] = 0.048
                else:
                    new_map["JPY"] = 0.048
            if new_map:
                self.rates_map = new_map
        except Exception:
            pass
        finally:
            db.close()

    # 向后兼容旧接口
    @rx.event
    def load_exchange_rate(self):
        """向后兼容旧接口，内部调用 load_all_rates。"""
        return AppState.load_all_rates()

    @rx.event
    def set_exchange_rate(self, rate_val: str):
        """向后兼容旧接口，等价于设置 JPY 汇率。"""
        return AppState.set_currency_rate("JPY", rate_val)


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
        """在 State 内直接生成全量备份 ZIP，通过 rx.download(data=...) 返回给客户端。
        
        使用 data= 而非 url= 以避免 Reflex 前端开发代理层破坏二进制数据。
        """
        import io
        import zipfile
        import pandas as pd
        from datetime import datetime

        engine = get_cached_engine(self.test_mode)
        env_suffix = "test" if self.test_mode else "prod"
        current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        filename = f"yurara-db-backup_{env_suffix}_{current_time}.zip"

        zip_buffer = io.BytesIO()
        try:
            with engine.connect() as conn:
                with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for file_name, table_name, _ in TABLES_MAP:
                        try:
                            df = pd.read_sql_table(table_name, conn)
                            zf.writestr(file_name, df.to_csv(index=False).encode("utf-8-sig"))
                        except Exception as e_table:
                            print(f"[Backup] Failed to export {table_name}: {e_table}")
            return rx.download(data=zip_buffer.getvalue(), filename=filename)
        except Exception as e:
            self.toast_message = f"❌ 备份生成失败: {e}"
            self.toast_icon = "❌"

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

    @rx.event
    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
