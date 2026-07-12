# yurara_app/state/offline_sales_state.py
"""
线下展会 POS 收银台 State 模块。
负责购物车运算、1.98% 支付手续费自动扣除、物理库存木桶限量校验以及收银场景配置。
"""
import reflex as rx
from datetime import datetime
from pydantic import BaseModel
from typing import Any
from ..state.app_state import AppState
from services.offline_sales_service import OfflineSalesService
from services.product_service import ProductService
from services.inventory_service import InventoryService
from services.finance_service import FinanceService
from constants import PLATFORM_CODES, OrderStatus
from models import OfflineTemplate, Product, Warehouse, CompanyBalanceItem


class CartItemModel(BaseModel):
    product_name: str = ""
    variant: str = ""
    unit_price: float = 0.0
    qty: int = 1
    image_data: str = ""


class POSTemplateItemModel(BaseModel):
    id: int = 0
    product_name: str = ""
    variant: str = ""
    preset_price: float = 0.0
    remaining_quantity: int = 0
    max_limit: int = 0
    image_data: str = ""


class POSTemplateModel(BaseModel):
    id: int = 0
    name: str = ""
    code: str = ""
    currency: str = "CNY"
    warehouse_id: int = 0
    warehouse_name: str = "未分配"
    platform: str = "国内线下"
    template_items: list[POSTemplateItemModel] = []


class POSOrderRow(BaseModel):
    order_no: str = ""
    date: str = ""
    items_str: str = ""
    original_amount: float = 0.0
    received_amount: float = 0.0
    notes: str = ""


