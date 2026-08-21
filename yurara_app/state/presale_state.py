# yurara_app/state/presale_state.py
"""
预售销售管理 State 模块。
管理预售定金购物车建单、尾款单号精确查找与绑定、尾款物理一键解绑、Excel批量定金建单与尾款自动匹配导入、以及 Dialog 物理级联售后联动。
"""
import io
import math
import reflex as rx
import pandas as pd
from datetime import date
from pydantic import BaseModel
from typing import Any
from ..state.app_state import AppState
from services.sales_order_service import SalesOrderService
from services.product_service import ProductService
from services.inventory_service import InventoryService
from constants import PLATFORM_CODES, OrderStatus
from models import Product, Warehouse, CompanyBalanceItem, SalesOrder, InventoryLog, SalesOrderItem


class PresaleOrderRow(BaseModel):
    勾选: bool = False
    id: int = 0
    order_no: str = ""
    final_order_no: str = ""
    status: str = ""
    items_summary: str = ""
    deposit_amount: float = 0.0
    final_amount: float = 0.0
    refunded_amount: float = 0.0
    discount_note: str = "-"
    currency: str = "CNY"
    platform: str = ""
    created_date: str = ""
    notes: str = ""
    search_keywords: str = ""


class SplitItemModel(BaseModel):
    item_id: int = 0
    product_name: str = ""
    variant: str = ""
    warehouse_name: str = ""
    max_qty: int = 0
    split_qty: int = 0
    unit_deposit: float = 0.0


class ResendItemModel(BaseModel):
    order_item_id: int = 0
    product_name: str = ""
    variant: str = ""
    quantity: int = 0
    warehouse_id: int = 0
    warehouse_name: str = ""
    part_name: str = "整套"
    part_options: list[str] = []


