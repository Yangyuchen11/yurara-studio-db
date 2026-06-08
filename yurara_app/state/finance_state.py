# yurara_app/state/finance_state.py
"""
财务流水录入 State 模块。
包含强类型下拉选项模型以适配 rx.select.root / rx.select.item 动态编译渲染。
"""
from datetime import date
import reflex as rx
from pydantic import BaseModel
from ..state.app_state import AppState
from constants import PRODUCT_COST_CATEGORIES, Currency

class FinanceRecordItem(BaseModel):
    id: int = 0
    date: str = ""
    currency: str = ""
    type: str = ""
    amount: float = 0.0
    category: str = ""
    desc: str = ""
    url: str = ""
    cny_bal: float = 0.0
    jpy_bal: float = 0.0

class TempBatchItem(BaseModel):
    key: str = ""
    name: str = ""
    amount: float = 0.0
    qty: float = 1.0
    desc: str = ""
    url: str = ""

# ===================== 下拉菜单强类型选项模型 =====================

class CashAccountOption(BaseModel):
    id: str = ""
    label: str = ""
    currency: str = ""

class DebtOption(BaseModel):
    id: str = ""
    label: str = ""
    amount: float = 0.0
    currency: str = ""

class AssetOption(BaseModel):
    id: str = ""
    label: str = ""

class ProductOption(BaseModel):
    id: str = ""
    label: str = ""

class BudgetOption(BaseModel):
    id: str = ""
    label: str = ""