POS_TRANSLATIONS = {
    "zh": {
        "active_template": "当前活动收银模板：",
        "back_to_cashier": "🔙 返回收银台",
        "history_orders": "📜 历史交易流水",
        "exit_fullscreen": "📴 退出专注全屏",
        "open_fullscreen": "📺 开启收银全屏",
        "history_orders_title": "📜 已结账历史交易全览",
        "order_no": "交易单号",
        "order_date": "成交日期",
        "order_items": "购买商品明细",
        "order_amount": "交易额",
        "received_amount": "实收记账额",
        "notes": "流向备注",
        "action": "操作",
        "delete_confirm_title": "确定要删除此订单并回滚吗？",
        "delete_confirm_desc_1": "此操作将永久删除展会订单 ",
        "delete_confirm_desc_2": "，回滚已扣减的模板分配额度、还原出货仓库对应的实物库存，并全额扣减已记账的现金流水与资产！是否确定？",
        "delete_confirm_btn": "确定删除",
        "exhibition_panel": "🛍️ 展会选购面板：",
        "source_warehouse": "大货库存提取来源仓: ",
        "added_cart_prefix": "已加购 ",
        "added_cart_suffix": " 件",
        "recent_ledger": "📋 近期本地模板成交流水 (快捷对账)",
        "items_detail": "商品明细",
        "original_subtotal": "原价小计",
        "net_received": "实收净额",
        "cart_title": "🧾 POS 结账清单",
        "clear_cart": "清空选购",
        "cart_empty": "购物车为空",
        "select_payment": "💵 选择支付媒介：",
        "pay_cash": "💵 现金支付",
        "pay_paypay": "📱 PayPay 扫码",
        "total_due": "应收总价:",
        "paypay_fee_label": "PayPay 扣减扣点 (1.98%):",
        "net_receive_label": "预计实际收款入账金额:",
        "deposit_account": "物理入账账户",
        "checkout_btn": "✅ 完成交易并扣减库存记账",
        "out_of_stock": "🚫 售罄",
        "no_stock": "无货",
        "revoke": "撤销",
        "empty_template_warning": "⚠️ 线下展会收银模板为空！请先点击右侧“模板配置”Tab建立至少一个收银模板配置。",
    },
    "en": {
        "active_template": "Active Template:",
        "back_to_cashier": "🔙 Back to Cashier",
        "history_orders": "📜 History Orders",
        "exit_fullscreen": "📴 Exit Fullscreen",
        "open_fullscreen": "📺 Open Fullscreen",
        "history_orders_title": "📜 History Transaction List",
        "order_no": "Order No",
        "order_date": "Date",
        "order_items": "Items Detail",
        "order_amount": "Total Amt",
        "received_amount": "Received Amt",
        "notes": "Remarks",
        "action": "Action",
        "delete_confirm_title": "Delete Order & Rollback?",
        "delete_confirm_desc_1": "This will permanently delete order ",
        "delete_confirm_desc_2": ", rollback template quantity, restore physical stock, and reverse all asset ledgers! Confirm?",
        "delete_confirm_btn": "Confirm Delete",
        "exhibition_panel": "🛍️ Exhibition Panel:",
        "source_warehouse": "Source Warehouse: ",
        "added_cart_prefix": "Added ",
        "added_cart_suffix": " qty",
        "recent_ledger": "📋 Recent Template Transactions (Quick Audit)",
        "items_detail": "Items Detail",
        "original_subtotal": "Subtotal",
        "net_received": "Net Received",
        "cart_title": "🧾 POS Checkout List",
        "clear_cart": "Clear Cart",
        "cart_empty": "Cart is empty",
        "select_payment": "💵 Select Payment:",
        "pay_cash": "💵 Cash",
        "pay_paypay": "📱 PayPay Scan",
        "total_due": "Total Due:",
        "paypay_fee_label": "PayPay Fee (1.98%):",
        "net_receive_label": "Est. Net Income:",
        "deposit_account": "Deposit Account",
        "checkout_btn": "✅ Checkout & Update Stock/Ledger",
        "out_of_stock": "🚫 Out of stock",
        "no_stock": "No Stock",
        "revoke": "Revoke",
        "empty_template_warning": "⚠️ Offline checkout template is empty! Please click 'Template Config' on the right to create at least one template.",
    },
    "ja": {
        "active_template": "現在のレジテンプレート：",
        "back_to_cashier": "🔙 レジに戻る",
        "history_orders": "📜 取引履歴",
        "exit_fullscreen": "📴 フルスクリーン終了",
        "open_fullscreen": "📺 フルスクリーン開始",
        "history_orders_title": "📜 会計済み取引履歴一覧",
        "order_no": "注文番号",
        "order_date": "成約日",
        "order_items": "購入商品明細",
        "order_amount": "取引額",
        "received_amount": "実収額",
        "notes": "備考",
        "action": "操作",
        "delete_confirm_title": "この注文を削除してロールバックしますか？",
        "delete_confirm_desc_1": "この操作は展示会注文 ",
        "delete_confirm_desc_2": " を永久に削除し、テンプレート割当量を戻し、実物在庫を復元し、記帳されたキャッシュフローと資産を全額差し引きます！よろしいですか？",
        "delete_confirm_btn": "削除確定",
        "exhibition_panel": "🛍️ 展示会商品パネル：",
        "source_warehouse": "出庫元倉庫: ",
        "added_cart_prefix": "加算済み ",
        "added_cart_suffix": " 点",
        "recent_ledger": "📋 最近のローカル取引履歴 (簡易照合)",
        "items_detail": "商品明细",
        "original_subtotal": "小計",
        "net_received": "実収純額",
        "cart_title": "🧾 POS 会計リスト",
        "clear_cart": "カートを空にする",
        "cart_empty": "カートは空です",
        "select_payment": "💵 決済方法選択：",
        "pay_cash": "💵 現金決済",
        "pay_paypay": "📱 PayPay決済",
        "total_due": "お会計金額：",
        "paypay_fee_label": "PayPay決済手数料 (1.98%):",
        "net_receive_label": "入金予定額：",
        "deposit_account": "入金先口座",
        "checkout_btn": "✅ 会計完了（在庫減算・記帳）",
        "out_of_stock": "🚫 完売",
        "no_stock": "在庫なし",
        "revoke": "キャンセル",
        "empty_template_warning": "⚠️ 展示会レジテンプレートが空です！右側の「テンプレート設定」タブをクリックして、少なくとも1つのテンプレートを作成してください。",
    }
}


