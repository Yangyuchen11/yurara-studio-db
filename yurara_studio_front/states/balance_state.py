# yurara_studio_front/states/balance_state.py
import reflex as rx
from database import SessionLocal
from services.balance_service import BalanceService
from yurara_studio_front.states.base_state import BaseState

class BalanceState(BaseState):
    """处理公司账面概览的数据状态"""

    @rx.var
    def exchange_rate_val(self) -> float:
        return self.exchange_rate

    # 如果要在 UI 里计算总额，在 State 里定义计算 Var
    def get_total_cny(self, cny_val, jpy_val):
        return cny_val + (jpy_val * self.exchange_rate)

    @rx.var
    def total_jpy_as_cny(self) -> float:
        """专门用于前端显示的 JPY 转 CNY 计算"""
        return self.cash_jpy * self.exchange_rate

    @rx.var
    def total_jpy_as_cny_for_assets(self) -> float:
        return self.pure_asset_jpy * self.exchange_rate
    
    # 顶部四大模块的汇总数据
    cash_cny: float = 0.0
    cash_jpy: float = 0.0
    pure_asset_cny: float = 0.0
    pure_asset_jpy: float = 0.0
    total_asset_cny: float = 0.0
    total_asset_jpy: float = 0.0
    total_liab_cny: float = 0.0
    total_liab_jpy: float = 0.0
    net_cny: float = 0.0
    net_jpy: float = 0.0
    
    # 表格数据：Reflex 的 data_table 需要 List[List] 或 List[Dict] 格式
    liabilities_data: list[list[str]] = []
    equities_data: list[list[str]] = []

    def load_data(self):
        """页面加载时，从数据库获取数据并赋值给 State"""
        # 注意：在 Reflex 的事件中，务必使用 with 打开和关闭数据库会话
        with SessionLocal() as db:
            summary = BalanceService.get_financial_summary(db)
            
            # 1. 提取汇总数据
            self.cash_cny = summary["cash"]["CNY"]
            self.cash_jpy = summary["cash"]["JPY"]
            
            self.pure_asset_cny = summary["totals"]["pure_asset"]["CNY"]
            self.pure_asset_jpy = summary["totals"]["pure_asset"]["JPY"]
            
            self.total_asset_cny = summary["totals"]["asset"]["CNY"]
            self.total_asset_jpy = summary["totals"]["asset"]["JPY"]
            
            self.total_liab_cny = summary["totals"]["liability"]["CNY"]
            self.total_liab_jpy = summary["totals"]["liability"]["JPY"]
            
            self.net_cny = summary["totals"]["net"]["CNY"]
            self.net_jpy = summary["totals"]["net"]["JPY"]
            
            # 2. 格式化负债表格数据 (过滤掉金额为0的项)
            self.liabilities_data = [
                [
                    i.name, 
                    f"{i.amount:,.2f}" if i.currency == "CNY" else "-", 
                    f"{i.amount:,.0f}" if i.currency == "JPY" else "-"
                ]
                for i in summary["liabilities"] if abs(i.amount) >= 0.01
            ]
            
            # 3. 格式化资本/权益表格数据
            self.equities_data = [
                [
                    i.name, 
                    f"{i.amount:,.2f}" if i.currency == "CNY" else "-", 
                    f"{i.amount:,.0f}" if i.currency == "JPY" else "-"
                ]
                for i in summary["equities"] if abs(i.amount) >= 0.01
            ]