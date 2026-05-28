# yurara_app/state/consumable_state.py
"""
其他资产管理(耗材) State 模块。
管理耗材列表、出入库操作逻辑（包含联动生成销售流水及分摊商品成本）、编辑保存及审计日志日期修改。
"""
import reflex as rx
from pydantic import BaseModel
from datetime import date
from ..state.app_state import AppState
from services.consumable_service import ConsumableService
from models import CompanyBalanceItem
from cache_manager import sync_all_caches

class ConsumableItem(BaseModel):
    id: int = 0
    name: str = ""
    category: str = ""
    currency: str = ""
    unit_price: float = 0.0
    remaining_qty: float = 0.0
    remaining_cny: float = 0.0
    remaining_jpy: float = 0.0
    shop_name: str = ""
    url: str = ""
    remarks: str = ""

class ConsumableLogItem(BaseModel):
    id: int = 0
    date: str = ""
    item_name: str = ""
    change_qty: float = 0.0
    note: str = ""

class DropdownOption(BaseModel):
    value: str = ""
    label: str = ""

class ConsumableState(AppState):
    items: list[ConsumableItem] = []
    logs: list[ConsumableLogItem] = []
    
    # 统计数据
    total_cny: float = 0.0
    total_jpy: float = 0.0
    grand_total_cny: float = 0.0
    
    is_loading: bool = False
    
    # 下拉基础选项
    active_item_names: list[str] = []
    cash_accounts: list[DropdownOption] = []
    products_list: list[DropdownOption] = []
    
    # 快速库存操作表单状态
    op_date: str = ""              # 操作日期 (YYYY-MM-DD)
    op_item_name: str = ""         # 选中物品
    op_type: str = "出库"          # "出库" 或 "入库"
    op_qty: float = 1.0           # 操作数量
    out_mode: str = "内部消耗"      # "内部消耗" 或 "对外销售"
    
    # 对外销售信息表单
    sale_content: str = ""
    sale_source: str = ""
    sale_amount: float = 0.0
    sale_currency: str = "CNY"
    sale_account_id: str = ""
    sale_remark: str = ""
    
    # 内部消耗信息表单
    is_link_product: bool = False
    target_product_id: str = ""
    target_cost_category: str = "包装费"
    
    # 通用备注
    op_remark: str = ""

    # 编辑模态框状态
    is_edit_open: bool = False
    edit_item_id: int = 0
    edit_name: str = ""
    edit_category: str = ""
    edit_currency: str = "CNY"
    edit_unit_price: float = 0.0
    edit_remaining_qty: float = 0.0
    edit_shop_name: str = ""
    edit_url: str = ""
    edit_remarks: str = ""

    # ===================== 计算属性 =====================

    @rx.var
    def total_cny_str(self) -> str:
        return f"¥ {self.total_cny:,.2f}"

    @rx.var
    def total_jpy_str(self) -> str:
        return f"¥ {self.total_jpy:,.0f}"

    @rx.var
    def grand_total_cny_str(self) -> str:
        return f"¥ {self.grand_total_cny:,.2f}"

    @rx.var
    def has_items(self) -> bool:
        return len(self.items) > 0

    @rx.var
    def is_outbound(self) -> bool:
        return self.op_type == "出库"

    @rx.var
    def is_sale(self) -> bool:
        return (self.op_type == "出库") & (self.out_mode == "对外销售")

    @rx.var
    def is_internal(self) -> bool:
        return (self.op_type == "出库") & (self.out_mode == "内部消耗")

    # ===================== 事件处理器 =====================

    @rx.event
    def load_consumable_page(self):
        """加载耗材清单、汇总指标、日志、商品和收款账户列表"""
        self.is_loading = True
        db = self.get_db()
        try:
            service = ConsumableService(db)
            
            # 1. 资产清单
            raw_items = service.get_all_consumables()
            formatted_items = []
            t_cny = 0.0
            t_jpy = 0.0
            
            for i in raw_items:
                curr = getattr(i, "currency", "CNY")
                qty = i.remaining_qty
                unit_price = i.unit_price
                val_origin = unit_price * qty
                
                show_cny = val_origin if curr != "JPY" else 0.0
                show_jpy = val_origin if curr == "JPY" else 0.0
                
                # 过滤无库存或无价值的项
                if qty <= 0.001 and val_origin <= 0.001:
                    continue

                if curr == "JPY":
                    t_jpy += val_origin
                else:
                    t_cny += val_origin

                formatted_items.append(ConsumableItem(
                    id=i.id,
                    name=i.name,
                    category=i.category or "",
                    currency=curr,
                    unit_price=unit_price,
                    remaining_qty=qty,
                    remaining_cny=show_cny,
                    remaining_jpy=show_jpy,
                    shop_name=i.shop_name or "",
                    url=getattr(i, 'url', '') or "",
                    remarks=i.remarks or ""
                ))
            
            self.items = formatted_items
            self.total_cny = t_cny
            self.total_jpy = t_jpy
            self.grand_total_cny = t_cny + (t_jpy * self.exchange_rate)

            # 2. 快速操作默认值
            active_list = service.get_active_consumables()
            self.active_item_names = [x.name for x in active_list]
            if self.active_item_names and not self.op_item_name:
                self.op_item_name = self.active_item_names[0]
                self.sale_content = f"售出 {self.op_item_name}"
            
            if not self.op_date:
                self.op_date = date.today().strftime("%Y-%m-%d")

            # 3. 日志记录
            raw_logs = service.get_logs()
            self.logs = [ConsumableLogItem(
                id=l.id,
                date=str(l.date),
                item_name=l.item_name,
                change_qty=l.change_qty,
                note=l.note or ""
            ) for l in raw_logs]

            # 4. 流动资金账户 (现金类型资产)
            cash_items = db.query(CompanyBalanceItem).filter(
                CompanyBalanceItem.category == "asset",
                CompanyBalanceItem.asset_type == "现金"
            ).all()
            self.cash_accounts = [DropdownOption(
                value=str(a.id),
                label=f"[{a.currency}] {a.name}"
            ) for a in cash_items]
            if self.cash_accounts and not self.sale_account_id:
                self.sale_account_id = self.cash_accounts[0].value

            # 5. 可归属的商品大货列表
            products = service.get_all_products()
            self.products_list = [DropdownOption(
                value=str(p.id),
                label=p.name
            ) for p in products]
            if self.products_list and not self.target_product_id:
                self.target_product_id = self.products_list[0].value

        finally:
            db.close()
            self.is_loading = False

    @rx.event
    def on_change_item_name(self, name: str):
        self.op_item_name = name
        self.sale_content = f"售出 {name}"

    @rx.event
    def submit_inventory_change(self):
        """执行快速出入库处理，包括联动计费或记账"""
        if not self.op_item_name or self.op_item_name == "暂无库存":
            return rx.toast("请选择有效的库存项目", level="error")
        if self.op_qty <= 0:
            return rx.toast("变动数量必须大于 0", level="error")
            
        db = self.get_db()
        try:
            service = ConsumableService(db)
            sign = -1 if self.op_type == "出库" else 1
            qty_delta = self.op_qty * sign
            
            mode = "normal"
            s_info = None
            c_info = None
            final_remark = self.op_remark
            
            # 出库特别配置
            if self.op_type == "出库":
                if self.out_mode == "对外销售":
                    if self.sale_amount <= 0:
                        yield rx.toast("⚠️ 销售金额为 0，仅扣减库存，不生成流水", level="warning")
                    if not self.sale_content.strip():
                        return rx.toast("请输入收入内容说明", level="error")
                    if not self.sale_account_id:
                        return rx.toast("请选择收款资金账户", level="error")
                        
                    mode = "sale"
                    s_info = {
                        "content": self.sale_content.strip(),
                        "source": self.sale_source.strip(),
                        "amount": self.sale_amount,
                        "currency": self.sale_currency,
                        "remark": self.sale_remark.strip(),
                        "account_id": int(self.sale_account_id)
                    }
                elif self.is_link_product and self.target_product_id:
                    mode = "cost"
                    c_info = {
                        "product_id": int(self.target_product_id),
                        "category": self.target_cost_category,
                        "remark": self.op_remark.strip()
                    }

            # 解析日期对象
            try:
                op_date_obj = date.fromisoformat(self.op_date)
            except ValueError:
                op_date_obj = date.today()

            # 调用 Service 写入
            name, delta, link_msg = service.process_inventory_change(
                item_name=self.op_item_name,
                date_obj=op_date_obj,
                delta_qty=qty_delta,
                exchange_rate=self.exchange_rate,
                mode=mode,
                sale_info=s_info,
                cost_info=c_info,
                base_remark=final_remark
            )

            msg_icon = "💰" if self.is_sale else ("📉" if qty_delta < 0 else "📈")
            yield rx.toast(f"库存更新成功：{name} {delta} {link_msg}", icon=msg_icon)
            
            # 全局同步缓存并重置页面状态
            sync_all_caches()
            self.op_qty = 1.0
            self.op_remark = ""
            self.sale_amount = 0.0
            self.sale_source = ""
            self.sale_remark = ""
            
            yield ConsumableState.load_consumable_page()
            
        except ValueError as e:
            yield rx.toast(str(e), level="error")
        except Exception as e:
            yield rx.toast(f"操作失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def open_edit_dialog(self, item: ConsumableItem):
        """打开并初始化修改耗材对话框"""
        self.edit_item_id = item.id
        self.edit_name = item.name
        self.edit_category = item.category
        self.edit_currency = item.currency
        self.edit_unit_price = item.unit_price
        self.edit_remaining_qty = item.remaining_qty
        self.edit_shop_name = item.shop_name
        self.edit_url = item.url
        self.edit_remarks = item.remarks
        self.is_edit_open = True

    @rx.event
    def close_edit_dialog(self):
        self.is_edit_open = False
        self.edit_item_id = 0

    @rx.event
    def submit_edit_item(self):
        """保存耗材修改数据"""
        if not self.edit_name.strip():
            return rx.toast("项目名称不能为空", level="error")
        if self.edit_unit_price < 0 or self.edit_remaining_qty < 0:
            return rx.toast("单价或数量不能为负数", level="error")

        db = self.get_db()
        try:
            service = ConsumableService(db)
            changes = {
                self.edit_item_id: {
                    "name": self.edit_name.strip(),
                    "category": self.edit_category.strip(),
                    "currency": self.edit_currency,
                    "unit_price": self.edit_unit_price,
                    "remaining_qty": self.edit_remaining_qty,
                    "shop_name": self.edit_shop_name.strip(),
                    "url": self.edit_url.strip(),
                    "remarks": self.edit_remarks.strip()
                }
            }
            if service.update_items_batch(changes):
                yield rx.toast("耗材资产更新成功！", icon="💾")
                self.is_edit_open = False
                yield ConsumableState.load_consumable_page()
            else:
                yield rx.toast("保存修改失败，未找到该项目", level="error")
        except Exception as e:
            yield rx.toast(f"保存更新发生异常: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def update_log_date(self, log_id: int, new_date: str):
        """在历史日志表格中修改账期"""
        if not new_date.strip():
            return
        db = self.get_db()
        try:
            service = ConsumableService(db)
            log_changes = {
                log_id: {"date": new_date.strip()}
            }
            if service.update_logs_batch(log_changes):
                yield rx.toast("账期修改成功", icon="📅")
                yield ConsumableState.load_consumable_page()
            else:
                yield rx.toast("账期修改失败", level="error")
        except Exception as e:
            yield rx.toast(f"修改日志日期失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def set_op_qty(self, val: float):
        self.op_qty = val

    @rx.event
    def set_sale_amount(self, val: float):
        self.sale_amount = val

    @rx.event
    def set_edit_unit_price(self, val: float):
        self.edit_unit_price = val

    @rx.event
    def set_edit_remaining_qty(self, val: float):
        self.edit_remaining_qty = val

    @rx.event
    def set_op_date(self, val: str): self.op_date = val

    @rx.event
    def set_op_type(self, val: str): self.op_type = val

    @rx.event
    def set_out_mode(self, val: str): self.out_mode = val

    @rx.event
    def set_sale_content(self, val: str): self.sale_content = val

    @rx.event
    def set_sale_source(self, val: str): self.sale_source = val

    @rx.event
    def set_sale_currency(self, val: str): self.sale_currency = val

    @rx.event
    def set_sale_account_id(self, val: str): self.sale_account_id = val

    @rx.event
    def set_sale_remark(self, val: str): self.sale_remark = val

    @rx.event
    def set_is_link_product(self, val: bool): self.is_link_product = val

    @rx.event
    def set_target_product_id(self, val: str): self.target_product_id = val

    @rx.event
    def set_target_cost_category(self, val: str): self.target_cost_category = val

    @rx.event
    def set_op_remark(self, val: str): self.op_remark = val

    @rx.event
    def set_edit_name(self, val: str): self.edit_name = val

    @rx.event
    def set_edit_category(self, val: str): self.edit_category = val

    @rx.event
    def set_edit_currency(self, val: str): self.edit_currency = val

    @rx.event
    def set_edit_shop_name(self, val: str): self.edit_shop_name = val

    @rx.event
    def set_edit_url(self, val: str): self.edit_url = val

    @rx.event
    def set_edit_remarks(self, val: str): self.edit_remarks = val