def _sync_load_offline_data(is_test: bool, selected_template_id: int):
    """在后台线程中执行的所有数据库查询"""
    import os
    from sqlalchemy.orm import sessionmaker
    from .app_state import get_cached_engine
    from models import OfflineTemplate
    
    engine = get_cached_engine(is_test)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        service = OfflineSalesService(db)
        
        # 1. 加载模板列表
        _api_url = os.environ.get("API_URL", f"http://localhost:{os.environ.get('BACKEND_PORT', '8000')}")
        tpls = service.get_all_templates()
        prod_service = ProductService(service.db)
        all_prods = prod_service.get_all_products()
        img_lookup = {f"{p.name}_{c.color_name}": f"{_api_url}/color-image/{c.id}" if c.image_data else "" for p in all_prods for c in p.colors}
        
        inv_service = InventoryService(service.db)
        wh_details = inv_service.get_warehouse_inventory_details()
        prod_lookup = {p.name: p for p in all_prods}
        
        tpl_list = []
        for t in tpls:
            stock_in_wh = wh_details.get(t.warehouse_id, {}).get("stock", {})
            items_list = []
            for item in sorted(t.items, key=lambda x: x.id):
                prod_obj = prod_lookup.get(item.product_name)
                reqs = {"整套": 1}
                if prod_obj:
                    color_obj = next((c for c in prod_obj.colors if c.color_name == item.variant), None)
                    if color_obj and color_obj.parts:
                        reqs = {p.part_name: p.quantity for p in color_obj.parts}
                
                pt_dict = stock_in_wh.get(item.product_name, {}).get(item.variant, {})
                possible_sets = 0
                if reqs:
                    possible_sets = min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items())
                
                key = f"{item.product_name}_{item.variant}"
                img_data = img_lookup.get(key, "")
                
                items_list.append(POSTemplateItemModel(
                    id=item.id,
                    product_name=item.product_name,
                    variant=item.variant,
                    preset_price=round(float(item.preset_price), 2),
                    remaining_quantity=item.remaining_quantity,
                    max_limit=max(0, possible_sets),
                    image_data=img_data
                ))
            
            tpl_list.append(POSTemplateModel(
                id=t.id,
                name=t.name,
                code=t.code,
                currency=t.currency,
                warehouse_id=t.warehouse_id or 0,
                warehouse_name=t.warehouse.name if t.warehouse else "未分配",
                platform=t.platform or "中国线下",
                template_items=items_list
            ))
            
        # 2. 加载选定模板的订单
        active_tpl_id = selected_template_id if selected_template_id else (tpl_list[0].id if tpl_list else 0)
        orders_list = []
        if active_tpl_id:
            tpl = service.db.query(OfflineTemplate).filter(OfflineTemplate.id == active_tpl_id).first()
            if tpl:
                orders = service.get_orders_by_template(tpl.code)
                for o in orders:
                    items_str = ", ".join([f"{i.product_name}-{i.variant} ×{i.quantity}" for i in o.items])
                    fee = 0.0
                    if "手续费" in (o.notes or ""):
                        try:
                            fee = float(o.notes.split("扣除手续费")[1].replace(")", "").strip())
                        except:
                            pass
                    orders_list.append(POSOrderRow(
                        order_no=o.order_no,
                        date=o.created_date.strftime("%Y-%m-%d") if o.created_date else "",
                        items_str=items_str,
                        original_amount=round(float(o.total_amount), 2),
                        received_amount=round(float(o.total_amount - fee), 2),
                        notes=o.notes or ""
                    ))
        
        return tpl_list, orders_list, active_tpl_id
    finally:
        db.close()