class FinanceState(AppState):
    records: list[FinanceRecordItem] = []
    total_records: int = 0
    page: int = 1
    total_pages: int = 1
    cur_cny: float = 0.0
    cur_jpy: float = 0.0
    is_loading: bool = False
    
    # === 表单共用控制 ===
    active_tab: str = "list"  # list / add / edit / delete
    rec_type: str = "支出"    # 支出 / 收入 / 货币兑换 / 债务 / 资金移动
    form_ver: int = 0
    
    # === 通用单项收支表单 ===
    f_date: str = date.today().strftime("%Y-%m-%d")
    f_category: str = "其他"
    f_currency: str = "CNY"
    f_amount: float = 0.0
    f_shop: str = ""
    f_desc: str = ""
    f_url: str = ""
    f_account_id: str = ""
    
    # === 货币兑换专属 ===
    ex_source_curr: str = "CNY"
    ex_target_curr: str = "JPY"
    ex_amount_out: float = 0.0
    ex_amount_in: float = 0.0
    ex_source_acc_id: str = ""
    ex_target_acc_id: str = ""
    ex_desc: str = ""
    
    # === 债务管理专属 ===
    debt_op: str = "➕ 新增债务"   # ➕ 新增债务 / 💸 偿还债务
    debt_name: str = ""
    debt_dest: str = "存入流动资金 (拿到现金)"  # 存入流动资金 / 新增资产项
    debt_rel_content: str = ""
    debt_amount: float = 0.0
    debt_curr: str = "CNY"
    debt_target_acc_id: str = ""
    debt_source: str = ""
    debt_remark: str = ""
    # 偿还债务
    debt_repay_type: str = "💸 资金还款"  # 💸 资金还款 / 🔄 资产抵消
    debt_selected_id: str = ""
    debt_repay_amount: float = 0.0
    debt_repay_source_acc_id: str = ""
    debt_repay_remark: str = ""
    debt_repay_offset_asset_id: str = ""
    
    # === 资金移动专属 ===
    move_from_asset_id: str = ""
    move_to_asset_id: str = ""
    move_amount: float = 0.0
    move_desc: str = ""
    
    # === 批量商品成本专属 ===
    batch_product_id: str = ""
    batch_cost_cat: str = "大货材料费"
    batch_asset_cat: str = "包装材"
    batch_selected_budget_id: str = ""  # 0 / 空 表示不匹配预算
    batch_shipping_fee: float = 0.0
    
    # 批量录入临时单条输入
    temp_name: str = ""
    temp_amount: float = 0.0
    temp_qty: float = 1.0
    temp_desc: str = ""
    temp_url: str = ""
    batch_items: list[TempBatchItem] = []
    
    # === 编辑/删除面板专属 ===
    edit_selected_id: str = ""
    edit_date: str = ""
    edit_type: str = "支出"
    edit_acc_id: str = ""
    edit_amount: float = 0.0
    edit_category: str = ""
    edit_desc: str = ""
    edit_url: str = ""
    
    delete_selected_id: str = ""
    is_selected_delete_budget_related: bool = False
    delete_include_budget: bool = False
    
    # === 下拉菜单缓存资源 ===
    cash_accounts: list[CashAccountOption] = []
    unsettled_debts: list[DebtOption] = []
    offset_assets: list[AssetOption] = []
    products_list: list[ProductOption] = []
    budgets_list: list[BudgetOption] = []

    # ===================== 计算属性 =====================

    @rx.var
    def jpy_to_cny(self) -> float:
        return self.cur_jpy * self.exchange_rate

    @rx.var
    def total_balance(self) -> float:
        return self.cur_cny + self.jpy_to_cny

    @rx.var
    def is_non_cash(self) -> bool:
        return self.f_category in {"现有资产增加", "新资产增加", "现有资产减少", "其他资产增加"}

    @rx.var
    def batch_items_subtotal(self) -> float:
        return sum(item.amount for item in self.batch_items)

    @rx.var
    def batch_total_with_shipping(self) -> float:
        return self.batch_items_subtotal + self.batch_shipping_fee

    # ===================== 服务端格式化字符串 =====================

    @rx.var
    def cur_cny_str(self) -> str: return f"¥ {self.cur_cny:,.2f}"
    @rx.var
    def cur_jpy_str(self) -> str: return f"¥ {self.cur_jpy:,.0f}"
    @rx.var
    def jpy_to_cny_str(self) -> str: return f"¥ {self.jpy_to_cny:,.2f}"
    @rx.var
    def total_balance_str(self) -> str: return f"¥ {self.total_balance:,.2f}"
    
    @rx.var
    def batch_items_subtotal_str(self) -> str: return f"{self.batch_items_subtotal:,.2f}"
    @rx.var
    def batch_total_with_shipping_str(self) -> str: return f"{self.batch_total_with_shipping:,.2f}"

    # ===================== 事件处理器 =====================

    @rx.event
    def set_rec_type(self, val: str):
        self.rec_type = val
        self.form_ver += 1
        self.reset_subform_variables()

    @rx.event
    def set_f_date(self, val: str): self.f_date = val
    @rx.event
    def set_f_category(self, val: str):
        self.f_category = val
        self.load_budgets_options()
        
    @rx.event
    def set_f_currency(self, val: str): self.f_currency = val
    @rx.event
    def set_f_amount(self, val: float): self.f_amount = val
    @rx.event
    def set_f_shop(self, val: str): self.f_shop = val
    @rx.event
    def set_f_desc(self, val: str): self.f_desc = val
    @rx.event
    def set_f_url(self, val: str): self.f_url = val
    @rx.event
    def set_f_account_id(self, val: str):
        self.f_account_id = val
        if val:
            for acc in self.cash_accounts:
                if acc.id == val:
                    self.f_currency = acc.currency
                    break

    # 货币兑换专属事件
    @rx.event
    def set_ex_source_curr(self, val: str):
        self.ex_source_curr = val
        self.ex_target_curr = "JPY" if val == "CNY" else "CNY"
        self.calc_exchange_estimate()
        
    @rx.event
    def set_ex_amount_out(self, val: float):
        self.ex_amount_out = val
        self.calc_exchange_estimate()
        
    @rx.event
    def set_ex_amount_in(self, val: float): self.ex_amount_in = val
    @rx.event
    def set_ex_source_acc_id(self, val: str): self.ex_source_acc_id = val
    @rx.event
    def set_ex_target_acc_id(self, val: str): self.ex_target_acc_id = val
    @rx.event
    def set_ex_desc(self, val: str): self.ex_desc = val

    # 债务管理专属事件
    @rx.event
    def set_debt_op(self, val: str): self.debt_op = val
    @rx.event
    def set_debt_name(self, val: str): self.debt_name = val
    @rx.event
    def set_debt_dest(self, val: str): self.debt_dest = val
    @rx.event
    def set_debt_rel_content(self, val: str): self.debt_rel_content = val
    @rx.event
    def set_debt_amount(self, val: float): self.debt_amount = val
    @rx.event
    def set_debt_curr(self, val: str): self.debt_curr = val
    @rx.event
    def set_debt_target_acc_id(self, val: str): self.debt_target_acc_id = val
    @rx.event
    def set_debt_source(self, val: str): self.debt_source = val
    @rx.event
    def set_debt_remark(self, val: str): self.debt_remark = val
    # 偿还债务
    @rx.event
    def set_debt_repay_type(self, val: str): self.debt_repay_type = val
    @rx.event
    def set_debt_selected_id(self, val: str):
        self.debt_selected_id = val
        # 联动自动填入债务最大金额
        if val:
            debt_id = int(val)
            for d in self.unsettled_debts:
                if int(d.id) == debt_id:
                    self.debt_repay_amount = d.amount
                    self.debt_curr = d.currency
                    break
                    
    @rx.event
    def set_debt_repay_amount(self, val: float): self.debt_repay_amount = val
    @rx.event
    def set_debt_repay_source_acc_id(self, val: str): self.debt_repay_source_acc_id = val
    @rx.event
    def set_debt_repay_remark(self, val: str): self.debt_repay_remark = val
    @rx.event
    def set_debt_repay_offset_asset_id(self, val: str): self.debt_repay_offset_asset_id = val

    # 资金移动专属事件
    @rx.event
    def set_move_from_asset_id(self, val: str): self.move_from_asset_id = val
    @rx.event
    def set_move_to_asset_id(self, val: str): self.move_to_asset_id = val
    @rx.event
    def set_move_amount(self, val: float): self.move_amount = val
    @rx.event
    def set_move_desc(self, val: str): self.move_desc = val

    # 批量商品成本与资产专属事件
    @rx.event
    def set_batch_product_id(self, val: str):
        self.batch_product_id = val
        self.load_budgets_options()
        
    @rx.event
    def set_batch_cost_cat(self, val: str):
        self.batch_cost_cat = val
        self.load_budgets_options()
        
    @rx.event
    def set_batch_asset_cat(self, val: str): self.batch_asset_cat = val
    @rx.event
    def set_batch_selected_budget_id(self, val: str): self.batch_selected_budget_id = val
    @rx.event
    def set_batch_shipping_fee(self, val: float): self.batch_shipping_fee = val

    @rx.event
    def set_temp_name(self, val: str): self.temp_name = val
    @rx.event
    def set_temp_amount(self, val: float): self.temp_amount = val
    @rx.event
    def set_temp_qty(self, val: float): self.temp_qty = val
    @rx.event
    def set_temp_desc(self, val: str): self.temp_desc = val
    @rx.event
    def set_temp_url(self, val: str): self.temp_url = val

    # 批量列表追加与移除
    @rx.event
    def add_batch_item(self):
        if not self.temp_name.strip():
            return rx.toast("明细名称不能为空！", level="warning")
        if self.temp_amount <= 0:
            return rx.toast("明细金额必须大于0！", level="warning")
            
        new_item = TempBatchItem(
            key=f"item_{len(self.batch_items)}",
            name=self.temp_name.strip(),
            amount=round(float(self.temp_amount), 2),
            qty=round(float(self.temp_qty), 2),
            desc=self.temp_desc.strip(),
            url=self.temp_url.strip()
        )
        self.batch_items.append(new_item)
        self.temp_name = ""
        self.temp_amount = 0.0
        self.temp_qty = 1.0
        self.temp_desc = ""
        self.temp_url = ""
        self.batch_items = list(self.batch_items)

    @rx.event
    def remove_batch_item(self, key: str):
        self.batch_items = [item for item in self.batch_items if item.key != key]

    # 编辑专属事件
    @rx.event
    def set_edit_selected_id(self, val: str):
        self.edit_selected_id = val
        if val:
            rec_id = int(val)
            db = self.get_db()
            try:
                from services.finance_service import FinanceService
                r = FinanceService.get_record_by_id(db, rec_id)
                if r:
                    self.edit_date = r.date.strftime("%Y-%m-%d")
                    self.edit_type = "收入" if r.amount > 0 else "支出"
                    self.edit_amount = abs(r.amount)
                    self.edit_category = r.category
                    self.edit_desc = r.description or ""
                    self.edit_url = r.url or ""
                    self.edit_acc_id = str(r.account_id) if r.account_id else ""
            finally:
                db.close()

    @rx.event
    def set_edit_date(self, val: str): self.edit_date = val
    @rx.event
    def set_edit_type(self, val: str): self.edit_type = val
    @rx.event
    def set_edit_acc_id(self, val: str): self.edit_acc_id = val
    @rx.event
    def set_edit_amount(self, val: float): self.edit_amount = val
    @rx.event
    def set_edit_category(self, val: str): self.edit_category = val
    @rx.event
    def set_edit_desc(self, val: str): self.edit_desc = val
    @rx.event
    def set_edit_url(self, val: str): self.edit_url = val

    @rx.event
    def set_delete_selected_id(self, val: str):
        self.delete_selected_id = val
        self.is_selected_delete_budget_related = False
        self.delete_include_budget = False
        if val:
            rec_id = int(val)
            db = self.get_db()
            try:
                from services.finance_service import FinanceService
                from models import CostItem
                rec = FinanceService.get_record_by_id(db, rec_id)
                if rec and rec.category == "商品成本" and rec.related_item_id:
                    target_cost = db.query(CostItem).filter(CostItem.id == rec.related_item_id).first()
                    if target_cost and target_cost.supplier == "预算设定":
                        self.is_selected_delete_budget_related = True
            except Exception:
                pass
            finally:
                db.close()

    @rx.event
    def set_delete_include_budget(self, val: bool):
        self.delete_include_budget = val

    # ===================== 业务计算辅助 =====================

    def calc_exchange_estimate(self):
        """按全局汇率自动计算汇率换算金额"""
        if self.ex_source_curr == "CNY":
            self.ex_amount_in = self.ex_amount_out / self.exchange_rate
        else:
            self.ex_amount_in = self.ex_amount_out * self.exchange_rate

    def reset_subform_variables(self):
        """重置各分类的变量"""
        self.f_date = date.today().strftime("%Y-%m-%d")
        self.f_amount = 0.0
        self.f_desc = ""
        self.f_shop = ""
        self.f_url = ""
        self.ex_amount_out = 0.0
        self.ex_amount_in = 0.0
        self.ex_desc = ""
        self.debt_name = ""
        self.debt_amount = 0.0
        self.debt_remark = ""
        self.debt_repay_amount = 0.0
        self.debt_repay_remark = ""
        self.move_amount = 0.0
        self.move_desc = ""
        self.batch_items = []
        self.batch_shipping_fee = 0.0

    # ===================== 加载列表数据 =====================

    @rx.event
    def load_finance_page(self):
        self.f_date = date.today().strftime("%Y-%m-%d")
        self.is_loading = True
        yield
        db = self.get_db()
        try:
            from services.finance_service import FinanceService
            import math
            
            # 1. 抓取真分页明细 (100条/页)
            df, total_rows = FinanceService.get_finance_records_page(db, page=self.page, page_size=100)
            self.total_records = total_rows
            self.total_pages = max(1, math.ceil(total_rows / 100))
            
            # 页码溢出容错
            if self.page > self.total_pages:
                self.page = self.total_pages
                df, _ = FinanceService.get_finance_records_page(db, page=self.page, page_size=100)

            # 解析为 Pydantic 强类型记录
            processed_records = []
            for _, row in df.iterrows():
                processed_records.append(
                    FinanceRecordItem(
                        id=int(row["ID"]),
                        date=row["日期"].strftime("%Y-%m-%d"),
                        currency=row["币种"],
                        type=row["收支"],
                        amount=round(float(row["金额"]), 2),
                        category=row["分类"],
                        desc=row["备注"],
                        url=row["网址"],
                        cny_bal=round(float(row["当前CNY余额"]), 2),
                        jpy_bal=round(float(row["当前JPY余额"]), 2)
                    )
                )
            self.records = processed_records
            
            # 2. 当前总额指标
            cny_bal, jpy_bal = FinanceService.get_current_balances(db)
            self.cur_cny = round(float(cny_bal), 2)
            self.cur_jpy = round(float(jpy_bal), 2)
            
            # 3. 加载缓存的下拉选项
            # A. 现金账户
            cash_list = FinanceService.get_transferable_assets(db)
            self.cash_accounts = [
                CashAccountOption(
                    id=str(a.id),
                    label=f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})",
                    currency=a.currency
                )
                for a in cash_list
            ]
            
            # B. 负债
            liab_list = FinanceService.get_balance_items(db, "liability")
            self.unsettled_debts = [
                DebtOption(id=str(l.id), label=f"{l.name} (待还余额: {l.amount:,.2f})", amount=float(l.amount), currency=l.currency)
                for l in liab_list
            ]
            
            # C. 抵债资产
            asset_list = FinanceService.get_balance_items(db, "asset")
            self.offset_assets = [
                AssetOption(id=str(a.id), label=f"{a.name} (余额: {a.amount:,.2f})")
                for a in asset_list if not a.name.startswith(("在制", "预入库", "流动资金"))
            ]
            
            # D. 商品列表
            p_list = FinanceService.get_all_products(db)
            self.products_list = [
                ProductOption(id=str(p.id), label=p.name)
                for p in p_list
            ]
            
            # 初始化默认的外键 ID
            if self.cash_accounts:
                if not self.f_account_id:
                    self.f_account_id = self.cash_accounts[0].id
                    self.f_currency = self.cash_accounts[0].currency
                else:
                    for acc in self.cash_accounts:
                        if acc.id == self.f_account_id:
                            self.f_currency = acc.currency
                            break
                if not self.ex_source_acc_id: self.ex_source_acc_id = self.cash_accounts[0].id
                if not self.ex_target_acc_id: self.ex_target_acc_id = self.cash_accounts[0].id
                if not self.debt_target_acc_id: self.debt_target_acc_id = self.cash_accounts[0].id
                if not self.debt_repay_source_acc_id: self.debt_repay_source_acc_id = self.cash_accounts[0].id
                if not self.move_from_asset_id: self.move_from_asset_id = self.cash_accounts[0].id
                if not self.move_to_asset_id: self.move_to_asset_id = self.cash_accounts[0].id
                
            if self.products_list and not self.batch_product_id:
                self.batch_product_id = self.products_list[0].id
                
            if self.unsettled_debts and not self.debt_selected_id:
                self.debt_selected_id = self.unsettled_debts[0].id
                
            if self.offset_assets and not self.debt_repay_offset_asset_id:
                self.debt_repay_offset_asset_id = self.offset_assets[0].id

            self.load_budgets_options()

        except Exception as e:
            print(f"[FinanceState] load_finance_page error: {e}")
        finally:
            db.close()
            self.is_loading = False

    def load_budgets_options(self):
        """联动加载当前选定商品下的预算项选项"""
        if not self.batch_product_id:
            self.budgets_list = []
            return
            
        p_id = int(self.batch_product_id)
        db = self.get_db()
        try:
            from services.finance_service import FinanceService
            budgets = FinanceService.get_budget_items(db, p_id, self.batch_cost_cat)
            self.budgets_list = [
                BudgetOption(id=str(b.id), label=b.item_name)
                for b in budgets
            ]
            self.batch_selected_budget_id = ""
        finally:
            db.close()

    @rx.event
    def change_page(self, delta: int):
        target = self.page + delta
        if 1 <= target <= self.total_pages:
            self.page = target
            yield FinanceState.load_finance_page()

    # ===================== 数据写入与动作提交 =====================

    @rx.event
    def submit_add_form(self):
        db = self.get_db()
        try:
            from services.finance_service import FinanceService
            from cache_manager import sync_all_caches
            
            # ---- 场景 A: 货币兑换 ----
            if self.rec_type == "货币兑换":
                if self.ex_amount_out <= 0 or self.ex_amount_in <= 0:
                    yield rx.toast("兑换出入账金额必须大于 0", level="warning")
                    return
                
                src_acc = int(self.ex_source_acc_id) if self.ex_source_acc_id else None
                tgt_acc = int(self.ex_target_acc_id) if self.ex_target_acc_id else None
                
                FinanceService.execute_exchange(
                    db,
                    date_val=date.fromisoformat(self.f_date),
                    source_curr=self.ex_source_curr,
                    target_curr=self.ex_target_curr,
                    amount_out=self.ex_amount_out,
                    amount_in=self.ex_amount_in,
                    desc=self.ex_desc.strip(),
                    source_acc_id=src_acc,
                    target_acc_id=tgt_acc
                )
                yield rx.toast("💱 货币兑换成功！")

            # ---- 场景 B: 债务管理 ----
            elif self.rec_type == "债务":
                if "新增" in self.debt_op:
                    if not self.debt_name.strip() or self.debt_amount <= 0:
                        yield rx.toast("请填写债务名称并确保金额大于 0！", level="warning")
                        return
                    
                    is_to_cash = (self.debt_dest == "存入流动资金 (拿到现金)")
                    if not is_to_cash and not self.debt_rel_content.strip():
                        yield rx.toast("请填写关联挂账的资产名称！", level="warning")
                        return
                        
                    tgt_acc = int(self.debt_target_acc_id) if self.debt_target_acc_id else None
                    
                    FinanceService.create_debt(
                        db,
                        date_val=date.fromisoformat(self.f_date),
                        curr=self.debt_curr,
                        name=self.debt_name.strip(),
                        amount=self.debt_amount,
                        source=self.debt_source.strip(),
                        remark=self.debt_remark.strip(),
                        is_to_cash=is_to_cash,
                        related_content=self.debt_rel_content.strip(),
                        target_acc_id=tgt_acc
                    )
                    yield rx.toast("📝 新增债务成功！")
                else:
                    # 偿还债务
                    if not self.debt_selected_id:
                        yield rx.toast("当前无记录在案的债务可偿清！", level="warning")
                        return
                    if self.debt_repay_amount <= 0:
                        yield rx.toast("还款金额必须大于 0！", level="warning")
                        return
                        
                    sel_debt_id = int(self.debt_selected_id)
                    
                    if "资金" in self.debt_repay_type:
                        src_acc = int(self.debt_repay_source_acc_id) if self.debt_repay_source_acc_id else None
                        FinanceService.repay_debt(
                            db,
                            date_val=date.fromisoformat(self.f_date),
                            debt_id=sel_debt_id,
                            amount=self.debt_repay_amount,
                            remark=self.debt_repay_remark.strip(),
                            source_acc_id=src_acc
                        )
                        yield rx.toast("💸 债务资金偿还成功！")
                    else:
                        # 资产抵消
                        if not self.debt_repay_offset_asset_id:
                            yield rx.toast("请先选择抵债资产项！", level="warning")
                            return
                            
                        asset_id = int(self.debt_repay_offset_asset_id)
                        FinanceService.offset_debt(
                            db,
                            date_val=date.fromisoformat(self.f_date),
                            debt_id=sel_debt_id,
                            asset_id=asset_id,
                            amount=self.debt_repay_amount,
                            remark=self.debt_repay_remark.strip()
                        )
                        yield rx.toast("🔄 资产抵债核销成功！")

            # ---- 场景 C: 普通收入 / 支出 (普通录入 + 批量分割) ----
            elif self.rec_type in ["收入", "支出"]:
                is_batch_mode = self.rec_type == "支出" and self.f_category in ["商品成本", "固定资产购入", "其他资产购入"]
                
                # A. 批量录入模式
                if is_batch_mode:
                    if not self.batch_items and self.batch_shipping_fee <= 0:
                        yield rx.toast("请先在下方明细表中至少录入一项明细或提供邮费金额！", level="warning")
                        return
                    if not self.f_account_id:
                        yield rx.toast("未指定操作现金扣款账户！", level="warning")
                        return
                        
                    items_data = []
                    for item in self.batch_items:
                        items_data.append({
                            "name": item.name,
                            "amount": item.amount,
                            "qty": item.qty,
                            "desc": item.desc,
                            "url": item.url
                        })
                        
                    base_data = {
                        "date": date.fromisoformat(self.f_date),
                        "currency": self.f_currency,
                        "account_id": int(self.f_account_id),
                        "shop": self.f_shop.strip(),
                        "category": self.f_category
                    }
                    
                    batch_config = {
                        "product_id": int(self.batch_product_id) if self.batch_product_id else None,
                        "cost_cat": self.batch_cost_cat,
                        "asset_cat": self.batch_asset_cat,
                        "shipping_fee": self.batch_shipping_fee
                    }
                    
                    # 匹配预算模式
                    selected_budget_id = int(self.batch_selected_budget_id) if self.batch_selected_budget_id else None
                    if selected_budget_id:
                        # 强绑定为单条记录匹配预算
                        if len(self.batch_items) != 1:
                            yield rx.toast("匹配特定预算项时，物品明细表内只能有且仅有一条物品记录！", level="warning")
                            return
                            
                        first_item = self.batch_items[0]
                        base_data = {
                            "date": date.fromisoformat(self.f_date), "type": "支出", "currency": self.f_currency,
                            "amount": first_item.amount, "category": self.f_category, "shop": self.f_shop.strip(),
                            "desc": first_item.desc, "url": first_item.url, "account_id": int(self.f_account_id)
                        }
                        
                        link_config = {
                            "link_type": "cost", "target_cost_id": selected_budget_id,
                            "name": first_item.name, "qty": first_item.qty,
                            "unit_price": first_item.amount / first_item.qty if first_item.qty else 0,
                            "product_id": int(self.batch_product_id), "cat": self.batch_cost_cat
                        }
                        
                        msg = FinanceService.create_general_transaction(db, base_data, link_config, self.exchange_rate)
                        yield rx.toast(f"🎯 预算匹配成功: {msg}")
                    else:
                        # 纯批量切账单模式
                        msg = FinanceService.create_batch_expense_transaction(
                            db, base_data, batch_config, items_data, self.exchange_rate
                        )
                        yield rx.toast(f"📦 {msg}")

                # B. 单项通用录入模式
                else:
                    if self.f_amount <= 0:
                        yield rx.toast("录入金额必须大于 0！", level="warning")
                        return
                        
                    # 非现金类别不需要现金账户
                    is_non_cash = self.f_category in FinanceService.NON_CASH_CATEGORIES
                    acc_id = int(self.f_account_id) if (not is_non_cash and self.f_account_id) else None
                    
                    base_data = {
                        "date": date.fromisoformat(self.f_date), "type": self.rec_type, "currency": self.f_currency,
                        "amount": self.f_amount, "category": self.f_category, "shop": self.f_shop.strip(),
                        "desc": self.f_desc.strip(), "url": self.f_url.strip(), "account_id": acc_id,
                        "is_non_cash": is_non_cash
                    }
                    
                    # 确定业务映射类型
                    link_config = {
                        "link_type": None, "is_new": False, "target_id": None,
                        "name": "", "qty": 1.0, "unit_price": self.f_amount, "product_id": None, "cat": ""
                    }
                    
                    msg = FinanceService.create_general_transaction(db, base_data, link_config, self.exchange_rate)
                    yield rx.toast(f"💾 记账成功: {msg}")

            # ---- 场景 D: 资金移动 ----
            elif self.rec_type == "资金移动":
                if not self.move_from_asset_id or not self.move_to_asset_id:
                    yield rx.toast("请选择转出账户和转入账户！", level="warning")
                    return
                if self.move_from_asset_id == self.move_to_asset_id:
                    yield rx.toast("转出和转入不能是同一个现金账户！", level="warning")
                    return
                if self.move_amount <= 0:
                    yield rx.toast("资金划转金额必须大于 0！", level="warning")
                    return
                    
                from_id = int(self.move_from_asset_id)
                to_id = int(self.move_to_asset_id)
                
                FinanceService.execute_fund_transfer(
                    db,
                    date_val=date.fromisoformat(self.f_date),
                    from_asset_id=from_id,
                    to_asset_id=to_id,
                    amount=self.move_amount,
                    desc=self.move_desc.strip()
                )
                yield rx.toast(f"🔄 内部资金划转成功：{self.move_amount} 元")

            # 清空重置表单并加载数据
            self.form_ver += 1
            self.reset_subform_variables()
            sync_all_caches()
            yield FinanceState.load_finance_page()

        except Exception as e:
            yield rx.toast(f"保存录入失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def submit_delete_record(self):
        if not self.delete_selected_id:
            yield rx.toast("请选择要删除的流水记录！", level="warning")
            return
            
        rec_id = int(self.delete_selected_id)
        db = self.get_db()
        try:
            from services.finance_service import FinanceService
            from cache_manager import sync_all_caches
            
            # 服务端删除逻辑，内置核心销售流水拦截保护
            msg = FinanceService.delete_record(db, rec_id, include_budget=self.delete_include_budget)
            if msg is not False:
                yield rx.toast(f"🗑️ 删除流水成功，级联撤销: {msg}")
                self.delete_selected_id = ""
                sync_all_caches()
                yield FinanceState.load_finance_page()
            else:
                yield rx.toast("删除失败，记录不存在！", level="error")
        except Exception as e:
            yield rx.toast(str(e), level="error")
        finally:
            db.close()

    @rx.event
    def submit_edit_record(self):
        if not self.edit_selected_id:
            yield rx.toast("请选择要修改的流水记录！", level="warning")
            return
            
        rec_id = int(self.edit_selected_id)
        db = self.get_db()
        try:
            from services.finance_service import FinanceService
            from cache_manager import sync_all_caches
            
            updates = {
                "date": date.fromisoformat(self.edit_date),
                "type": self.edit_type,
                "amount_abs": self.edit_amount,
                "category": self.edit_category.strip(),
                "desc": self.edit_desc.strip(),
                "url": self.edit_url.strip(),
                "account_id": int(self.edit_acc_id) if self.edit_acc_id else None
            }
            
            if FinanceService.update_record(db, rec_id, updates):
                yield rx.toast("💾 流水修改保存成功！")
                self.edit_selected_id = ""
                sync_all_caches()
                yield FinanceState.load_finance_page()
            else:
                yield rx.toast("流水修改失败！", level="error")
        except Exception as e:
            yield rx.toast(f"修改失败: {e}", level="error")
        finally:
            db.close()
