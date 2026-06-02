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


class OfflineSalesState(AppState):
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

    # ===================== 计算属性 =====================

    @rx.var
    def has_templates(self) -> bool:
        return len(self.templates) > 0

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
        if curr == "JPY":
            return f"{self.cart_total:,.0f} JPY"
        return f"¥ {self.cart_total:,.2f}"

    @rx.var
    def paypay_fee_str(self) -> str:
        curr = self.active_template.currency if self.active_template else "CNY"
        if curr == "JPY":
            return f"{self.paypay_fee:,.0f} JPY"
        return f"¥ {self.paypay_fee:,.2f}"

    @rx.var
    def paypay_receive_str(self) -> str:
        curr = self.active_template.currency if self.active_template else "CNY"
        if curr == "JPY":
            return f"{self.paypay_estimated_receive:,.0f} JPY"
        return f"¥ {self.paypay_estimated_receive:,.2f}"

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
        return list(PLATFORM_CODES.values())

    @rx.var
    def is_cart_empty(self) -> bool:
        return len(self.cart) == 0

    # ===================== 事件处理器 =====================

    @rx.event
    def load_offline_page(self):
        """初始化加载展会收银页面。"""
        db = self.get_db()
        try:
            service = OfflineSalesService(db)
            self.load_templates_list(service)
            if self.templates and not self.selected_template_id:
                self.selected_template_id = self.templates[0].id
                
            if self.selected_template_id:
                self.load_template_orders(service)
            
            # 自动初始化加载可分配的商品大货列表，防止切换至模板配置Tab时内容为空
            self.open_create_template()
        finally:
            db.close()

    @rx.event
    def select_tab(self, tab_name: str):
        self.active_tab = tab_name

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
        tpls = service.get_all_templates()
        prod_service = ProductService(service.db)
        all_prods = prod_service.get_all_products()
        img_lookup = {f"{p.name}_{c.color_name}": c.image_data or "" for p in all_prods for c in p.colors}
        
        # 抓取仓库木桶原理真实大货可组装库存限额
        inv_service = InventoryService(service.db)
        wh_details = inv_service.get_warehouse_inventory_details()
        
        # 缓存所有产品，以避免在循环中对每个模板项执行 N+1 数据库查询
        prod_lookup = {p.name: p for p in all_prods}
        
        tpl_list = []
        for t in tpls:
            stock_in_wh = wh_details.get(t.warehouse_id, {}).get("stock", {})
            
            items_list = []
            for item in t.items:
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
    def add_to_cart(self, prod_name: str, variant: str, price: float, max_qty: int, image_data: str):
        """加购逻辑：检查模板数量余量及库存上限。"""
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
        
        db = self.get_db()
        try:
            whs = db.query(Warehouse).all()
            self.tpl_wh_id = whs[0].id if whs else 0
            self.tpl_wh_name = whs[0].name if whs else ""
            self.load_assignable_stocks()
        finally:
            db.close()

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
            for k, v in PLATFORM_CODES.items():
                if v == self.tpl_platform:
                    platform_code = k
                    break
                    
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
                        "img_data": c.image_data or ""
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
            return rx.toast("收银模板已成功注销！")
        except Exception as e:
            return rx.toast(f"注销失败: {e}", level="error")
        finally:
            db.close()