class OfflineSalesState(AppState):
    pos_lang: str = "zh"  # "zh", "en", "ja"
    active_tab: str = "pos"  # "pos" 或 "template"
    templates: list[POSTemplateModel] = []
    selected_template_id: int = 0
    cart: list[CartItemModel] = []
    pay_method: str = "现金"  # "现金" 或 "PayPay"
    selected_account_id: int = 0
    show_history_only: bool = False
    pos_orders: list[POSOrderRow] = []
    is_fullscreen: bool = False
    
    # 模板配置/编辑状态
    is_edit_mode: bool = False
    tpl_id: int = 0
    tpl_name: str = ""
    tpl_code: str = ""
    tpl_currency: str = "CNY"
    tpl_wh_id: int = 0
    tpl_platform: str = "国内线下"
    all_assignable_items: list[dict[str, Any]] = []
    tpl_wh_name: str = ""
    selected_account_name: str = ""
    _assignable_loaded: bool = False  # 懒加载标志：仅在首次切换模板配置Tab时触发
    _page_initialized: bool = False   # 页面级缓存标志：驱驶页面时跳过重复加载

    # ===================== 计算属性 =====================

    @rx.var
    def has_templates(self) -> bool:
        return len(self.templates) > 0

    @rx.var
    def tr(self) -> dict[str, str]:
        return POS_TRANSLATIONS.get(self.pos_lang, POS_TRANSLATIONS["zh"])

    @rx.var
    def active_template(self) -> POSTemplateModel | None:
        """获取当前选择的活动收银模板。"""
        for t in self.templates:
            if t.id == self.selected_template_id:
                return t
        return self.templates[0] if self.templates else None

    @rx.var
    def active_template_items(self) -> list[POSTemplateItemModel]:
        t = self.active_template
        return t.template_items if t else []

    @rx.var
    def template_options(self) -> list[str]:
        return [f"{t.name} ({t.code})" for t in self.templates]

    @rx.var
    def template_selected_value(self) -> str:
        t = self.active_template
        if t:
            return f"{t.name} ({t.code})"
        return ""

    @rx.var
    def edit_template_selected_value(self) -> str:
        for t in self.templates:
            if t.id == self.tpl_id:
                return f"{t.name} ({t.code})"
        if self.is_edit_mode and self.templates:
            return f"{self.templates[0].name} ({self.templates[0].code})"
        return ""

    @rx.var
    def cart_qty_map(self) -> dict[str, int]:
        res = {}
        if self.active_template:
            for item in self.active_template.template_items:
                res[f"{item.product_name}_{item.variant}"] = 0
        for ci in self.cart:
            res[f"{ci.product_name}_{ci.variant}"] = ci.qty
        return res

    @rx.var
    def cart_total(self) -> float:
        return sum(ci.qty * ci.unit_price for ci in self.cart)

    @rx.var
    def paypay_fee(self) -> float:
        """若使用 PayPay 支付，自动产生 1.98% 手续费。"""
        if self.pay_method == "PayPay":
            return self.cart_total * 0.0198
        return 0.0

    @rx.var
    def paypay_estimated_receive(self) -> float:
        return self.cart_total - self.paypay_fee

    # --- 格式化显示 ---
    @rx.var
    def cart_total_str(self) -> str:
        curr = self.active_template.currency if self.active_template else "CNY"
        if curr == "CNY":
            return f"¥ {self.cart_total:,.2f}"
        elif curr == "JPY":
            return f"{self.cart_total:,.0f} JPY"
        else:
            return f"{self.cart_total:,.2f} {curr}"

    @rx.var
    def paypay_fee_str(self) -> str:
        curr = self.active_template.currency if self.active_template else "CNY"
        if curr == "CNY":
            return f"¥ {self.paypay_fee:,.2f}"
        elif curr == "JPY":
            return f"{self.paypay_fee:,.0f} JPY"
        else:
            return f"{self.paypay_fee:,.2f} {curr}"

    @rx.var
    def paypay_receive_str(self) -> str:
        curr = self.active_template.currency if self.active_template else "CNY"
        if curr == "CNY":
            return f"¥ {self.paypay_estimated_receive:,.2f}"
        elif curr == "JPY":
            return f"{self.paypay_estimated_receive:,.0f} JPY"
        else:
            return f"{self.paypay_estimated_receive:,.2f} {curr}"

    @rx.var
    def cash_account_options(self) -> list[str]:
        """依据当前模板币种过滤适合收款的现金账户。"""
        if not self.active_template:
            return []
        curr = self.active_template.currency
        db = self.get_db()
        try:
            accs = db.query(CompanyBalanceItem).filter(
                CompanyBalanceItem.category == 'asset',
                CompanyBalanceItem.asset_type == '现金',
                CompanyBalanceItem.currency == curr
            ).all()
            return [a.name for a in accs]
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
    def is_cart_empty(self) -> bool:
        return len(self.cart) == 0

    # ===================== 事件处理器 =====================

    @rx.event
    async def load_offline_page(self):
        """初始化加载展会收银页面。"""
        # 1. 登录验证守卫（方案 A）
        from .auth_state import AuthState
        auth_state = await self.get_state(AuthState)
        if not auth_state.authenticated:
            return

        if self._page_initialized:
            # 页面已初始化且其间没有发生数据变更（结账/删单/模板修改均已内联刷新状态）
            # 直接跳过所有数据库查询，实现页面秒开入场
            self.auto_match_cash_account()
            return
        
        # 2. 将同步阻塞的数据库操作交付线程池运行（方案 C）
        import asyncio
        loop = asyncio.get_running_loop()
        tpl_list, orders_list, active_tpl_id = await loop.run_in_executor(
            None,
            _sync_load_offline_data,
            self.test_mode,
            self.selected_template_id
        )
        
        self.templates = tpl_list
        self.pos_orders = orders_list
        self.selected_template_id = active_tpl_id
        
        # 补全其他的状态初始化逻辑
        self._assignable_loaded = False
        if self.templates:
            first_tpl = self.templates[0]
            self.tpl_wh_id = first_tpl.warehouse_id
            self.tpl_wh_name = first_tpl.warehouse_name
        self.tpl_platform = "国内线下"
        self.is_edit_mode = False
        self._page_initialized = True
        
        self.auto_match_cash_account()

    @rx.event
    def select_tab(self, tab_name: str):
        self.active_tab = tab_name
        if tab_name == "pos":
            self.auto_match_cash_account()
        elif tab_name == "template" and not self._assignable_loaded:
            # 懒加载：首次切换至模板配置Tab才触发库存查询
            self.open_create_template()

    @rx.event
    def select_template(self, tpl_id: int):
        """切换结账模板。"""
        self.selected_template_id = int(tpl_id)
        self.cart = []
        db = self.get_db()
        try:
            service = OfflineSalesService(db)
            self.load_template_orders(service)
            self.auto_match_cash_account()
        finally:
            db.close()

    @rx.event
    def change_template_by_option(self, val: str):
        """UI select 下拉切换收银模板。"""
        for t in self.templates:
            if f"{t.name} ({t.code})" == val:
                yield OfflineSalesState.select_template(t.id)
                break

    @rx.event
    def select_template_for_edit_by_option(self, val: str):
        """UI select 下拉选择要编辑的模板"""
        for t in self.templates:
            if f"{t.name} ({t.code})" == val:
                yield OfflineSalesState.open_edit_template(t)
                break

    def load_templates_list(self, service: OfflineSalesService):
        """拉取收银场景模板配置列表。"""
        import os
        _api_url = os.environ.get("API_URL", f"http://localhost:{os.environ.get('BACKEND_PORT', '8000')}")
        tpls = service.get_all_templates()
        prod_service = ProductService(service.db)
        all_prods = prod_service.get_all_products()
        img_lookup = {f"{p.name}_{c.color_name}": f"{_api_url}/color-image/{c.id}" if c.image_data else "" for p in all_prods for c in p.colors}
        
        # 抓取仓库木桶原理真实大货可组装库存限额
        inv_service = InventoryService(service.db)
        wh_details = inv_service.get_warehouse_inventory_details()
        
        # 缓存所有产品，以避免在循环中对每个模板项执行 N+1 数据库查询
        prod_lookup = {p.name: p for p in all_prods}
        
        tpl_list = []
        for t in tpls:
            stock_in_wh = wh_details.get(t.warehouse_id, {}).get("stock", {})
            
            items_list = []
            for item in sorted(t.items, key=lambda x: x.id):
                # 从内存中快速检索产品，无需再次查询数据库
                prod_obj = prod_lookup.get(item.product_name)
                reqs = {"整套": 1}
                if prod_obj:
                    color_obj = next((c for c in prod_obj.colors if c.color_name == item.variant), None)
                    if color_obj and color_obj.parts:
                        reqs = {p.part_name: p.quantity for p in color_obj.parts}
                
                pt_dict = stock_in_wh.get(item.product_name, {}).get(item.variant, {})
                possible_sets = 0
                if reqs:
                    possible_sets = min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items())
                
                key = f"{item.product_name}_{item.variant}"
                img_data = img_lookup.get(key, "")
                
                items_list.append(POSTemplateItemModel(
                    id=item.id,
                    product_name=item.product_name,
                    variant=item.variant,
                    preset_price=round(float(item.preset_price), 2),
                    remaining_quantity=item.remaining_quantity,
                    max_limit=max(0, possible_sets),
                    image_data=img_data
                ))
            
            tpl_list.append(POSTemplateModel(
                id=t.id,
                name=t.name,
                code=t.code,
                currency=t.currency,
                warehouse_id=t.warehouse_id or 0,
                warehouse_name=t.warehouse.name if t.warehouse else "未分配",
                platform=t.platform or "中国线下",
                template_items=items_list
            ))
        self.templates = tpl_list

    def load_template_orders(self, service: OfflineSalesService):
        """载入当前模板在物理流向中已成交的历史结账订单。"""
        tpl = service.db.query(OfflineTemplate).filter(OfflineTemplate.id == self.selected_template_id).first()
        if not tpl:
            return
            
        orders = service.get_orders_by_template(tpl.code)
        orders_list = []
        for o in orders:
            items_str = ", ".join([f"{i.product_name}-{i.variant} ×{i.quantity}" for i in o.items])
            fee = 0.0
            if "手续费" in (o.notes or ""):
                try:
                    fee = float(o.notes.split("扣除手续费")[1].replace(")", "").strip())
                except:
                    pass
            orders_list.append(POSOrderRow(
                order_no=o.order_no,
                date=o.created_date.strftime("%Y-%m-%d") if o.created_date else "",
                items_str=items_str,
                original_amount=round(float(o.total_amount), 2),
                received_amount=round(float(o.total_amount - fee), 2),
                notes=o.notes or ""
            ))
        self.pos_orders = orders_list

    # --- 收银购物车操作 ---
    @rx.event
    def add_to_cart(self, prod_name: str, variant: str):
        """加购逻辑：检查模板数量余量及库存上限。"""
        target_item = None
        for item in self.active_template_items:
            if item.product_name == prod_name and item.variant == variant:
                target_item = item
                break
                
        if not target_item:
            return rx.toast("未找到对应商品模板项目！", level="error")
            
        price = target_item.preset_price
        max_qty = target_item.max_limit
        image_data = target_item.image_data

        # 寻找购物车现有
        found = False
        for ci in self.cart:
            if ci.product_name == prod_name and ci.variant == variant:
                if ci.qty < max_qty:
                    ci.qty += 1
                else:
                    return rx.toast("加购数量已达该模板限额或大货散料木桶配装上限！", level="error")
                found = True
                break
                
        if not found:
            if max_qty > 0:
                self.cart.append(CartItemModel(
                    product_name=prod_name,
                    variant=variant,
                    unit_price=round(float(price), 2),
                    qty=1,
                    image_data=image_data
                ))
            else:
                return rx.toast("该商品已售罄或散料库存已不足配装成套！", level="error")
        # 强制通知更新
        self.cart = list(self.cart)

    @rx.event
    def remove_from_cart(self, prod_name: str, variant: str):
        """购物车中减少一件商品。"""
        for ci in self.cart:
            if ci.product_name == prod_name and ci.variant == variant:
                ci.qty -= 1
                if ci.qty <= 0:
                    self.cart.remove(ci)
                break
        self.cart = list(self.cart)

    @rx.event
    def clear_cart(self):
        self.cart = []

    @rx.event
    def set_pay_method(self, method: str):
        """切换支付，并触发账户匹配更新。"""
        self.pay_method = method
        self.auto_match_cash_account()

    def auto_match_cash_account(self):
        """根据当前支付方式和币种，自动推荐/匹配最适合的收款资产钱包。"""
        if not self.active_template:
            return
        db = self.get_db()
        try:
            curr = self.active_template.currency
            accs = db.query(CompanyBalanceItem).filter(
                CompanyBalanceItem.category == 'asset',
                CompanyBalanceItem.asset_type == '现金',
                CompanyBalanceItem.currency == curr
            ).all()
            
            if not accs:
                return
                
            target_acc = accs[0]
            # 逻辑匹配：PayPay 匹配 paypay 账户，现金匹配 Cash/现金
            for a in accs:
                if self.pay_method == "PayPay" and "paypay" in a.name.lower():
                    target_acc = a
                    break
                elif self.pay_method == "现金" and ("现金" in a.name or "cash" in a.name.lower()):
                    target_acc = a
                    break
            self.selected_account_id = target_acc.id
            self.selected_account_name = target_acc.name
        except Exception:
            pass
        finally:
            db.close()

    @rx.event
    def set_selected_account_id(self, val: str):
        if val: self.selected_account_id = int(val)

    @rx.event
    def set_selected_account_name(self, name: str):
        self.selected_account_name = name
        db = self.get_db()
        try:
            acc = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == name).first()
            if acc:
                self.selected_account_id = acc.id
        finally:
            db.close()

    @rx.event
    def submit_pos_checkout(self):
        """执行订单支付清结。"""
        if self.is_cart_empty:
            return rx.toast("购物车为空", level="error")
        if not self.selected_account_id:
            return rx.toast("请选择物理收款账户", level="error")
            
        db = self.get_db()
        try:
            service = OfflineSalesService(db)
            
            # 转为 dict 形式
            items_data = [
                {"product_name": ci.product_name, "variant": ci.variant, "qty": ci.qty, "unit_price": ci.unit_price} 
                for ci in self.cart
            ]
            
            order_no, net = service.checkout_offline_order(
                template_id=self.selected_template_id,
                cart_items=items_data,
                payment_method=self.pay_method,
                fee_rate=0.0198,
                account_id=self.selected_account_id
            )
            
            # 结账成功
            self.cart = []
            self.load_templates_list(service)
            self.load_template_orders(service)
            
            # 刷新
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            return rx.toast(f"交易成功！订单号: {order_no}，实收入账: {net:,.2f}")
        except Exception as e:
            db.rollback()
            return rx.toast(f"交易清结失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def set_pos_lang(self, val: str | list[str]):
        if isinstance(val, list):
            val = val[0] if val else "zh"
        self.pos_lang = val

    @rx.event
    def toggle_history_only(self):
        self.show_history_only = not self.show_history_only

    @rx.event
    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            return rx.call_script(
                "if (!document.fullscreenElement) { document.documentElement.requestFullscreen().catch(err => console.log(err)); }"
            )
        else:
            return rx.call_script(
                "if (document.fullscreenElement) { document.exitFullscreen().catch(err => console.log(err)); }"
            )

    @rx.event
    def delete_offline_order(self, order_no: str):
        """删除线下POS订单，回滚模板余量、还原实物库存、流水与资金"""
        db = self.get_db()
        try:
            service = OfflineSalesService(db)
            msg = service.delete_offline_order(order_no)
            
            # 重新加载列表和数据
            self.load_templates_list(service)
            self.load_template_orders(service)
            
            # 同步缓存
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            return rx.toast(f"成功: {msg}")
        except Exception as e:
            db.rollback()
            return rx.toast(f"删除回滚失败: {e}", level="error")
        finally:
            db.close()

    # --- 模板配置新建/修改 Setter 与动作 ---
    @rx.event
    def set_tpl_name(self, val: str): self.tpl_name = val
    @rx.event
    def set_tpl_code(self, val: str): self.tpl_code = val
    @rx.event
    def set_tpl_currency(self, val: str): self.tpl_currency = val
    @rx.event
    def set_tpl_wh_id(self, val: str):
        self.tpl_wh_id = int(val) if val else 0
        self.load_assignable_stocks()

    @rx.event
    def set_tpl_wh_name(self, name: str):
        self.tpl_wh_name = name
        db = self.get_db()
        try:
            wh = db.query(Warehouse).filter(Warehouse.name == name).first()
            if wh:
                self.tpl_wh_id = wh.id
                self.load_assignable_stocks()
        finally:
            db.close()
        
    @rx.event
    def set_tpl_platform(self, val: str):
        self.tpl_platform = val
        self.load_assignable_stocks()

    @rx.event
    def change_template_mode(self, val: str | list[str]):
        """处理新建/编辑模式切换"""
        if isinstance(val, list):
            val = val[0] if val else ""
        if val == "create":
            self.open_create_template()
        else:
            self.is_edit_mode = True
            if self.templates:
                self.open_edit_template(self.templates[0])

    @rx.event
    def open_create_template(self):
        """开启模板新建模式。"""
        self.is_edit_mode = False
        self.tpl_id = 0
        self.tpl_name = ""
        self.tpl_code = ""
        self.tpl_currency = "CNY"
        self.tpl_platform = "国内线下"
        
        # 直接从已加载的 templates 中取第一个仓库，避免再次查询数据库
        if self.templates:
            first_tpl = self.templates[0]
            self.tpl_wh_id = first_tpl.warehouse_id
            self.tpl_wh_name = first_tpl.warehouse_name
        
        self.load_assignable_stocks()
        self._assignable_loaded = True

    @rx.event
    def open_edit_template(self, tpl: POSTemplateModel):
        """载入已有配置开启编辑模式。"""
        self.is_edit_mode = True
        self.tpl_id = tpl.id
        self.tpl_name = tpl.name
        self.tpl_code = tpl.code
        self.tpl_currency = tpl.currency
        self.tpl_wh_id = tpl.warehouse_id
        self.tpl_wh_name = tpl.warehouse_name
        self.tpl_platform = tpl.platform
        
        self.load_assignable_stocks(exist_items=tpl.template_items)

    def load_assignable_stocks(self, exist_items=None):
        """动态加载所选仓库大货可分配的最大整套数，并作为限额校验。"""
        import os
        _api_url = os.environ.get("API_URL", f"http://localhost:{os.environ.get('BACKEND_PORT', '8000')}")
        db = self.get_db()
        try:
            prod_service = ProductService(db)
            all_prods = prod_service.get_all_products()
            
            # 抓取仓库木桶原理可组装上限
            inv_service = InventoryService(db)
            wh_details = inv_service.get_warehouse_inventory_details()
            stock_in_wh = wh_details.get(self.tpl_wh_id, {}).get("stock", {})
            
            # 解析平台 code
            platform_code = "offline_cn"
            from models import SalesPlatform
            platform = db.query(SalesPlatform).filter(SalesPlatform.name == self.tpl_platform).first()
            if platform:
                platform_code = platform.code
                    
            exist_map = {}
            if exist_items:
                exist_map = {f"{i.product_name}_{i.variant}": (round(float(i.preset_price), 2), i.remaining_quantity) for i in exist_items}
                
            assign_list = []
            for p in all_prods:
                for c in p.colors:
                    key = f"{p.name}_{c.color_name}"
                    
                    # 计算可组装套数上限
                    reqs = {pt.part_name: pt.quantity for pt in c.parts} if c.parts else {"整套": 1}
                    pt_dict = stock_in_wh.get(p.name, {}).get(c.color_name, {})
                    possible_sets = 0
                    if reqs:
                        possible_sets = min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items())
                    max_stock = max(0, possible_sets)
                    
                    # 匹配售价
                    price = 0.0
                    if c.prices:
                        matched = next((pr.price for pr in c.prices if pr.platform == platform_code), None)
                        price = matched if matched is not None else next((pr.price for pr in c.prices if pr.currency == "CNY"), c.prices[0].price)
                        
                    is_in = False
                    qty = 0
                    if key in exist_map:
                        is_in = True
                        price, qty = exist_map[key]
                        
                    assign_list.append({
                        "product_name": p.name,
                        "variant": c.color_name,
                        "preset_price": round(float(price), 2),
                        "quantity": qty,
                        "max_stock": max_stock,
                        "is_selected": is_in,
                        "img_data": f"{_api_url}/color-image/{c.id}" if c.image_data else ""
                    })
            self.all_assignable_items = assign_list
        except Exception:
            pass
        finally:
            db.close()

    @rx.event
    def toggle_item_assign(self, prod_name: str, variant: str):
        for r in self.all_assignable_items:
            if r["product_name"] == prod_name and r["variant"] == variant:
                r["is_selected"] = not r["is_selected"]
                break
        self.all_assignable_items = list(self.all_assignable_items)

    @rx.event
    def update_item_assign_qty(self, prod_name: str, variant: str, val: str):
        try:
            qty_val = int(val) if val else 0
            for r in self.all_assignable_items:
                if r["product_name"] == prod_name and r["variant"] == variant:
                    if qty_val > r["max_stock"]:
                        qty_val = r["max_stock"]
                        # We cannot use rx.toast directly from standard backend loop, but returning a yield is fully supported!
                    r["quantity"] = qty_val
                    break
        except ValueError:
            pass
        self.all_assignable_items = list(self.all_assignable_items)

    @rx.event
    def update_item_assign_price(self, prod_name: str, variant: str, val: str):
        try:
            price_val = float(val) if val else 0.0
            for r in self.all_assignable_items:
                if r["product_name"] == prod_name and r["variant"] == variant:
                    r["preset_price"] = price_val
                    break
        except ValueError:
            pass
        self.all_assignable_items = list(self.all_assignable_items)


    @rx.event
    def save_template(self):
        """保存或更新收银模板配置。"""
        if not self.tpl_name.strip() or not self.tpl_code.strip():
            return rx.toast("请填写完整的模板名称和代号！", level="error")
            
        selected_rows = [r for r in self.all_assignable_items if r["is_selected"]]
        if not selected_rows:
            return rx.toast("请至少选择一项商品加入模板", level="error")
            
        # 组装入库参数
        items_data = [
            {"product_name": r["product_name"], "variant": r["variant"], "preset_price": r["preset_price"], "quantity": int(r["quantity"])}
            for r in selected_rows
        ]
        
        db = self.get_db()
        try:
            service = OfflineSalesService(db)
            if self.is_edit_mode:
                service.update_template(
                    self.tpl_id, self.tpl_name.strip(), self.tpl_code.strip(), 
                    self.tpl_currency, self.tpl_wh_id, self.tpl_platform, items_data
                )
                msg = "模板已成功修改并同步！"
            else:
                service.create_template(
                    self.tpl_name.strip(), self.tpl_code.strip(), 
                    self.tpl_currency, self.tpl_wh_id, self.tpl_platform, items_data
                )
                msg = "模板已开立成功！"
                
            self.load_templates_list(service)
            self.selected_template_id = self.templates[0].id
            self.load_template_orders(service)
            self._assignable_loaded = False  # 模板已更新，下次切换Tab时重新加载
            return rx.toast(msg)
        except Exception as e:
            return rx.toast(f"保存失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_template(self, tpl_id: int):
        db = self.get_db()
        try:
            service = OfflineSalesService(db)
            service.delete_template(tpl_id)
            self.load_templates_list(service)
            if self.templates:
                self.selected_template_id = self.templates[0].id
                self.load_template_orders(service)
            self._assignable_loaded = False  # 模板已删除，下次切换Tab时重新加载
            return rx.toast("收银模板已成功注销！")
        except Exception as e:
            return rx.toast(f"注销失败: {e}", level="error")
        finally:
            db.close()
