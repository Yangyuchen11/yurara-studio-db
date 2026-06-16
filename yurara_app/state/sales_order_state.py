# yurara_app/state/sales_order_state.py
"""
线上销售管理 State 模块。
负责购物车建单、超卖盘点预警、Excel 批量导入解析预览、批量发货/完成流转、以及 Dialog 式售后详细物理联动。
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


class SalesOrderItemModel(BaseModel):
    product_name: str = ""
    variant: str = ""
    quantity: int = 1
    warehouse_id: int | None = None
    warehouse_name: str = "未分配"
    unit_price: float = 0.0
    subtotal: float = 0.0


class SalesOrderRefundModel(BaseModel):
    id: int = 0
    refund_amount: float = 0.0
    refund_reason: str = ""
    refund_date: str = ""
    is_returned: bool = False
    returned_quantity: int = 0
    is_resend: bool = False
    resend_quantity: int = 0


class ResendItemModel(BaseModel):
    order_item_id: int = 0
    product_name: str = ""
    variant: str = ""
    quantity: int = 0
    warehouse_id: int = 0
    warehouse_name: str = ""
    part_name: str = "整套"
    part_options: list[str] = []


class SalesOrderRow(BaseModel):
    勾选: bool = False
    id: int = 0
    order_no: str = ""
    status: str = ""
    items_summary: str = ""
    total_amount: float = 0.0
    refunded_amount: float = 0.0
    currency: str = "CNY"
    platform: str = ""
    created_date: str = ""
    notes: str = ""


class SalesOrderState(AppState):
    # --- 页面状态 ---
    active_tab: str = "all"  # "all", "pending", "shipped", "completed", "after_sales"
    orders: list[SalesOrderRow] = []
    selected_order_ids: list[int] = []
    selected_product_filter: str = "全部商品"
    is_loading: bool = False
    search_query: str = ""
    page_index: int = 1
    page_size: int = 50

    # --- 统计指标 ---
    stat_total: int = 0
    stat_pending: int = 0
    stat_shipped: int = 0
    stat_completed: int = 0
    stat_after_sales: int = 0

    # ===================== 手动建单表单状态 =====================
    order_no_input: str = ""
    order_date_input: str = ""  # Will be initialized to current date
    platform_input: str = "微店"
    currency_input: str = "CNY"
    target_account_input: str = ""
    total_price_input: float = 0.0
    deduct_fee_input: bool = True
    notes_input: str = ""
    order_cart: list[dict] = []  # dict keys: key, product_name, variant, quantity, warehouse_id, warehouse_name

    # --- 购物车暂存添加项 ---
    sel_p_name: str = ""
    sel_v_name: str = ""
    sel_qty: int = 1
    sel_wh_name: str = "未分配"

    # ===================== Excel 批量导入状态 =====================
    parsed_preview_orders: list[dict] = []  # dict keys: is_out_of_stock, stock_warning, order_no, platform, target_account, currency, total_qty, gross_price, fee, net_price, items_str, items
    excel_import_errors: list[str] = []
    any_out_of_stock: bool = False

    # ===================== 单个订单操作与详情 =====================
    active_detail_order_id: int = 0
    show_detail_flag: bool = False
    
    detail_order_no: str = ""
    detail_status: str = ""
    detail_platform: str = ""
    detail_currency: str = ""
    detail_created_date: str = ""
    detail_shipped_date: str = ""
    detail_completed_date: str = ""
    detail_target_account: str = ""
    detail_notes: str = ""
    detail_discount_note: str = ""
    detail_items: list[dict] = []  # dict keys: product_name, variant, warehouse_name, quantity, unit_price, subtotal
    detail_total_amount: float = 0.0

    # --- 编辑订单信息表单 ---
    edit_discount_note: str = ""
    edit_notes: str = ""
    
    # --- 删除订单二次确认 ---
    show_delete_confirm: bool = False

    # ===================== 售后 Dialog 状态 =====================
    active_refund_order_id: int = 0
    show_refund_form: bool = False
    
    # --- 已有关联售后列表 ---
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
        return all(s == "🚚 已发货" for s in statuses)

    @rx.var
    def can_refund(self) -> bool:
        if self.selected_count != 1:
            return False
        statuses = self.selected_orders_statuses
        if not statuses:
            return False
        return statuses[0] in ["🚚 已发货", "✅ 完成", "🔧 售后"]

    @rx.var
    def filtered_orders(self) -> list[SalesOrderRow]:
        query = self.search_query.strip().lower()
        if not query:
            return self.orders
        res = []
        for o in self.orders:
            if (query in o.order_no.lower() or 
                query in o.platform.lower() or 
                query in o.notes.lower() or 
                query in o.items_summary.lower() or 
                query in o.created_date.lower() or 
                query in o.status.lower()):
                res.append(o)
        return res

    @rx.var
    def paginated_orders(self) -> list[SalesOrderRow]:
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
    def is_single_selected(self) -> bool:
        return self.selected_count == 1

    @rx.var
    def single_selected_id(self) -> int:
        return self.selected_order_ids[0] if self.is_single_selected else 0

    @rx.var
    def selected_amount_sum(self) -> float:
        return sum(o.total_amount for o in self.orders if o.勾选)

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
                CompanyBalanceItem.currency == self.currency_input
            ).all()
            
            names = [a.name for a in accs]
            
            # Formulate recommended accounts
            recommended = "流动资金-支付宝账户"
            if self.platform_input == "微店":
                recommended = "流动资金-微店账户"
            elif self.platform_input == "Booth":
                recommended = "流动资金-booth账户"
            elif self.currency_input != "CNY":
                if accs:
                    recommended = accs[0].name
                else:
                    recommended = f"流动资金-{self.currency_input.lower()}临时账户"
                
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
            return [w.name for w in whs] + ["未分配"]
        except Exception:
            return ["未分配"]
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
        return sum(c["quantity"] for c in self.order_cart)

    @rx.var
    def cart_gross_price(self) -> float:
        return self.total_price_input

    @rx.var
    def cart_estimated_fee(self) -> float:
        if not self.deduct_fee_input:
            return 0.0
        db = self.get_db()
        try:
            from models import SalesPlatform
            platform = db.query(SalesPlatform).filter(SalesPlatform.name == self.platform_input).first()
            if platform:
                return math.ceil(self.total_price_input * platform.fee_rate) + platform.fee_fixed
            return 0.0
        except Exception:
            return 0.0
        finally:
            db.close()

    @rx.var
    def cart_booth_shipping_peel(self) -> float:
        """For Booth, attempt to calculate parsed preset item shipping peel if possible."""
        if self.platform_input != "Booth" or not self.order_cart:
            return 0.0
        db = self.get_db()
        try:
            preset_total = 0.0
            price_missing = False
            for item in self.order_cart:
                p = db.query(Product).filter(Product.name == item["product_name"]).first()
                unit_p = 0.0
                if p:
                    color_c = next((c for c in p.colors if c.color_name == item["variant"]), None)
                    if color_c:
                        matched_pr = next((pr.price for pr in color_c.prices if pr.platform and pr.platform.lower() == "booth"), 0.0)
                        unit_p = matched_pr
                if unit_p <= 0:
                    price_missing = True
                preset_total += unit_p * item["quantity"]
            
            if price_missing or preset_total <= 0:
                return 0.0
            return max(0.0, self.total_price_input - preset_total)
        except Exception:
            return 0.0
        finally:
            db.close()

    @rx.var
    def cart_net_price(self) -> float:
        net = self.total_price_input - self.cart_estimated_fee - self.cart_booth_shipping_peel
        return max(0.0, net)

    @rx.var
    def cart_net_unit_price(self) -> float:
        qty = self.cart_item_count
        if qty > 0:
            return self.cart_net_price / qty
        return 0.0

    # ===================== 核心事件处理器 =====================

    @rx.event
    def load_orders_page(self):
        """主页面加载。"""
        self.order_date_input = date.today().isoformat()
        self.selected_order_ids = []
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            
            # 1. 抓取统计
            p_filter = None if self.selected_product_filter == "全部商品" else self.selected_product_filter
            stats = service.get_order_statistics(product_name=p_filter)
            self.stat_total = stats["total"]
            self.stat_pending = stats["pending"]
            self.stat_shipped = stats["shipped"]
            self.stat_completed = stats["completed"]
            self.stat_after_sales = stats["after_sales"]

            # 2. 抓取对应状态下的列表
            status_map = {
                "all": None,
                "pending": OrderStatus.PENDING,
                "shipped": OrderStatus.SHIPPED,
                "completed": OrderStatus.COMPLETED,
                "after_sales": OrderStatus.AFTER_SALES
            }
            active_status = status_map.get(self.active_tab)
            
            orders_list = service.get_all_orders(status=active_status, product_name=p_filter, limit=1000)
            rows = []
            for o in orders_list:
                item_count = len(o.items)
                items_summary = ", ".join([f"{i.product_name}-{i.variant}×{i.quantity}" for i in o.items[:2]])
                if item_count > 2:
                    items_summary += f" 等{item_count}项"

                total_refunded = sum([r.refund_amount for r in o.refunds])
                
                status_display = o.status
                if o.status == OrderStatus.PENDING: status_display = "📦 待发货"
                elif o.status == OrderStatus.SHIPPED: status_display = "🚚 已发货"
                elif o.status == OrderStatus.COMPLETED: status_display = "✅ 完成"
                elif o.status == OrderStatus.AFTER_SALES: status_display = "🔧 售后"

                rows.append(SalesOrderRow(
                    勾选=o.id in self.selected_order_ids,
                    id=o.id,
                    order_no=o.order_no,
                    status=status_display,
                    items_summary=items_summary,
                    total_amount=round(float(o.total_amount), 2),
                    refunded_amount=round(float(total_refunded), 2),
                    currency=o.currency,
                    platform=o.platform,
                    created_date=o.created_date.strftime("%Y-%m-%d") if o.created_date else "",
                    notes=o.notes or "-"
                ))
            self.orders = rows
            
            # Setup default selected options
            prods = db.query(Product).all()
            if prods and not self.sel_p_name:
                self.sel_p_name = prods[0].name
                self.sel_v_name = prods[0].colors[0].color_name if prods[0].colors else ""
            
            # Auto-align target account
            self.auto_match_account()
        except Exception as e:
            print(f"Error loading orders page: {e}")
        finally:
            db.close()

    @rx.event
    def select_tab(self, tab_name: str):
        self.active_tab = tab_name
        self.selected_order_ids = []
        self.page_index = 1
        yield SalesOrderState.load_orders_page()

    @rx.event
    def select_product_filter(self, val: str):
        self.selected_product_filter = val
        self.selected_order_ids = []
        self.page_index = 1
        yield SalesOrderState.load_orders_page()

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

    # --- 建单表单字段 Setter ---
    @rx.event
    def set_order_no_input(self, val: str): self.order_no_input = val
    @rx.event
    def set_order_date_input(self, val: str): self.order_date_input = val
    @rx.event
    def set_platform_input(self, val: str):
        self.platform_input = val
        db = self.get_db()
        try:
            from models import SalesPlatform
            platform = db.query(SalesPlatform).filter(SalesPlatform.name == val).first()
            if platform:
                self.currency_input = platform.currency
        except Exception:
            pass
        finally:
            db.close()
        self.auto_match_account()
        
    @rx.event
    def set_currency_input(self, val: str):
        self.currency_input = val
        self.auto_match_account()

    @rx.event
    def set_target_account_input(self, val: str): self.target_account_input = val
    @rx.event
    def set_total_price_input(self, val: str):
        try:
            self.total_price_input = float(val) if val else 0.0
        except ValueError:
            self.total_price_input = 0.0
            
    @rx.event
    def toggle_deduct_fee(self, val: bool): self.deduct_fee_input = val
    @rx.event
    def set_notes_input(self, val: str): self.notes_input = val

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
        if self.platform_input == "微店":
            recommended = "流动资金-微店账户"
        elif self.platform_input == "Booth":
            recommended = "流动资金-booth账户"
        elif self.currency_input != "CNY":
            db = self.get_db()
            try:
                acc = db.query(CompanyBalanceItem).filter(
                    CompanyBalanceItem.category == 'asset',
                    CompanyBalanceItem.asset_type == '现金',
                    CompanyBalanceItem.currency == self.currency_input
                ).first()
                if acc:
                    recommended = acc.name
                else:
                    recommended = f"流动资金-{self.currency_input.lower()}临时账户"
            except Exception:
                recommended = f"流动资金-{self.currency_input.lower()}临时账户"
            finally:
                db.close()
        self.target_account_input = recommended

    # --- 购物车操作事件 ---
    @rx.event
    def add_to_cart(self):
        if not self.sel_p_name or not self.sel_v_name:
            return rx.toast("请选择商品及款式", level="error")
        
        db = self.get_db()
        try:
            wh = db.query(Warehouse).filter(Warehouse.name == self.sel_wh_name).first()
            wh_id = wh.id if wh else None
            
            # Find duplicates
            found = False
            for c in self.order_cart:
                if c["product_name"] == self.sel_p_name and c["variant"] == self.sel_v_name and c["warehouse_name"] == self.sel_wh_name:
                    c["quantity"] += self.sel_qty
                    found = True
                    break
            
            if not found:
                self.order_cart.append({
                    "key": f"cart_{len(self.order_cart)}_{date.today().strftime('%H%M%S')}",
                    "product_name": self.sel_p_name,
                    "variant": self.sel_v_name,
                    "quantity": self.sel_qty,
                    "warehouse_id": wh_id,
                    "warehouse_name": self.sel_wh_name
                })
            self.order_cart = list(self.order_cart)
            return rx.toast(f"成功将 {self.sel_p_name}-{self.sel_v_name} ×{self.sel_qty} 加入购物车")
        finally:
            db.close()

    @rx.event
    def remove_from_cart(self, cart_key: str):
        self.order_cart = [c for c in self.order_cart if c["key"] != cart_key]

    @rx.event
    def clear_cart(self):
        self.order_cart = []

    @rx.event
    def submit_create_order(self):
        """手动建单提交。"""
        if not self.order_no_input.strip():
            yield rx.toast("订单号不能为空！", level="error")
            return
        if not self.order_cart:
            yield rx.toast("购物车为空，请加购商品！", level="error")
            return
        if self.total_price_input <= 0:
            yield rx.toast("订单总价必须大于 0！", level="error")
            return
        
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            
            # Check duplicate order no
            existing = db.query(SalesOrder).filter(SalesOrder.order_no == self.order_no_input.strip()).first()
            if existing:
                yield rx.toast(f"订单号 {self.order_no_input} 已存在，请勿重复输入", level="error")
                return

            # Check stock for physical warning
            warning_msgs = []
            valid_reasons = ["入库", "出库", "退货入库", "发货撤销", "验收完成入库", "其他入库", "库存移动"]
            
            final_unit = self.cart_net_unit_price
            items_data = []
            for item in self.order_cart:
                items_data.append({
                    "product_name": item["product_name"],
                    "variant": item["variant"],
                    "quantity": item["quantity"],
                    "unit_price": final_unit,
                    "warehouse_id": item["warehouse_id"]
                })
                
                # Query physical stock
                from sqlalchemy import func
                stock_q = db.query(func.sum(InventoryLog.change_amount)).filter(
                    InventoryLog.product_name == item["product_name"],
                    InventoryLog.variant == item["variant"],
                    InventoryLog.reason.in_(valid_reasons)
                )
                if item["warehouse_id"] is not None:
                    stock_q = stock_q.filter(InventoryLog.warehouse_id == item["warehouse_id"])
                else:
                    stock_q = stock_q.filter(InventoryLog.warehouse_id == None)
                    
                cur_stock = stock_q.scalar() or 0
                if cur_stock < item["quantity"]:
                    warning_msgs.append(f"{item['product_name']}-{item['variant']}(需:{item['quantity']}, 可用:{cur_stock})")

            # Create Order
            order_date = None
            if self.order_date_input:
                try:
                    order_date = date.fromisoformat(self.order_date_input)
                except ValueError:
                    pass
            
            order, err = service.create_order(
                items_data=items_data,
                platform=self.platform_input,
                currency=self.currency_input,
                notes=self.notes_input,
                order_date=order_date,
                order_no=self.order_no_input.strip(),
                target_account_name=self.target_account_input
            )
            
            if err:
                yield rx.toast(f"建单失败: {err}", level="error")
                return
                
            self.order_cart = []
            self.order_no_input = ""
            self.notes_input = ""
            self.total_price_input = 0.0
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            if warning_msgs:
                yield rx.toast("⚠️ 订单已超卖创建！请及时补足大货库存: " + " | ".join(warning_msgs), duration=5000)
            else:
                yield rx.toast("✅ 线上销售订单创建成功！")
            
            yield SalesOrderState.load_orders_page()
        except Exception as e:
            yield rx.toast(f"系统错误: {e}", level="error")
        finally:
            db.close()

    # ===================== Excel 批量导入 =====================

    @rx.event
    async def handle_excel_import(self, files: list[rx.UploadFile]):
        if not files:
            return
        
        self.excel_import_errors = []
        self.parsed_preview_orders = []
        self.any_out_of_stock = False
        
        file = files[0]
        data = await file.read()
        
        db = self.get_db()
        try:
            df = pd.read_excel(io.BytesIO(data))
            service = SalesOrderService(db)
            
            parsed, errors = service.validate_and_parse_import_data(df, self.exchange_rate)
            if errors:
                if isinstance(errors, list):
                    self.excel_import_errors = errors
                else:
                    self.excel_import_errors = [str(errors)]
                return rx.toast("Excel 模板校验失败！请点击展开详情查看具体错误行", level="error")
            
            if parsed:
                # Resolve warehouse names for display
                wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}
                
                preview_list = []
                for p in parsed:
                    if p.get("is_out_of_stock", False):
                        self.any_out_of_stock = True
                    
                    items_str = ", ".join([f"{i['product_name']}-{i['variant']} ×{i['quantity']} (仓: {wh_dict.get(i['warehouse_id'], '未分配')})" for i in p["items"]])
                    preview_list.append({
                        "stock_warning": "⚠️ " + p.get("stock_warning", "缺货") if p.get("is_out_of_stock", False) else "🟢 库存充足",
                        "order_no": p["order_no"],
                        "platform": p["platform"],
                        "target_account": p["target_account"],
                        "currency": p["currency"],
                        "total_qty": p["total_qty"],
                        "gross_price": round(float(p["gross_price"]), 2),
                        "fee": round(float(p["fee"]), 2),
                        "net_price": round(float(p["net_price"]), 2),
                        "items_str": items_str,
                        "items": p["items"]
                    })
                self.parsed_preview_orders = preview_list
                return rx.toast(f"✅ Excel 校验成功！识别到 {len(preview_list)} 个订单，请预览核对无误后点击导入。")
        except Exception as e:
            self.excel_import_errors = [f"文件解析发生崩溃: {e}"]
            return rx.toast("文件读取失败，请检查是否为合规的 .xlsx 模板", level="error")
        finally:
            db.close()

    @rx.event
    def submit_batch_import(self):
        if not self.parsed_preview_orders:
            yield rx.toast("无可导入的数据！", level="error")
            return
            
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            count = service.batch_create_orders(self.parsed_preview_orders)
            
            self.parsed_preview_orders = []
            self.excel_import_errors = []
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            yield rx.toast(f"成功批量导入并生成 {count} 个销售订单！", level="success")
            yield SalesOrderState.load_orders_page()
        except Exception as e:
            yield rx.toast(f"批量导入写入失败: {e}", level="error")
        finally:
            db.close()

    # ===================== 表格多选与批量操作 =====================

    @rx.event
    def toggle_order_select(self, order_id: int):
        order_id = int(order_id)
        if order_id in self.selected_order_ids:
            self.selected_order_ids.remove(order_id)
        else:
            self.selected_order_ids.append(order_id)
            
        # Synchronize select flags on orders list
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
    def ship_selected_orders(self):
        if not self.selected_order_ids:
            yield rx.toast("没有选中的订单！", level="error")
            return
            
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            success = 0
            errors = []
            for o_id in self.selected_order_ids:
                try:
                    service.ship_order(o_id)
                    success += 1
                except Exception as e:
                    errors.append(f"订单 {o_id} 发货失败: {e}")
                    
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            self.selected_order_ids = []
            if errors:
                for err in errors:
                    yield rx.toast(err, level="error", duration=4000)
            yield rx.toast(f"📦 批量发货完成！成功发货 {success} 个单据")
            yield SalesOrderState.load_orders_page()
        finally:
            db.close()

    @rx.event
    def complete_selected_orders(self):
        if not self.selected_order_ids:
            yield rx.toast("没有选中的订单！", level="error")
            return
            
        db = self.get_db()
        try:
            service = SalesOrderService(db)
            success = 0
            errors = []
            for o_id in self.selected_order_ids:
                try:
                    service.complete_order(o_id)
                    success += 1
                except Exception as e:
                    errors.append(f"订单 {o_id} 收款结算失败: {e}")
                    
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            self.selected_order_ids = []
            if errors:
                for err in errors:
                    yield rx.toast(err, level="error", duration=4000)
            yield rx.toast(f"✅ 批量收款对账完成！已结清 {success} 个订单")
            yield SalesOrderState.load_orders_page()
        finally:
            db.close()

    # ===================== 查看详情与基础修改 =====================

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
                return rx.toast("订单不存在！", level="error")
                
            self.detail_order_no = o.order_no
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
                    "unit_price": round(float(i.unit_price), 2),
                    "subtotal": round(float(i.subtotal), 2)
                })
            self.detail_items = items_list
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
            
            yield rx.toast("订单基础信息修改保存成功！")
            yield SalesOrderState.open_order_detail(self.active_detail_order_id)
            yield SalesOrderState.load_orders_page()
        except Exception as e:
            yield rx.toast(f"保存修改失败: {e}", level="error")
            return
        finally:
            db.close()

    @rx.event
    def open_delete_confirm(self):
        self.show_delete_confirm = True

    @rx.event
    def cancel_delete_confirm(self):
        self.show_delete_confirm = False

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
            yield SalesOrderState.load_orders_page()
        except Exception as e:
            yield rx.toast(f"删除失败: {e}", level="error")
            return
        finally:
            db.close()

    # ===================== 售后 Dialog 与物理联动 =====================

    @rx.event
    def open_refund_dialog(self, order_id: int):
        self.active_refund_order_id = int(order_id)
        self.show_refund_form = True
        
        # Reset form fields
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
                return rx.toast("订单不存在", level="error")
                
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

            # Configure options for return and resend
            ret_items = []
            res_items = []
            
            wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}
            all_prods = db.query(Product).all()
            
            for item in o.items:
                wh_name = wh_dict.get(item.warehouse_id, "未分配")
                # Return Item Model
                ret_items.append({
                    "order_item_id": item.id,
                    "product_name": item.product_name,
                    "variant": item.variant,
                    "max_quantity": item.quantity,
                    "quantity": 0,
                    "warehouse_id": item.warehouse_id or 0,
                    "warehouse_name": wh_name
                })
                
                # Resend Parts options mapping
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
            yield rx.toast("售后金额不能为负数", level="error")
            return
        if not self.ref_reason_input.strip():
            yield rx.toast("请输入售后原因以作记录审计", level="error")
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
            yield SalesOrderState.open_refund_dialog(self.active_refund_order_id)
            yield SalesOrderState.load_orders_page()
        except Exception as e:
            yield rx.toast(f"申请售后失败: {e}", level="error")
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
            yield SalesOrderState.open_refund_dialog(self.active_refund_order_id)
            yield SalesOrderState.load_orders_page()
        except Exception as e:
            yield rx.toast(f"修改售后失败: {e}", level="error")
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
            yield SalesOrderState.open_refund_dialog(self.active_refund_order_id)
            yield SalesOrderState.load_orders_page()
        except Exception as e:
            yield rx.toast(f"回滚售后失败: {e}", level="error")
            return
        finally:
            db.close()