class PresaleState(AppState):
    # --- 页面状态 ---
    active_tab: str = "all"  # "all", "deposit", "final", "pending", "shipped", "completed", "after_sales"
    orders: list[PresaleOrderRow] = []
    selected_order_ids: list[int] = []
    selected_product_filter: str = "全部商品"
    is_loading: bool = False
    search_query: str = ""
    page_index: int = 1
    page_size: int = 50

    # --- 统计指标 ---
    stat_total: int = 0
    stat_pending_deposit: int = 0
    stat_pending_final: int = 0
    stat_pending: int = 0
    stat_shipped: int = 0
    stat_completed: int = 0

    # ===================== 手动建单定金状态 =====================
    create_mode: str = "1️⃣ 创建主定金订单"  # 或 "2️⃣ 绑定尾款单"
    pre_order_no: str = ""
    pre_date_input: str = ""  # Today
    pre_plat: str = "微店"
    pre_curr: str = "CNY"
    pre_target_account: str = ""
    pre_tp: float = 0.0
    pre_fee: bool = True
    pre_discount: str = ""
    pre_notes: str = ""
    pre_cart: list[dict] = []  # dict keys: key, product_name, variant, quantity, warehouse_id, warehouse_name

    # --- 购物车暂存添加项 ---
    sel_p_name: str = ""
    sel_v_name: str = ""
    sel_qty: int = 1
    sel_wh_name: str = ""

    # ===================== 2️⃣ 绑定尾款面板状态 =====================
    search_dep_no: str = ""
    found_deposit_order_id: int = 0
    found_deposit_order_no: str = ""
    found_deposit_order_date: str = ""
    found_deposit_order_platform: str = ""
    found_deposit_order_currency: str = ""
    found_deposit_order_items: list[dict] = []  # keys: product_name, variant, quantity
    show_search_lock: bool = False

    # --- 尾款绑定表单 ---
    final_no_input: str = ""
    final_amount_input: float = 0.0
    pre_fee_final: bool = True
    f_notes: str = ""

    # ===================== Excel 批量导入状态 =====================
    parsed_preview_orders: list[dict] = []  # keys: stock_warning, order_no, platform, target_account, currency, total_qty, gross_price, fee, net_price, items_str, matched_deposit_id, discount_note
    excel_import_errors: list[str] = []
    bulk_presale_mode: str = "🚀 批量导入定金"  # 或 "🔗 批量匹配并绑定尾款"

    # ===================== 批量修改发货仓库 =====================
    show_batch_wh_modal: bool = False
    batch_target_wh_name: str = ""

    # ===================== 单个订单操作与详情 =====================
    active_detail_order_id: int = 0
    show_detail_flag: bool = False

    detail_order_no: str = ""
    detail_final_order_no: str = ""
    detail_status: str = ""
    detail_platform: str = ""
    detail_currency: str = ""
    detail_created_date: str = ""
    detail_shipped_date: str = ""
    detail_completed_date: str = ""
    detail_target_account: str = ""
    detail_notes: str = ""
    detail_discount_note: str = ""
    detail_items: list[dict] = []  # keys: product_name, variant, warehouse_name, quantity, subtotal
    detail_deposit_amount: float = 0.0
    detail_final_amount: float = 0.0
    detail_total_amount: float = 0.0

    # --- 编辑表单 ---
    edit_discount_note: str = ""
    edit_notes: str = ""

    # --- 删除订单二次确认 ---
    show_delete_confirm: bool = False

    # ===================== 拆分定金订单 Dialog 状态 =====================
    show_split_modal: bool = False
    split_target_order_id: int = 0
    split_base_order_no: str = ""
    split_next_order_no: str = ""
    split_orig_deposit: float = 0.0
    split_orig_total_qty: int = 0
    split_items_data: list[SplitItemModel] = []

    # ===================== 售后 Dialog 状态 =====================
    active_refund_order_id: int = 0
    show_refund_form: bool = False

    existing_refunds: list[dict] = []  # keys: id, refund_date, refund_reason, refund_amount, is_returned, is_resend, is_editing
    
    # --- 新售后表单 ---
    ref_amount_input: float = 0.0
    ref_reason_input: str = ""
    ref_is_returned: bool = False
    ref_is_resend: bool = False
    ref_returned_items: list[dict] = []  # keys: order_item_id, product_name, variant, max_quantity, quantity, warehouse_id, warehouse_name
    ref_resend_items: list[ResendItemModel] = []  # strongly typed list of ResendItemModel

    # --- 编辑已有售后明细 ---
    editing_refund_id: int = 0
    editing_refund_amount: float = 0.0
    editing_refund_reason: str = ""

    # ===================== 计算属性 =====================

    @rx.var
    def has_orders(self) -> bool:
        return len(self.filtered_orders) > 0

    @rx.var
    def selected_orders_statuses(self) -> list[str]:
        res = []
        for o_id in self.selected_order_ids:
            for o in self.orders:
                if o.id == o_id:
                    res.append(o.status)
                    break
        return res

    @rx.var
    def can_complete_deposit(self) -> bool:
        statuses = self.selected_orders_statuses
        if not statuses:
            return False
        return all(s == "🕒 待完成定金" for s in statuses)

    @rx.var
    def can_ship(self) -> bool:
        statuses = self.selected_orders_statuses
        if not statuses:
            return False
        return all(s == "📦 待发货" for s in statuses)

    @rx.var
    def can_complete(self) -> bool:
        statuses = self.selected_orders_statuses
        if not statuses:
            return False
        return all(s in ["🚚 已发货", "🔧 售后"] for s in statuses)

    @rx.var
    def can_refund(self) -> bool:
        if self.selected_count != 1:
            return False
        statuses = self.selected_orders_statuses
        if not statuses:
            return False
        return statuses[0] in ["🚚 已发货", "✅ 完成", "🔧 售后"]

    @rx.var
    def filtered_orders(self) -> list[PresaleOrderRow]:
        query = self.search_query.strip().lower()
        if not query:
            return self.orders
        res = []
        for o in self.orders:
            if (query in o.order_no.lower() or 
                query in o.final_order_no.lower() or
                query in o.platform.lower() or 
                query in o.notes.lower() or 
                query in o.items_summary.lower() or 
                query in o.search_keywords.lower() or
                query in o.created_date.lower() or 
                query in o.status.lower() or
                query in o.discount_note.lower()):
                res.append(o)
        return res

    @rx.var
    def paginated_orders(self) -> list[PresaleOrderRow]:
        start = (self.page_index - 1) * self.page_size
        end = start + self.page_size
        return self.filtered_orders[start:end]

    @rx.var
    def total_pages(self) -> int:
        n = len(self.filtered_orders)
        if n == 0:
            return 1
        return math.ceil(n / self.page_size)

    @rx.var
    def page_info(self) -> str:
        total = len(self.filtered_orders)
        if total == 0:
            return "0-0 of 0"
        start = (self.page_index - 1) * self.page_size + 1
        end = min(self.page_index * self.page_size, total)
        return f"{start}-{end} of {total}"

    @rx.var
    def has_prev_page(self) -> bool:
        return self.page_index > 1

    @rx.var
    def has_next_page(self) -> bool:
        return self.page_index < self.total_pages

    @rx.var
    def is_select_all(self) -> bool:
        if not self.orders:
            return False
        return all(o.勾选 for o in self.orders)

    @rx.var
    def selected_count(self) -> int:
        return len(self.selected_order_ids)

    @rx.var
    def can_batch_edit_wh(self) -> bool:
        return self.selected_count > 0

    @rx.var
    def is_single_selected(self) -> bool:
        return self.selected_count == 1

    @rx.var
    def single_selected_id(self) -> int:
        return self.selected_order_ids[0] if self.is_single_selected else 0

    @rx.var
    def selected_final_amount_sum(self) -> float:
        return round(sum(o.final_amount for o in self.orders if o.勾选), 2)

    @rx.var
    def selected_amount_sum(self) -> float:
        return round(sum(o.deposit_amount + o.final_amount for o in self.orders if o.勾选), 2)

    @rx.var
    def active_variants(self) -> list[str]:
        db = self.get_db()
        try:
            p = db.query(Product).filter(Product.name == self.sel_p_name).first()
            if p:
                return [c.color_name for c in p.colors]
            return []
        except Exception:
            return []
        finally:
            db.close()

    @rx.var
    def cash_account_options(self) -> list[str]:
        db = self.get_db()
        try:
            accs = db.query(CompanyBalanceItem).filter(
                CompanyBalanceItem.category == 'asset',
                CompanyBalanceItem.asset_type == '现金',
                CompanyBalanceItem.currency == self.pre_curr
            ).all()
            
            names = [a.name for a in accs]
            recommended = "流动资金-支付宝账户"
            if self.pre_plat == "微店":
                recommended = "流动资金-微店账户"
            elif self.pre_plat == "Booth":
                recommended = "流动资金-booth账户"
            elif self.pre_curr != "CNY":
                if accs:
                    recommended = accs[0].name
                else:
                    recommended = f"流动资金-{self.pre_curr.lower()}临时账户"
                
            if recommended not in names:
                names.insert(0, recommended)
            return names
        except Exception:
            return []
        finally:
            db.close()

    @rx.var
    def warehouse_options(self) -> list[str]:
        db = self.get_db()
        try:
            whs = db.query(Warehouse).all()
            return [w.name for w in whs]
        except Exception:
            return []
        finally:
            db.close()

    @rx.var
    def platform_options(self) -> list[str]:
        db = self.get_db()
        try:
            from models import SalesPlatform
            return [p.name for p in db.query(SalesPlatform).all()]
        except Exception:
            return []
        finally:
            db.close()

    @rx.var
    def product_options(self) -> list[str]:
        db = self.get_db()
        try:
            prods = db.query(Product).all()
            return ["全部商品"] + [p.name for p in prods]
        except Exception:
            return ["全部商品"]
        finally:
            db.close()

    @rx.var
    def cart_item_count(self) -> int:
        return sum(c["quantity"] for c in self.pre_cart)

    @rx.var
    def cart_gross_price(self) -> float:
        return self.pre_tp

    @rx.var
    def cart_estimated_fee(self) -> float:
        if not self.pre_fee:
            return 0.0
        db = self.get_db()
        try:
            from models import SalesPlatform
            platform = db.query(SalesPlatform).filter(SalesPlatform.name == self.pre_plat).first()
            if platform:
                raw_fee = self.pre_tp * platform.fee_rate + platform.fee_fixed
                if platform.currency == "JPY" or self.pre_currency == "JPY":
                    return float(math.ceil(raw_fee))
                return round(float(raw_fee), 2)
            return 0.0
        except Exception:
            return 0.0
        finally:
            db.close()

    @rx.var
    def cart_net_price(self) -> float:
        net = self.pre_tp - self.cart_estimated_fee
        return max(0.0, net)

    # --- 绑定尾款预计收益 ---
    @rx.var
    def final_estimated_fee(self) -> float:
        if not self.pre_fee_final or not self.show_search_lock:
            return 0.0
        db = self.get_db()
        try:
            from models import SalesPlatform
            platform = db.query(SalesPlatform).filter(SalesPlatform.name == self.found_deposit_order_platform).first()
            if platform:
                raw_fee = self.final_amount_input * platform.fee_rate + platform.fee_fixed
                if platform.currency == "JPY" or self.found_deposit_order_currency == "JPY":
                    return float(math.ceil(raw_fee))
                return round(float(raw_fee), 2)
            return 0.0
        except Exception:
            return 0.0
        finally:
            db.close()

    @rx.var
    def final_net_price(self) -> float:
        net = self.final_amount_input - self.final_estimated_fee
        return max(0.0, net)

    @rx.var
    def existing_final_info(self) -> dict:
        """检查当前输入的 final_no_input 是否已绑定到其他定金单"""
        final_no = self.final_no_input.strip()
        if not final_no:
            return {"exists": False, "msg": "", "total_final": 0.0}
        db = self.get_db()
        try:
            from models import SalesOrder
            bound = db.query(SalesOrder).filter(
                SalesOrder.final_order_no == final_no,
                SalesOrder.order_type == "预售"
            ).all()
            if bound:
                dep_nos = ", ".join(o.order_no for o in bound)
                total_final = sum(o.final_amount for o in bound)
                return {
                    "exists": True,
                    "msg": f"💡 检测到尾款单【{final_no}】已绑定定金单: [{dep_nos}]。将作为合并尾款共同绑定，共享其尾款数据 (实收: ¥ {total_final:.2f})，无需重复填写尾款金额。",
                    "total_final": total_final
                }
            return {"exists": False, "msg": "", "total_final": 0.0}
        except Exception:
            return {"exists": False, "msg": "", "total_final": 0.0}
        finally:
            db.close()

    @rx.var
    def is_existing_final_no(self) -> bool:
        return bool(self.existing_final_info.get("exists", False))

    @rx.var
    def existing_final_hint(self) -> str:
        return str(self.existing_final_info.get("msg", ""))

    # --- 拆分订单计算属性 ---
    @rx.var
    def can_split_order(self) -> bool:
        """检查当前详情订单是否可以拆分：待付尾款且未绑尾款"""
        return (
            self.detail_status == OrderStatus.PRESALE_PENDING_FINAL
            and (self.detail_final_order_no == "-" or not self.detail_final_order_no)
        )

    @rx.var
    def split_selected_total_qty(self) -> int:
        return sum(it.split_qty for it in self.split_items_data)

    @rx.var
    def split_preview_new_deposit(self) -> float:
        return round(sum(it.split_qty * it.unit_deposit for it in self.split_items_data), 2)

    @rx.var
    def split_preview_remain_deposit(self) -> float:
        return max(0.0, round(self.split_orig_deposit - self.split_preview_new_deposit, 2))

    @rx.var
    def split_preview_remain_qty(self) -> int:
        return max(0, self.split_orig_total_qty - self.split_selected_total_qty)

    @rx.var
    def can_submit_split(self) -> bool:
        return 0 < self.split_selected_total_qty < self.split_orig_total_qty

    # ===================== 核心事件处理器 =====================

    @rx.event
    async def load_presale_page(self):
        if not await self.is_authenticated_user():
            return
        self.pre_date_input = date.today().isoformat()
        self.selected_order_ids = []
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            
            p_filter = None if self.selected_product_filter == "全部商品" else self.selected_product_filter
            stats = service.get_order_statistics(product_name=p_filter, order_type="预售")
            self.stat_total = stats["total"]
            self.stat_pending_deposit = stats["pending_deposit"]
            self.stat_pending_final = stats["pending_final"]
            self.stat_pending = stats["pending"]
            self.stat_shipped = stats["shipped"]
            self.stat_completed = stats["completed"]

            status_map = {
                "all": None,
                "deposit": OrderStatus.PRESALE_PENDING_DEPOSIT,
                "final": OrderStatus.PRESALE_PENDING_FINAL,
                "pending": OrderStatus.PENDING,
                "shipped": OrderStatus.SHIPPED,
                "completed": OrderStatus.COMPLETED,
                "after_sales": OrderStatus.AFTER_SALES
            }
            active_status = status_map.get(self.active_tab)
            
            orders_list = service.get_all_orders(status=active_status, product_name=p_filter, order_type="预售", limit=1000)
            rows = []
            for o in orders_list:
                item_count = len(o.items)
                items_summary = ", ".join([f"{i.product_name}-{i.variant}×{i.quantity}" for i in o.items[:2]])
                if item_count > 2:
                    items_summary += f" 等{item_count}项"

                total_refunded = sum([r.refund_amount for r in o.refunds])
                
                status_display = o.status
                if o.status == OrderStatus.PRESALE_PENDING_DEPOSIT: status_display = "🕒 待完成定金"
                elif o.status == OrderStatus.PRESALE_PENDING_FINAL: status_display = "⏳ 待付尾款"
                elif o.status == OrderStatus.PENDING: status_display = "📦 待发货"
                elif o.status == OrderStatus.SHIPPED: status_display = "🚚 已发货"
                elif o.status == OrderStatus.COMPLETED: status_display = "✅ 完成"
                elif o.status == OrderStatus.AFTER_SALES: status_display = "🔧 售后"

                all_items_str = ", ".join([f"{i.product_name} {i.variant} {i.quantity}" for i in o.items])
                rows.append(PresaleOrderRow(
                    勾选=o.id in self.selected_order_ids,
                    id=o.id,
                    order_no=o.order_no,
                    final_order_no=o.final_order_no or "-",
                    status=status_display,
                    items_summary=items_summary,
                    deposit_amount=round(float(o.deposit_amount), 2),
                    final_amount=round(float(o.final_amount), 2),
                    refunded_amount=round(float(total_refunded), 2),
                    discount_note=o.discount_note or "-",
                    currency=o.currency,
                    platform=o.platform,
                    created_date=o.created_date.strftime("%Y-%m-%d") if o.created_date else "",
                    notes=o.notes or "-",
                    search_keywords=all_items_str
                ))
            self.orders = rows
            
            prods = db.query(Product).all()
            if prods and not self.sel_p_name:
                self.sel_p_name = prods[0].name
                self.sel_v_name = prods[0].colors[0].color_name if prods[0].colors else ""
            
            self.auto_match_account()
        except Exception as e:
            print(f"Error loading presale: {e}")
        finally:
            db.close()

    @rx.event
    def select_tab(self, tab_name: str):
        self.active_tab = tab_name
        self.selected_order_ids = []
        self.page_index = 1
        yield PresaleState.load_presale_page()

    @rx.event
    def select_product_filter(self, val: str):
        self.selected_product_filter = val
        self.selected_order_ids = []
        self.page_index = 1
        yield PresaleState.load_presale_page()

    @rx.event
    def set_search_query(self, val: str):
        self.search_query = val
        self.page_index = 1

    @rx.event
    def prev_page(self):
        if self.page_index > 1:
            self.page_index -= 1

    @rx.event
    def next_page(self):
        if self.page_index < self.total_pages:
            self.page_index += 1

    @rx.event
    def set_create_mode(self, val: str): self.create_mode = val
    @rx.event
    def select_p_name(self, val: str):
        self.sel_p_name = val
        db = self.get_db()
        try:
            p = db.query(Product).filter(Product.name == val).first()
            if p and p.colors:
                self.sel_v_name = p.colors[0].color_name
            else:
                self.sel_v_name = ""
        except Exception:
            pass
        finally:
            db.close()

    # --- 建单字段 Setters ---
    @rx.event
    def set_pre_order_no(self, val: str): self.pre_order_no = val
    @rx.event
    def set_pre_date_input(self, val: str): self.pre_date_input = val
    @rx.event
    def set_pre_plat(self, val: str):
        self.pre_plat = val
        db = self.get_db()
        try:
            from models import SalesPlatform
            platform = db.query(SalesPlatform).filter(SalesPlatform.name == val).first()
            if platform:
                self.pre_curr = platform.currency
        except Exception:
            pass
        finally:
            db.close()
        self.auto_match_account()
        
    @rx.event
    def set_pre_curr(self, val: str):
        self.pre_curr = val
        self.auto_match_account()

    @rx.event
    def set_pre_target_account(self, val: str): self.pre_target_account = val
    @rx.event
    def set_pre_tp(self, val: str):
        try:
            self.pre_tp = float(val) if val else 0.0
        except ValueError:
            self.pre_tp = 0.0
            
    @rx.event
    def toggle_pre_fee(self, val: bool): self.pre_fee = val
    @rx.event
    def set_pre_discount(self, val: str): self.pre_discount = val
    @rx.event
    def set_pre_notes(self, val: str): self.pre_notes = val

    # --- 购物车暂存 Setter ---
    @rx.event
    def set_sel_v_name(self, val: str): self.sel_v_name = val
    @rx.event
    def set_sel_qty(self, val: str):
        try:
            self.sel_qty = int(val) if val else 1
            if self.sel_qty < 1:
                self.sel_qty = 1
        except ValueError:
            self.sel_qty = 1
    @rx.event
    def set_sel_wh_name(self, val: str): self.sel_wh_name = val

    def auto_match_account(self):
        recommended = "流动资金-支付宝账户"
        if self.pre_plat == "微店":
            recommended = "流动资金-微店账户"
        elif self.pre_plat == "Booth":
            recommended = "流动资金-booth账户"
        elif self.pre_curr != "CNY":
            db = self.get_db()
            try:
                acc = db.query(CompanyBalanceItem).filter(
                    CompanyBalanceItem.category == 'asset',
                    CompanyBalanceItem.asset_type == '现金',
                    CompanyBalanceItem.currency == self.pre_curr
                ).first()
                if acc:
                    recommended = acc.name
                else:
                    recommended = f"流动资金-{self.pre_curr.lower()}临时账户"
            except Exception:
                recommended = f"流动资金-{self.pre_curr.lower()}临时账户"
            finally:
                db.close()
        self.pre_target_account = recommended

    # --- 购物车操作 ---
    @rx.event
    def add_to_pre_cart(self):
        if not self.sel_p_name or not self.sel_v_name:
            return rx.toast("请选择商品及款式", level="error")
        if not self.sel_wh_name or self.sel_wh_name == "未分配":
            return rx.toast("请选择具体的出货仓库", level="error")
        
        db = self.get_db()
        try:
            wh = db.query(Warehouse).filter(Warehouse.name == self.sel_wh_name).first()
            wh_id = wh.id if wh else None
            
            found = False
            for c in self.pre_cart:
                if c["product_name"] == self.sel_p_name and c["variant"] == self.sel_v_name and c["warehouse_name"] == self.sel_wh_name:
                    c["quantity"] += self.sel_qty
                    found = True
                    break
            
            if not found:
                self.pre_cart.append({
                    "key": f"pre_cart_{len(self.pre_cart)}_{date.today().strftime('%H%M%S')}",
                    "product_name": self.sel_p_name,
                    "variant": self.sel_v_name,
                    "quantity": self.sel_qty,
                    "warehouse_id": wh_id,
                    "warehouse_name": self.sel_wh_name
                })
            self.pre_cart = list(self.pre_cart)
            return rx.toast(f"成功将 {self.sel_p_name}-{self.sel_v_name} ×{self.sel_qty} 加入定金商品表")
        finally:
            db.close()

    @rx.event
    def remove_from_pre_cart(self, cart_key: str):
        self.pre_cart = [c for c in self.pre_cart if c["key"] != cart_key]

    @rx.event
    def clear_pre_cart(self):
        self.pre_cart = []

    @rx.event
    def submit_presale_deposit(self):
        """手动定金建单。"""
        if not self.pre_order_no.strip():
            yield rx.toast("定金单号不能为空！", level="error")
            return
        if not self.pre_cart:
            yield rx.toast("定金商品明细不能为空！", level="error")
            return
        if self.pre_tp <= 0:
            yield rx.toast("定金总价必须大于 0！", level="error")
            return
            
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            
            # Check duplicate order no
            existing = db.query(SalesOrder).filter(SalesOrder.order_no == self.pre_order_no.strip()).first()
            if existing:
                yield rx.toast(f"订单号 {self.pre_order_no} 已存在，请勿重复输入", level="error")
                return

            items_data = []
            net_price = self.cart_net_price
            unit_price = net_price / sum(x["quantity"] for x in self.pre_cart)
            
            for item in self.pre_cart:
                items_data.append({
                    "product_name": item["product_name"],
                    "variant": item["variant"],
                    "quantity": item["quantity"],
                    "unit_price": unit_price,
                    "warehouse_id": item["warehouse_id"]
                })

            order_date = None
            if self.pre_date_input:
                try:
                    order_date = date.fromisoformat(self.pre_date_input)
                except ValueError:
                    pass

            order, err = service.create_presale_deposit_order(
                items_data=items_data,
                platform=self.pre_plat,
                currency=self.pre_curr,
                notes=self.pre_notes,
                order_date=order_date,
                order_no=self.pre_order_no.strip(),
                target_account_name=self.pre_target_account,
                discount_note=self.pre_discount
            )
            
            if err:
                yield rx.toast(f"定金单创建失败: {err}", level="error")
                return
                
            self.pre_cart = []
            self.pre_order_no = ""
            self.pre_notes = ""
            self.pre_discount = ""
            self.pre_tp = 0.0
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast("✅ 预售定金订单创建成功！状态为【待完成定金】")
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"系统错误: {e}", level="error")
            return
        finally:
            db.close()

    # ===================== 2️⃣ 绑定尾款精确查找与绑定 =====================

    @rx.event
    def set_search_dep_no(self, val: str): self.search_dep_no = val
    @rx.event
    def set_final_no_input(self, val: str): self.final_no_input = val
    @rx.event
    def set_final_amount_input(self, val: str):
        try:
            self.final_amount_input = float(val) if val else 0.0
        except ValueError:
            self.final_amount_input = 0.0
            
    @rx.event
    def toggle_pre_fee_final(self, val: bool): self.pre_fee_final = val
    @rx.event
    def set_f_notes(self, val: str): self.f_notes = val

    @rx.event
    def search_deposit_order(self):
        if not self.search_dep_no.strip():
            return rx.toast("请输入原始定金单号！", level="error")
            
        self.show_search_lock = False
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            o = service.get_order_by_no(self.search_dep_no.strip())
            
            if not o:
                return rx.toast(f"❌ 未在预售单据中搜到定金单号: {self.search_dep_no}", level="error")
            elif o.status != OrderStatus.PRESALE_PENDING_FINAL:
                return rx.toast(f"⚠️ 定金单已锁定，但其当前状态为【{o.status}】，不是【待付尾款】。仅此阶段定金单可进行尾款绑定！", level="warning")
            else:
                self.found_deposit_order_id = o.id
                self.found_deposit_order_no = o.order_no
                self.found_deposit_order_date = o.created_date.strftime("%Y-%m-%d") if o.created_date else ""
                self.found_deposit_order_platform = o.platform
                self.found_deposit_order_currency = o.currency
                
                items = []
                for item in o.items:
                    items.append({
                        "product_name": item.product_name,
                        "variant": item.variant,
                        "quantity": item.quantity
                    })
                self.found_deposit_order_items = items
                self.show_search_lock = True
                
                # Reset binding fields
                self.final_no_input = ""
                self.final_amount_input = 0.0
                self.f_notes = ""
                
                return rx.toast("✅ 定金单锁定成功！请在下方输入对应尾款信息绑定")
        finally:
            db.close()

    @rx.event
    def submit_bind_final(self):
        if not self.show_search_lock:
            yield rx.toast("请先锁定有效的定金订单！", level="error")
            return
        if not self.final_no_input.strip():
            yield rx.toast("请输入尾款订单号！", level="error")
            return
        if not self.is_existing_final_no and self.final_amount_input < 0:
            yield rx.toast("尾款实收金额不能小于 0！", level="error")
            return
            
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            
            net_amt = 0.0 if self.is_existing_final_no else self.final_net_price
            
            msg = service.bind_presale_final_order(
                deposit_order_ids=self.found_deposit_order_id,
                final_order_no=self.final_no_input.strip(),
                final_net_amount=net_amt,
                new_notes=self.f_notes
            )
            
            self.show_search_lock = False
            self.search_dep_no = ""
            self.final_no_input = ""
            self.final_amount_input = 0.0
            self.f_notes = ""
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(msg, level="success")
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"绑定尾款失败: {e}", level="error")
            return
        finally:
            db.close()

    # ===================== Excel 批量导入 =====================

    @rx.event
    def set_bulk_presale_mode(self, val: str): self.bulk_presale_mode = val

    @rx.event
    async def handle_excel_import(self, files: list[rx.UploadFile]):
        if not files:
            return
        
        self.excel_import_errors = []
        self.parsed_preview_orders = []
        
        file = files[0]
        data = await file.read()
        
        pm_mode = "定金" if "定金" in self.bulk_presale_mode else "尾款"
        
        db = self.get_db()
        try:
            df = pd.read_excel(io.BytesIO(data))
            service = SalesOrderService(db)
            
            parsed, errors = service.validate_and_parse_import_data(df, self.exchange_rate, presale_mode=pm_mode)
            if errors:
                if isinstance(errors, list):
                    self.excel_import_errors = errors
                else:
                    self.excel_import_errors = [str(errors)]
                return rx.toast(f"Excel 预售{pm_mode}校验失败！请点击查看异常行", level="error")
            
            if parsed:
                wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}
                
                preview_list = []
                for p in parsed:
                    # Construct matching warehouse detail string
                    items_str = ", ".join([f"{i['product_name']}-{i['variant']} ×{i['quantity']} (仓: {wh_dict.get(i['warehouse_id'], '未分配')})" for i in p["items"]])
                    
                    preview_list.append({
                        "stock_warning": "🟢 待导入定金" if pm_mode == "定金" else "🔗 匹配成功(待绑尾发货)",
                        "order_no": p["order_no"],
                        "platform": p["platform"],
                        "target_account": p["target_account"],
                        "currency": p["currency"],
                        "total_qty": p["total_qty"],
                        "gross_price": float(p["gross_price"]),
                        "fee": float(p["fee"]),
                        "net_price": float(p["net_price"]),
                        "items_str": items_str,
                        "matched_deposit_id": p.get("matched_deposit_id") or 0,
                        "matched_deposit_ids": p.get("matched_deposit_ids") or ([p.get("matched_deposit_id")] if p.get("matched_deposit_id") else []),
                        "discount_note": p.get("discount_note") or "-",
                        "items": p.get("items", [])
                    })
                self.parsed_preview_orders = preview_list
                return rx.toast(f"✅ Excel 校验成功！识别到 {len(preview_list)} 个预售{pm_mode}记录，请核对后开始批量写入")
        except Exception as e:
            self.excel_import_errors = [f"解析底层崩溃: {e}"]
            return rx.toast("文件解析失败，请使用预定义列名模版", level="error")
        finally:
            db.close()

    @rx.event
    def submit_batch_import(self):
        if not self.parsed_preview_orders:
            yield rx.toast("无可执行导入的数据", level="error")
            return
            
        pm_mode = "定金" if "定金" in self.bulk_presale_mode else "尾款"
        
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            count = service.batch_create_orders(self.parsed_preview_orders, presale_mode=pm_mode)
            
            self.parsed_preview_orders = []
            self.excel_import_errors = []
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(f"成功批量{'生成' if pm_mode=='定金' else '绑定'} {count} 个预售单据！", level="success")
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"写入出错: {e}", level="error")
            return
        finally:
            db.close()

    # ===================== 表格多选与批量动作 =====================

    @rx.event
    def toggle_order_select(self, order_id: int):
        order_id = int(order_id)
        if order_id in self.selected_order_ids:
            self.selected_order_ids.remove(order_id)
        else:
            self.selected_order_ids.append(order_id)
            
        for o in self.orders:
            if o.id == order_id:
                o.勾选 = order_id in self.selected_order_ids
        self.orders = list(self.orders)

    @rx.event
    def toggle_select_all(self):
        if self.is_select_all:
            self.selected_order_ids = []
            for o in self.orders:
                o.勾选 = False
        else:
            self.selected_order_ids = [o.id for o in self.orders]
            for o in self.orders:
                o.勾选 = True
        self.orders = list(self.orders)

    @rx.event
    def complete_selected_deposits(self):
        """批量确认定金收款。"""
        if not self.selected_order_ids:
            yield rx.toast("未勾选任何订单！", level="error")
            return
            
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            success, errors = service.batch_complete_deposit_orders(self.selected_order_ids)
            
            self.selected_order_ids = []
            if errors:
                for err in errors[:5]:
                    yield rx.toast(err, level="error")
                if len(errors) > 5:
                    yield rx.toast(f"另有 {len(errors) - 5} 个定金单处理失败", level="warning")
            if success > 0:
                yield rx.toast(f"🕒 批量定金确认完成！已处理 {success} 个定金单")
            yield PresaleState.load_presale_page()
        finally:
            db.close()

    @rx.event
    def ship_selected_orders(self):
        if not self.selected_order_ids:
            yield rx.toast("未勾选任何订单！", level="error")
            return
            
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            success, errors = service.batch_ship_orders(self.selected_order_ids)
            
            self.selected_order_ids = []
            if errors:
                for err in errors[:5]:
                    yield rx.toast(err, level="error")
                if len(errors) > 5:
                    yield rx.toast(f"另有 {len(errors) - 5} 个单据处理失败", level="warning")
            if success > 0:
                yield rx.toast(f"📦 批量定金订单发货完成！成功发货 {success} 个单据")
            yield PresaleState.load_presale_page()
        finally:
            db.close()

    @rx.event
    def complete_selected_orders(self):
        if not self.selected_order_ids:
            yield rx.toast("未勾选任何订单！", level="error")
            return
            
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            success, errors = service.batch_complete_orders(self.selected_order_ids)
            
            self.selected_order_ids = []
            if errors:
                for err in errors[:5]:
                    yield rx.toast(err, level="error")
                if len(errors) > 5:
                    yield rx.toast(f"另有 {len(errors) - 5} 个单据处理失败", level="warning")
            if success > 0:
                yield rx.toast(f"✅ 批量预售结清完成！已结清 {success} 个单据")
            yield PresaleState.load_presale_page()
        finally:
            db.close()

    @rx.event
    def set_show_batch_wh_modal(self, val: bool):
        self.show_batch_wh_modal = val

    @rx.event
    def set_batch_target_wh_name(self, val: str):
        self.batch_target_wh_name = val

    @rx.event
    def open_batch_wh_modal(self):
        if not self.selected_order_ids:
            return rx.toast("未勾选任何订单！", level="error")
        opts = self.warehouse_options
        if opts and not self.batch_target_wh_name:
            self.batch_target_wh_name = opts[0]
        self.show_batch_wh_modal = True

    @rx.event
    def close_batch_wh_modal(self):
        self.show_batch_wh_modal = False

    @rx.event
    def submit_batch_update_warehouse(self):
        if not self.selected_order_ids:
            yield rx.toast("未勾选任何订单！", level="error")
            return
        if not self.batch_target_wh_name:
            yield rx.toast("请选择目标发货仓库！", level="error")
            return
        
        db = self.get_db()
        try:
            wh = db.query(Warehouse).filter(Warehouse.name == self.batch_target_wh_name).first()
            if not wh:
                yield rx.toast(f"找不到仓库 '{self.batch_target_wh_name}'", level="error")
                return
            
            service = SalesOrderService(db)
            count, wh_name = service.batch_update_warehouse(self.selected_order_ids, wh.id)
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            self.show_batch_wh_modal = False
            self.selected_order_ids = []
            yield rx.toast(f"🏭 成功将 {count} 个订单的发货仓库批量修改为【{wh_name}】！")
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"批量修改发货仓库失败: {e}", level="error")
        finally:
            db.close()

    # ===================== 查看详情与解绑/删除 =====================

    @rx.event
    def open_order_detail(self, order_id: int):
        self.active_detail_order_id = int(order_id)
        self.show_detail_flag = True
        self.show_delete_confirm = False
        
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            o = service.get_order_by_id(self.active_detail_order_id)
            if not o:
                self.show_detail_flag = False
                return rx.toast("单据不存在！", level="error")
                
            self.detail_order_no = o.order_no
            self.detail_final_order_no = o.final_order_no or "-"
            self.detail_status = o.status
            self.detail_platform = o.platform
            self.detail_currency = o.currency
            self.detail_created_date = o.created_date.strftime("%Y-%m-%d") if o.created_date else ""
            self.detail_shipped_date = o.shipped_date.strftime("%Y-%m-%d") if o.shipped_date else "未发货"
            self.detail_completed_date = o.completed_date.strftime("%Y-%m-%d") if o.completed_date else "未完成"
            self.detail_target_account = o.target_account_name or "系统默认"
            self.detail_notes = o.notes or "无"
            self.detail_discount_note = getattr(o, "discount_note", "") or ""
            
            # Edit fields
            self.edit_discount_note = self.detail_discount_note
            self.edit_notes = self.detail_notes
            
            wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}
            
            items_list = []
            for i in o.items:
                items_list.append({
                    "product_name": i.product_name,
                    "variant": i.variant,
                    "warehouse_name": wh_dict.get(i.warehouse_id, "未分配"),
                    "quantity": i.quantity,
                    "subtotal": round(float(i.subtotal), 2)
                })
            self.detail_items = items_list
            self.detail_deposit_amount = round(float(o.deposit_amount), 2)
            self.detail_final_amount = round(float(o.final_amount), 2)
            self.detail_total_amount = round(float(o.total_amount), 2)
        finally:
            db.close()

    @rx.event
    def set_edit_discount_note(self, val: str): self.edit_discount_note = val
    @rx.event
    def set_edit_notes(self, val: str): self.edit_notes = val

    @rx.event
    def submit_update_notes(self):
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            service.update_order_info(self.active_detail_order_id, {
                "discount_note": self.edit_discount_note,
                "notes": self.edit_notes
            })
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast("预售订单优惠及备注修改成功！")
            yield PresaleState.open_order_detail(self.active_detail_order_id)
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"保存修改失败: {e}", level="error")
            return
        finally:
            db.close()

    @rx.event
    def unbind_presale_final(self):
        """一键解绑物理剥离尾款。"""
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            msg = service.unbind_presale_final(self.active_detail_order_id)
            
            self.show_detail_flag = False
            self.selected_order_ids = []
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(msg, level="success")
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"解绑尾款失败: {e}", level="error")
            return
        finally:
            db.close()

    @rx.event
    def open_delete_confirm(self): self.show_delete_confirm = True
    @rx.event
    def cancel_delete_confirm(self): self.show_delete_confirm = False

    @rx.event
    def set_show_detail_flag(self, val: bool):
        self.show_detail_flag = val

    @rx.event
    def set_show_refund_form(self, val: bool):
        self.show_refund_form = val

    @rx.event
    def submit_delete_order(self):
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            msg = service.delete_order(self.active_detail_order_id)
            
            self.show_detail_flag = False
            self.show_delete_confirm = False
            self.selected_order_ids = []
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(msg)
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"物理删除失败: {e}", level="error")
            return
        finally:
            db.close()

    # ===================== 售后 Dialog 与物理联动 =====================

    @rx.event
    def open_refund_dialog(self, order_id: int):
        self.active_refund_order_id = int(order_id)
        self.show_refund_form = True
        
        self.ref_amount_input = 0.0
        self.ref_reason_input = ""
        self.ref_is_returned = False
        self.ref_is_resend = False
        self.ref_returned_items = []
        self.ref_resend_items = []
        self.editing_refund_id = 0
        
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            o = service.get_order_by_id(self.active_refund_order_id)
            if not o:
                self.show_refund_form = False
                return rx.toast("单据不存在", level="error")
                
            # Load existing refunds
            ref_list = []
            for r in o.refunds:
                ref_list.append({
                    "id": r.id,
                    "refund_date": r.refund_date.strftime("%Y-%m-%d") if r.refund_date else "",
                    "refund_reason": r.refund_reason,
                    "refund_amount": round(float(r.refund_amount), 2),
                    "is_returned": r.is_returned,
                    "is_resend": getattr(r, "is_resend", False),
                    "is_editing": False
                })
            self.existing_refunds = ref_list

            ret_items = []
            res_items = []
            
            wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}
            all_prods = db.query(Product).all()
            
            for item in o.items:
                wh_name = wh_dict.get(item.warehouse_id, "未分配")
                ret_items.append({
                    "order_item_id": item.id,
                    "product_name": item.product_name,
                    "variant": item.variant,
                    "max_quantity": item.quantity,
                    "quantity": 0,
                    "warehouse_id": item.warehouse_id or 0,
                    "warehouse_name": wh_name
                })
                
                p_obj = next((p for p in all_prods if p.name == item.product_name), None)
                color_obj = next((c for c in p_obj.colors if c.color_name == item.variant), None) if p_obj else None
                part_opts = ["整套"]
                if color_obj and color_obj.parts:
                    for pt in color_obj.parts:
                        part_opts.append(pt.part_name)
                        
                res_items.append(ResendItemModel(
                    order_item_id=item.id,
                    product_name=item.product_name,
                    variant=item.variant,
                    quantity=0,
                    warehouse_id=item.warehouse_id or 0,
                    warehouse_name=wh_name,
                    part_name="整套",
                    part_options=part_opts
                ))
            self.ref_returned_items = ret_items
            self.ref_resend_items = res_items
        finally:
            db.close()

    # --- 新售后表单 Setters ---
    @rx.event
    def set_ref_amount_input(self, val: str):
        try:
            self.ref_amount_input = float(val) if val else 0.0
        except ValueError:
            self.ref_amount_input = 0.0
            
    @rx.event
    def set_ref_reason_input(self, val: str): self.ref_reason_input = val
    @rx.event
    def toggle_ref_is_returned(self, val: bool): self.ref_is_returned = val
    @rx.event
    def toggle_ref_is_resend(self, val: bool): self.ref_is_resend = val

    @rx.event
    def update_returned_qty(self, item_id: int, val: str):
        item_id = int(item_id)
        try:
            qty = int(val) if val else 0
            for item in self.ref_returned_items:
                if item["order_item_id"] == item_id:
                    if qty > item["max_quantity"]:
                        qty = item["max_quantity"]
                    item["quantity"] = qty
                    break
        except ValueError:
            pass
        self.ref_returned_items = list(self.ref_returned_items)

    @rx.event
    def update_resend_qty(self, item_id: int, val: str):
        item_id = int(item_id)
        try:
            qty = int(val) if val else 0
            for item in self.ref_resend_items:
                if item.order_item_id == item_id:
                    item.quantity = qty
                    break
        except ValueError:
            pass
        self.ref_resend_items = list(self.ref_resend_items)

    @rx.event
    def update_resend_part(self, item_id: int, part: str):
        item_id = int(item_id)
        for item in self.ref_resend_items:
            if item.order_item_id == item_id:
                item.part_name = part
                break
        self.ref_resend_items = list(self.ref_resend_items)

    @rx.event
    def update_resend_warehouse(self, item_id: int, wh_name: str):
        item_id = int(item_id)
        db = self.get_db()
        try:
            wh = db.query(Warehouse).filter(Warehouse.name == wh_name).first()
            wh_id = wh.id if wh else 0
            for item in self.ref_resend_items:
                if item.order_item_id == item_id:
                    item.warehouse_id = wh_id
                    item.warehouse_name = wh_name
                    break
            self.ref_resend_items = list(self.ref_resend_items)
        finally:
            db.close()

    @rx.event
    def submit_add_refund(self):
        if self.ref_amount_input < 0:
            yield rx.toast("售后退款金额不能小于 0！", level="error")
            return
        if not self.ref_reason_input.strip():
            yield rx.toast("请输入售后审计原因！", level="error")
            return
            
        returned_list = []
        if self.ref_is_returned:
            for item in self.ref_returned_items:
                if item["quantity"] > 0:
                    returned_list.append({
                        "product_name": item["product_name"],
                        "variant": item["variant"],
                        "quantity": item["quantity"],
                        "warehouse_id": item["warehouse_id"] if item["warehouse_id"] > 0 else None
                    })
                    
        resend_list = []
        if self.ref_is_resend:
            for item in self.ref_resend_items:
                if item.quantity > 0:
                    resend_list.append({
                        "product_name": item.product_name,
                        "variant": item.variant,
                        "quantity": item.quantity,
                        "warehouse_id": item.warehouse_id if item.warehouse_id > 0 else None,
                        "part_name": None if item.part_name == "整套" else item.part_name
                    })
                    
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            
            returned_quantity = sum(x["quantity"] for x in returned_list) if self.ref_is_returned else 0
            resend_quantity = sum(x["quantity"] for x in resend_list) if self.ref_is_resend else 0
            
            msg = service.add_refund(
                order_id=self.active_refund_order_id,
                refund_amount=self.ref_amount_input,
                refund_reason=self.ref_reason_input.strip(),
                is_returned=self.ref_is_returned,
                returned_quantity=returned_quantity,
                returned_items=returned_list if self.ref_is_returned else None,
                exchange_rate=self.exchange_rate,
                is_resend=self.ref_is_resend,
                resend_quantity=resend_quantity,
                resend_items=resend_list if self.ref_is_resend else None
            )
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(msg)
            yield PresaleState.open_refund_dialog(self.active_refund_order_id)
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"售后提交失败: {e}", level="error")
            return
        finally:
            db.close()

    # --- 编辑/删除售后子操作 ---
    @rx.event
    def start_edit_refund(self, refund_id: int):
        self.editing_refund_id = int(refund_id)
        for r in self.existing_refunds:
            if r["id"] == self.editing_refund_id:
                r["is_editing"] = True
                self.editing_refund_amount = r["refund_amount"]
                self.editing_refund_reason = r["refund_reason"]
            else:
                r["is_editing"] = False
        self.existing_refunds = list(self.existing_refunds)

    @rx.event
    def cancel_edit_refund(self):
        self.editing_refund_id = 0
        for r in self.existing_refunds:
            r["is_editing"] = False
        self.existing_refunds = list(self.existing_refunds)

    @rx.event
    def set_editing_refund_amount(self, val: str):
        try:
            self.editing_refund_amount = float(val) if val else 0.0
        except ValueError:
            self.editing_refund_amount = 0.0
            
    @rx.event
    def set_editing_refund_reason(self, val: str): self.editing_refund_reason = val

    @rx.event
    def submit_edit_refund(self):
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            msg = service.update_refund(
                refund_id=self.editing_refund_id,
                refund_amount=self.editing_refund_amount,
                refund_reason=self.editing_refund_reason,
                exchange_rate=self.exchange_rate
            )
            self.editing_refund_id = 0
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(msg)
            yield PresaleState.open_refund_dialog(self.active_refund_order_id)
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"修改失败: {e}", level="error")
            return
        finally:
            db.close()

    @rx.event
    def submit_delete_refund(self, refund_id: int):
        refund_id = int(refund_id)
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            msg = service.delete_refund(refund_id)
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(msg)
            yield PresaleState.open_refund_dialog(self.active_refund_order_id)
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"撤销失败: {e}", level="error")
            return
        finally:
            db.close()

    # ===================== 拆分定金订单事件 =====================
    @rx.event
    def open_split_modal(self):
        if not self.active_detail_order_id:
            return
        db = self.get_db()
        try:
            from models import SalesOrder, Warehouse
            order = db.query(SalesOrder).filter(SalesOrder.id == self.active_detail_order_id).first()
            if not order:
                return rx.toast("订单不存在", level="error")
            if order.status != OrderStatus.PRESALE_PENDING_FINAL or order.final_order_no:
                return rx.toast("仅待付尾款且尚未绑定尾款的定金单支持拆分！", level="warning")

            self.split_target_order_id = order.id
            self.split_base_order_no = order.order_no
            self.split_orig_deposit = float(order.deposit_amount)
            self.split_orig_total_qty = sum(it.quantity for it in order.items)

            # 探测下一个子单号
            import re
            existing_splits = db.query(SalesOrder.order_no).filter(
                SalesOrder.order_no.like(f"{order.order_no}-%")
            ).all()
            max_idx = 0
            pattern = re.compile(rf"^{re.escape(order.order_no)}-(\d+)$")
            for (ex_no,) in existing_splits:
                m = pattern.match(ex_no)
                if m:
                    max_idx = max(max_idx, int(m.group(1)))
            self.split_next_order_no = f"{order.order_no}-{max_idx + 1}"

            # 组装 items
            wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}
            items_list = []
            for it in order.items:
                u_dep = it.subtotal / it.quantity if it.quantity > 0 else 0.0
                items_list.append(SplitItemModel(
                    item_id=it.id,
                    product_name=it.product_name,
                    variant=it.variant,
                    warehouse_name=wh_dict.get(it.warehouse_id, "未分配仓"),
                    max_qty=it.quantity,
                    split_qty=0,
                    unit_deposit=round(u_dep, 2)
                ))
            self.split_items_data = items_list
            self.show_split_modal = True
        finally:
            db.close()

    @rx.event
    def close_split_modal(self):
        self.show_split_modal = False

    @rx.event
    def set_split_item_qty(self, item_id: int, val: str):
        try:
            qty = int(val) if val else 0
        except ValueError:
            qty = 0
        
        new_list = []
        for it in self.split_items_data:
            if it.item_id == item_id:
                clamped_qty = max(0, min(qty, it.max_qty))
                it_copy = it.model_copy(update={"split_qty": clamped_qty})
                new_list.append(it_copy)
            else:
                new_list.append(it)
        self.split_items_data = new_list

    @rx.event
    def toggle_split_all_of_item(self, item_id: int):
        new_list = []
        for it in self.split_items_data:
            if it.item_id == item_id:
                new_qty = 0 if it.split_qty > 0 else it.max_qty
                it_copy = it.model_copy(update={"split_qty": new_qty})
                new_list.append(it_copy)
            else:
                new_list.append(it)
        self.split_items_data = new_list

    @rx.event
    def submit_split_presale_order(self):
        if not self.can_submit_split:
            yield rx.toast("请选择要拆出的商品项，且必须为原单保留至少 1 件商品", level="error")
            return

        db = self.get_db()
        try:
            service = SalesOrderService(db)
            split_payload = [
                {"item_id": it.item_id, "split_quantity": it.split_qty}
                for it in self.split_items_data
                if it.split_qty > 0
            ]
            new_ord, msg = service.split_presale_deposit_order(self.split_target_order_id, split_payload)
            
            self.show_split_modal = False
            self.show_detail_flag = False
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(msg, level="success")
            yield PresaleState.load_presale_page()
        except Exception as e:
            yield rx.toast(f"拆分失败: {e}", level="error")
            return
        finally:
            db.close()
