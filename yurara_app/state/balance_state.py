# yurara_app/state/balance_state.py
"""
公司账面概览（资产负债表与资本）State 模块。
已升级为多货币动态列架构：
  - 资产/负债/资本表格动态按实际出现的货币渲染列
  - 所有折算均使用 rates_map，支持任意新货币
"""
import reflex as rx
from pydantic import BaseModel
from ..state.app_state import AppState
from constants import to_cny


class BalanceDisplayRow(BaseModel):
    """账面明细行，支持动态任意货币列。"""
    item_name: str = ""
    # amounts_by_currency: { "CNY": "1,234.56", "JPY": "5,000", "USD": "100.00" }
    # 在 Reflex State 中用 dict[str, str] 存储（前端 JSON 序列化友好）
    amounts_by_currency: dict[str, str] = {}
    # 折合 CNY 合计（用于前端显示总列）
    total_cny_str: str = "-"


class BalanceSummaryItem(BaseModel):
    """单货币金额汇总项，用于顶部 KPI 卡片。"""
    currency: str = ""
    amount: float = 0.0
    amount_str: str = ""
    amount_cny_equiv: float = 0.0
    amount_cny_str: str = ""


class BalanceState(AppState):
    new_acc_name: str = ""
    new_acc_curr: str = "CNY"

    # --- 顶部 KPI 数据（各货币原值 + 折合 CNY 合计）---
    # 每项含 cash / pure_asset / total_asset / liability / equity / net 六个大类
    # 结构：dict[ 分类key, dict[货币代码, float] ]
    # 为了兼容 Reflex State 序列化，存储格式化字符串列表
    summary_currencies: list[str] = []  # 当前出现的所有货币，不含 CNY（CNY 始终第一列）

    cash_total_cny: float = 0.0
    pure_asset_total_cny: float = 0.0
    total_asset_total_cny: float = 0.0
    liability_total_cny: float = 0.0
    equity_total_cny: float = 0.0
    net_total_cny: float = 0.0

    # 各货币的分项原值（以 list[BalanceSummaryItem] 存储，前端按货币 key 索引）
    cash_by_currency: list[BalanceSummaryItem] = []
    pure_asset_by_currency: list[BalanceSummaryItem] = []
    total_asset_by_currency: list[BalanceSummaryItem] = []
    liability_by_currency: list[BalanceSummaryItem] = []
    equity_by_currency: list[BalanceSummaryItem] = []
    net_by_currency: list[BalanceSummaryItem] = []

    # 明细列表数据（动态列）
    assets_rows: list[BalanceDisplayRow] = []
    liabilities_rows: list[BalanceDisplayRow] = []
    equities_rows: list[BalanceDisplayRow] = []

    # ===================== 向后兼容计算属性 =====================

    @rx.var
    def cash_cny(self) -> float:
        for item in self.cash_by_currency:
            if item.currency == "CNY":
                return item.amount
        return 0.0

    @rx.var
    def cash_jpy(self) -> float:
        for item in self.cash_by_currency:
            if item.currency == "JPY":
                return item.amount
        return 0.0

    @rx.var
    def cash_total(self) -> float:
        return self.cash_total_cny

    @rx.var
    def total_asset_total(self) -> float:
        return self.total_asset_total_cny

    @rx.var
    def net_total(self) -> float:
        return self.net_total_cny

    @rx.var
    def liability_total(self) -> float:
        return self.liability_total_cny

    @rx.var
    def equity_total(self) -> float:
        return self.equity_total_cny

    # --- 格式化字符串（向后兼容旧 UI 调用）---
    @rx.var
    def cash_total_str(self) -> str: return f"¥ {self.cash_total_cny:,.2f}"
    @rx.var
    def total_asset_total_str(self) -> str: return f"¥ {self.total_asset_total_cny:,.2f}"
    @rx.var
    def net_total_str(self) -> str: return f"¥ {self.net_total_cny:,.2f}"
    @rx.var
    def liability_total_str(self) -> str: return f"¥ {self.liability_total_cny:,.2f}"
    @rx.var
    def equity_total_str(self) -> str: return f"¥ {self.equity_total_cny:,.2f}"
    @rx.var
    def pure_asset_total_str(self) -> str: return f"¥ {self.pure_asset_total_cny:,.2f}"

    # --- 账面表格的货币列头（含 CNY 和所有外币）---
    @rx.var
    def display_currencies(self) -> list[str]:
        """账面表格显示的所有货币列（CNY 在首位，其余按字母序）。"""
        result = ["CNY"]
        for c in sorted(self.summary_currencies):
            if c != "CNY":
                result.append(c)
        return result

    # ===================== 事件处理器 =====================

    @rx.event
    def set_new_acc_name(self, name: str):
        self.new_acc_name = name

    @rx.event
    def set_new_acc_curr(self, curr: str):
        self.new_acc_curr = curr

    @rx.event
    async def load_balance_data(self):
        if not await self.is_authenticated_user():
            return
        db = self.get_db()
        try:
            from services.balance_service import BalanceService
            summary = BalanceService.get_financial_summary(db)
            rates = dict(self.rates_map)

            # --- 收集所有出现过的货币 ---
            all_currencies = set()
            for group_key in ["cash", "fixed", "consumable"]:
                for curr in summary[group_key].keys():
                    all_currencies.add(curr)
            for item in (summary["manual_assets"] + summary["liabilities"] + summary["equities"]):
                if item.currency:
                    all_currencies.add(item.currency)
            all_currencies.discard("CNY")
            self.summary_currencies = sorted(list(all_currencies))
            all_curr_list = ["CNY"] + sorted(list(all_currencies))

            # --- 辅助：将 dict[currency, float] 转换为 BalanceSummaryItem 列表 ---
            def make_summary_items(amounts_dict: dict) -> list[BalanceSummaryItem]:
                items = []
                for curr in all_curr_list:
                    amt = amounts_dict.get(curr, 0.0)
                    if curr == "CNY":
                        fmt = f"¥ {amt:,.2f}"
                    else:
                        fmt = f"{amt:,.2f} {curr}"
                    items.append(BalanceSummaryItem(
                        currency=curr,
                        amount=amt,
                        amount_str=fmt,
                        amount_cny_equiv=to_cny(amt, curr, rates),
                        amount_cny_str=f"¥ {to_cny(amt, curr, rates):,.2f}"
                    ))
                return items

            # --- 汇总数据 ---
            cash_amts = summary["cash"]
            fixed_amts = summary["fixed"]
            cons_amts = summary["consumable"]
            wip_cny = summary["wip"]["total_cny"]
            manual_assets = summary["manual_assets"]
            liabilities = summary["liabilities"]
            equities = summary["equities"]

            # 构建 pure_asset / total_asset / etc. 各货币原值
            def sum_by_currency(items):
                result = {}
                for item in items:
                    curr = item.currency or "CNY"
                    result[curr] = result.get(curr, 0.0) + item.amount
                return result

            manual_amts = sum_by_currency(manual_assets)
            liab_amts = sum_by_currency(liabilities)
            eq_amts = sum_by_currency(equities)

            # pure_asset = fixed + cons + manual + wip(CNY only)
            pure_asset_amts = {}
            for curr in all_curr_list:
                pure_asset_amts[curr] = (
                    fixed_amts.get(curr, 0.0) +
                    cons_amts.get(curr, 0.0) +
                    manual_amts.get(curr, 0.0)
                )
            pure_asset_amts["CNY"] = pure_asset_amts.get("CNY", 0.0) + wip_cny

            # total_asset = cash + pure_asset
            total_asset_amts = {}
            for curr in all_curr_list:
                total_asset_amts[curr] = cash_amts.get(curr, 0.0) + pure_asset_amts.get(curr, 0.0)

            # net = total_asset - liability
            net_amts = {}
            for curr in all_curr_list:
                net_amts[curr] = total_asset_amts.get(curr, 0.0) - liab_amts.get(curr, 0.0)

            self.cash_by_currency = make_summary_items(cash_amts)
            self.pure_asset_by_currency = make_summary_items(pure_asset_amts)
            self.total_asset_by_currency = make_summary_items(total_asset_amts)
            self.liability_by_currency = make_summary_items(liab_amts)
            self.equity_by_currency = make_summary_items(eq_amts)
            self.net_by_currency = make_summary_items(net_amts)

            # --- 折合 CNY 合计 ---
            self.cash_total_cny = sum(to_cny(v, c, rates) for c, v in cash_amts.items())
            self.pure_asset_total_cny = sum(to_cny(v, c, rates) for c, v in pure_asset_amts.items())
            self.total_asset_total_cny = sum(to_cny(v, c, rates) for c, v in total_asset_amts.items())
            self.liability_total_cny = sum(to_cny(v, c, rates) for c, v in liab_amts.items())
            self.equity_total_cny = sum(to_cny(v, c, rates) for c, v in eq_amts.items())
            self.net_total_cny = sum(to_cny(v, c, rates) for c, v in net_amts.items())

            # --- 1. 资产行列表构建（动态列）---
            asset_data = []

            # 现金账户独立展现
            for cash_acc in summary["cash_items"]:
                if abs(cash_acc.amount) < 0.01:
                    continue
                amts = {curr: "-" for curr in all_curr_list}
                curr = cash_acc.currency or "CNY"
                if curr == "CNY":
                    amts[curr] = f"{cash_acc.amount:,.2f}"
                else:
                    amts[curr] = f"{cash_acc.amount:,.2f}"
                total_cny = to_cny(cash_acc.amount, curr, rates)
                asset_data.append(BalanceDisplayRow(
                    item_name=f"💵 {cash_acc.name}",
                    amounts_by_currency=amts,
                    total_cny_str=f"¥ {total_cny:,.2f}"
                ))

            if any(v > 0 for v in fixed_amts.values()):
                amts = {curr: "-" for curr in all_curr_list}
                for curr, val in fixed_amts.items():
                    if val > 0:
                        amts[curr] = f"{val:,.2f}"
                total_cny = sum(to_cny(v, c, rates) for c, v in fixed_amts.items())
                asset_data.append(BalanceDisplayRow(
                    item_name="固定资产(设备)",
                    amounts_by_currency=amts,
                    total_cny_str=f"¥ {total_cny:,.2f}"
                ))

            if any(v > 0 for v in cons_amts.values()):
                amts = {curr: "-" for curr in all_curr_list}
                for curr, val in cons_amts.items():
                    if val > 0:
                        amts[curr] = f"{val:,.2f}"
                total_cny = sum(to_cny(v, c, rates) for c, v in cons_amts.items())
                asset_data.append(BalanceDisplayRow(
                    item_name="其他资产",
                    amounts_by_currency=amts,
                    total_cny_str=f"¥ {total_cny:,.2f}"
                ))

            for p_name, net_val in summary["wip"]["list"]:
                amts = {curr: "-" for curr in all_curr_list}
                amts["CNY"] = f"{net_val:,.2f}"
                asset_data.append(BalanceDisplayRow(
                    item_name=f"📦 在制资产-{p_name}",
                    amounts_by_currency=amts,
                    total_cny_str=f"¥ {net_val:,.2f}"
                ))

            manual_display = self._aggregate_display_rows(manual_assets, all_curr_list, rates)
            asset_data.extend(manual_display)
            self.assets_rows = asset_data

            # --- 2. 负债行列表构建 ---
            self.liabilities_rows = self._aggregate_display_rows(liabilities, all_curr_list, rates)

            # --- 3. 资本行列表构建 ---
            self.equities_rows = self._aggregate_display_rows(equities, all_curr_list, rates)

        finally:
            db.close()

    def _aggregate_display_rows(self, items_list, all_curr_list: list, rates: dict) -> list[BalanceDisplayRow]:
        """将账面条目按名称分组，动态构建各货币列的显示行。"""
        grouped = {}
        for item in items_list:
            if abs(item.amount) < 0.01:
                continue
            name = item.name
            curr = item.currency or "CNY"
            if name not in grouped:
                grouped[name] = {c: 0.0 for c in all_curr_list}
            grouped[name][curr] = grouped[name].get(curr, 0.0) + item.amount

        result = []
        for name, amts in grouped.items():
            amts_str = {}
            total_cny = 0.0
            for curr in all_curr_list:
                val = amts.get(curr, 0.0)
                if abs(val) > 0.001:
                    amts_str[curr] = f"{val:,.2f}"
                    total_cny += to_cny(val, curr, rates)
                else:
                    amts_str[curr] = "-"
            result.append(BalanceDisplayRow(
                item_name=name,
                amounts_by_currency=amts_str,
                total_cny_str=f"¥ {total_cny:,.2f}"
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
