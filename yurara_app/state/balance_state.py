# yurara_app/state/balance_state.py
"""
公司账面概览（资产负债表与资本）State 模块。
包含服务端数值格式化以确保客户端高性能展示。
"""
import reflex as rx
from pydantic import BaseModel
from ..state.app_state import AppState

class BalanceDisplayRow(BaseModel):
    item_name: str = ""
    cny_val: str = "-"
    jpy_val: str = "-"

class BalanceState(AppState):
    new_acc_name: str = ""
    new_acc_curr: str = "CNY"
    
    # 汇总数据
    cash_cny: float = 0.0
    cash_jpy: float = 0.0
    
    pure_asset_cny: float = 0.0
    pure_asset_jpy: float = 0.0
    
    total_asset_cny: float = 0.0
    total_asset_jpy: float = 0.0
    
    liability_cny: float = 0.0
    liability_jpy: float = 0.0
    
    equity_cny: float = 0.0
    equity_jpy: float = 0.0
    
    net_cny: float = 0.0
    net_jpy: float = 0.0
    
    # 明细列表数据
    assets_rows: list[BalanceDisplayRow] = []
    liabilities_rows: list[BalanceDisplayRow] = []
    equities_rows: list[BalanceDisplayRow] = []

    # ===================== 计算属性 =====================

    @rx.var
    def cash_jpy_cny(self) -> float:
        return self.cash_jpy * self.exchange_rate

    @rx.var
    def cash_total(self) -> float:
        return self.cash_cny + self.cash_jpy_cny

    @rx.var
    def pure_asset_jpy_cny(self) -> float:
        return self.pure_asset_jpy * self.exchange_rate

    @rx.var
    def pure_asset_total(self) -> float:
        return self.pure_asset_cny + self.pure_asset_jpy_cny

    @rx.var
    def total_asset_jpy_cny(self) -> float:
        return self.total_asset_jpy * self.exchange_rate

    @rx.var
    def total_asset_total(self) -> float:
        return self.total_asset_cny + self.total_asset_jpy_cny

    @rx.var
    def net_jpy_cny(self) -> float:
        return self.net_jpy * self.exchange_rate

    @rx.var
    def net_total(self) -> float:
        return self.net_cny + self.net_jpy_cny

    @rx.var
    def liability_jpy_cny(self) -> float:
        return self.liability_jpy * self.exchange_rate

    @rx.var
    def liability_total(self) -> float:
        return self.liability_cny + self.liability_jpy_cny

    @rx.var
    def equity_jpy_cny(self) -> float:
        return self.equity_jpy * self.exchange_rate

    @rx.var
    def equity_total(self) -> float:
        return self.equity_cny + self.equity_jpy_cny

    # ===================== 服务端格式化字符串 =====================

    @rx.var
    def cash_cny_str(self) -> str: return f"¥ {self.cash_cny:,.2f}"
    @rx.var
    def cash_jpy_str(self) -> str: return f"¥ {self.cash_jpy:,.0f}"
    @rx.var
    def cash_jpy_cny_str(self) -> str: return f"¥ {self.cash_jpy_cny:,.2f}"
    @rx.var
    def cash_total_str(self) -> str: return f"¥ {self.cash_total:,.2f}"

    @rx.var
    def pure_asset_cny_str(self) -> str: return f"¥ {self.pure_asset_cny:,.2f}"
    @rx.var
    def pure_asset_jpy_str(self) -> str: return f"¥ {self.pure_asset_jpy:,.0f}"
    @rx.var
    def pure_asset_jpy_cny_str(self) -> str: return f"¥ {self.pure_asset_jpy_cny:,.2f}"
    @rx.var
    def pure_asset_total_str(self) -> str: return f"¥ {self.pure_asset_total:,.2f}"

    @rx.var
    def total_asset_cny_str(self) -> str: return f"¥ {self.total_asset_cny:,.2f}"
    @rx.var
    def total_asset_jpy_str(self) -> str: return f"¥ {self.total_asset_jpy:,.0f}"
    @rx.var
    def total_asset_jpy_cny_str(self) -> str: return f"¥ {self.total_asset_jpy_cny:,.2f}"
    @rx.var
    def total_asset_total_str(self) -> str: return f"¥ {self.total_asset_total:,.2f}"

    @rx.var
    def net_cny_str(self) -> str: return f"¥ {self.net_cny:,.2f}"
    @rx.var
    def net_jpy_str(self) -> str: return f"¥ {self.net_jpy:,.0f}"
    @rx.var
    def net_jpy_cny_str(self) -> str: return f"¥ {self.net_jpy_cny:,.2f}"
    @rx.var
    def net_total_str(self) -> str: return f"¥ {self.net_total:,.2f}"

    @rx.var
    def liability_cny_str(self) -> str: return f"¥ {self.liability_cny:,.2f}"
    @rx.var
    def liability_jpy_str(self) -> str: return f"¥ {self.liability_jpy:,.0f}"
    @rx.var
    def liability_jpy_cny_str(self) -> str: return f"¥ {self.liability_jpy_cny:,.2f}"
    @rx.var
    def liability_total_str(self) -> str: return f"¥ {self.liability_total:,.2f}"

    @rx.var
    def equity_cny_str(self) -> str: return f"¥ {self.equity_cny:,.2f}"
    @rx.var
    def equity_jpy_str(self) -> str: return f"¥ {self.equity_jpy:,.0f}"
    @rx.var
    def equity_jpy_cny_str(self) -> str: return f"¥ {self.equity_jpy_cny:,.2f}"
    @rx.var
    def equity_total_str(self) -> str: return f"¥ {self.equity_total:,.2f}"

    # ===================== 事件处理器 =====================

    @rx.event
    def set_new_acc_name(self, name: str):
        self.new_acc_name = name
        
    @rx.event
    def set_new_acc_curr(self, curr: str):
        self.new_acc_curr = curr
        
    @rx.event
    def load_balance_data(self):
        db = self.get_db()
        try:
            from services.balance_service import BalanceService
            summary = BalanceService.get_financial_summary(db)
            
            # 基础项汇总
            cash = summary["cash"]
            self.cash_cny = cash["CNY"]
            self.cash_jpy = cash["JPY"]
            
            totals = summary["totals"]
            self.pure_asset_cny = totals["pure_asset"]["CNY"]
            self.pure_asset_jpy = totals["pure_asset"]["JPY"]
            
            self.total_asset_cny = totals["asset"]["CNY"]
            self.total_asset_jpy = totals["asset"]["JPY"]
            
            self.liability_cny = totals["liability"]["CNY"]
            self.liability_jpy = totals["liability"]["JPY"]
            
            self.equity_cny = totals["equity"]["CNY"]
            self.equity_jpy = totals["equity"]["JPY"]
            
            self.net_cny = totals["net"]["CNY"]
            self.net_jpy = totals["net"]["JPY"]
            
            # --- 1. 资产行列表构建 ---
            asset_data = []
            
            # 现金账户独立展现
            for cash_acc in summary["cash_items"]:
                if abs(cash_acc.amount) < 0.01:
                    continue
                asset_data.append(BalanceDisplayRow(
                    item_name=f"💵 {cash_acc.name}",
                    cny_val=f"{cash_acc.amount:,.2f}" if cash_acc.currency == "CNY" else "-",
                    jpy_val=f"{cash_acc.amount:,.0f}" if cash_acc.currency == "JPY" else "-"
                ))
            
            fixed = summary["fixed"]
            if fixed["CNY"] > 0 or fixed["JPY"] > 0:
                asset_data.append(BalanceDisplayRow(
                    item_name="固定资产(设备)",
                    cny_val=f"{fixed['CNY']:,.2f}" if fixed['CNY'] > 0 else "-",
                    jpy_val=f"{fixed['JPY']:,.0f}" if fixed['JPY'] > 0 else "-"
                ))
                
            cons = summary["consumable"]
            if cons["CNY"] > 0 or cons["JPY"] > 0:
                asset_data.append(BalanceDisplayRow(
                    item_name="其他资产",
                    cny_val=f"{cons['CNY']:,.2f}" if cons['CNY'] > 0 else "-",
                    jpy_val=f"{cons['JPY']:,.0f}" if cons['JPY'] > 0 else "-"
                ))
                
            for p_name, net_val in summary["wip"]["list"]:
                asset_data.append(BalanceDisplayRow(
                    item_name=f"📦 在制资产-{p_name}",
                    cny_val=f"{net_val:,.2f}",
                    jpy_val="-"
                ))
                
            manual_display = self._aggregate_display_rows(summary["manual_assets"])
            asset_data.extend(manual_display)
            self.assets_rows = asset_data
            
            # --- 2. 负债行列表构建 ---
            self.liabilities_rows = self._aggregate_display_rows(summary["liabilities"])
            
            # --- 3. 资本行列表构建 ---
            self.equities_rows = self._aggregate_display_rows(summary["equities"])
            
        finally:
            db.close()
            
    def _aggregate_display_rows(self, items_list) -> list[BalanceDisplayRow]:
        grouped = {}
        for item in items_list:
            if abs(item.amount) < 0.01:
                continue
            name = item.name
            if name not in grouped:
                grouped[name] = {"CNY": 0.0, "JPY": 0.0}
            if item.currency == "CNY":
                grouped[name]["CNY"] += item.amount
            elif item.currency == "JPY":
                grouped[name]["JPY"] += item.amount
                
        result = []
        for name, amts in grouped.items():
            result.append(BalanceDisplayRow(
                item_name=name,
                cny_val=f"{amts['CNY']:,.2f}" if abs(amts['CNY']) > 0 else "-",
                jpy_val=f"{amts['JPY']:,.0f}" if abs(amts['JPY']) > 0 else "-"
            ))
        return result
        
    @rx.event
    def create_cash_account(self):
        if not self.new_acc_name.strip():
            yield rx.toast("请输入账户名称", level="error")
            return
        db = self.get_db()
        try:
            from services.balance_service import BalanceService
            BalanceService.add_cash_account(db, self.new_acc_name.strip(), self.new_acc_curr)
            self.new_acc_name = ""
            yield rx.toast(f"账户开立成功！")
            yield BalanceState.load_balance_data()
        except Exception as e:
            yield rx.toast(f"账户开立失败: {e}", level="error")
        finally:
            db.close()
