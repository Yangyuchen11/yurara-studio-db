# yurara_app/state/cost_state.py
"""
商品成本核算 State 模块。
包含服务端数值计算与各款式多平台毛利矩阵的逆推折算。
"""
import reflex as rx
import math
from pydantic import BaseModel
from typing import Any
from ..state.app_state import AppState
from services.cost_service import CostService
from constants import PRODUCT_COST_CATEGORIES


class CostItemModel(BaseModel):
    id: int = 0
    item_name: str = ""
    category: str = ""
    unit: str = ""
    currency: str = "CNY"
    quantity: float = 0.0
    unit_price: float = 0.0
    actual_cost: float = 0.0
    original_amount: float = 0.0
    supplier: str = ""
    url: str = ""
    remarks: str = ""
    is_budget: bool = False


class ProfitReferenceRow(BaseModel):
    color_name: str = ""
    platform_label: str = ""
    preset_price: float = 0.0
    price_currency: str = "CNY"
    price_cny: float = 0.0
    estimated_fee_cny: float = 0.0
    margin_cny: float = 0.0
    margin_rate: float = 0.0
    expected_total_profit: float = 0.0
    quantity: float = 0.0
    preset_price_str: str = ""
    estimated_fee_cny_str: str = ""
    margin_cny_str: str = ""
    margin_rate_str: str = ""
    expected_total_profit_str: str = ""



class CostState(AppState):
    product_names: list[str] = []
    selected_product_name: str = ""
    make_qty: float = 0.0
    cost_items: list[CostItemModel] = []
    wip_offset: float = 0.0
    is_production_completed: bool = False
    
    # 预算添加状态
    b_cat: str = PRODUCT_COST_CATEGORIES[0]
    b_name: str = ""
    b_unit_price: float = 0.0
    b_qty: float = 1.0
    b_unit_text: str = ""
    b_remarks: str = ""
    
    # 明细编辑状态
    is_edit_open: bool = False
    edit_item_id: int = 0
    edit_name: str = ""
    edit_category: str = ""
    edit_unit: str = ""
    edit_supplier: str = ""
    edit_url: str = ""
    edit_remarks: str = ""
    edit_qty: float = 0.0
    edit_unit_price: float = 0.0
    edit_actual_cost: float = 0.0
    edit_is_budget: bool = False

    # ===================== 计算属性 =====================

    @rx.var
    def has_products(self) -> bool:
        return len(self.product_names) > 0

    @rx.var
    def all_categories(self) -> list[str]:
        return PRODUCT_COST_CATEGORIES

    @rx.var
    def detailed_categories(self) -> list[str]:
        return PRODUCT_COST_CATEGORIES[:4]

    @rx.var
    def is_detailed_b_cat(self) -> bool:
        return self.b_cat in self.detailed_categories

    @rx.var
    def budget_total_val(self) -> float:
        return self.b_unit_price * self.b_qty

    @rx.var
    def budget_total_val_str(self) -> str:
        return f"¥ {self.budget_total_val:,.2f}"

    @rx.var
    def total_real_cost(self) -> float:
        """项目实付总支出。"""
        return sum(item.actual_cost for item in self.cost_items)

    @rx.var
    def total_budget_cost(self) -> float:
        """预算总成本。"""
        budget_map = {
            item.item_name: item.unit_price * item.quantity 
            for item in self.cost_items if item.supplier == "预算设定"
        }
        total_b = sum(budget_map.values())
        for item in self.cost_items:
            if item.supplier != "预算设定" and item.item_name not in budget_map:
                total_b += item.actual_cost
        return total_b

    @rx.var
    def unit_real_cost(self) -> float:
        """单套实付成本。"""
        if self.make_qty > 0:
            return self.total_real_cost / self.make_qty
        return 0.0

    @rx.var
    def unit_budget_cost(self) -> float:
        """单套预算成本。"""
        if self.make_qty > 0:
            return self.total_budget_cost / self.make_qty
        return 0.0

    @rx.var
    def remaining_wip(self) -> float:
        """当前在制资产。"""
        return self.total_real_cost + self.wip_offset

    # --- 字符串格式化方便渲染 ---
    @rx.var
    def total_real_cost_str(self) -> str: return f"¥ {self.total_real_cost:,.2f}"
    @rx.var
    def total_budget_cost_str(self) -> str: return f"¥ {self.total_budget_cost:,.2f}"
    @rx.var
    def unit_real_cost_str(self) -> str: return f"¥ {self.unit_real_cost:,.2f}"
    @rx.var
    def unit_budget_cost_str(self) -> str: return f"¥ {self.unit_budget_cost:,.2f}"
    @rx.var
    def remaining_wip_str(self) -> str: return f"¥ {self.remaining_wip:,.2f}"
    @rx.var
    def make_qty_str(self) -> str: return f"{int(self.make_qty)} 件"

    # --- 分组支出数据模型 ---
    @rx.var
    def grouped_cost_items(self) -> dict[str, list[dict[str, Any]]]:
        """将支出明细按类别分组输出给前端表格，防止前端进行复杂的 dict 处理。"""
        grouped = {cat: [] for cat in PRODUCT_COST_CATEGORIES}
        for item in self.cost_items:
            # 兼容检品发货等人工费搜索
            cat = item.category
            if "检品" in cat and "人工费" in cat:
                cat = "检品发货等人工费"
            if cat not in grouped:
                grouped[cat] = []
            
            is_budget_item = (item.supplier == "预算设定")
            budget_qty = item.quantity if is_budget_item else None
            budget_unit_price = item.unit_price if is_budget_item else None
            budget_total = (item.unit_price * item.quantity) if is_budget_item else None
            actual_qty = item.quantity if not is_budget_item else None
            actual_total = item.original_amount
            actual_unit_price = (item.original_amount / item.quantity) if (not is_budget_item and item.quantity > 0) else None

            grouped[cat].append({
                "id": item.id,
                "item_name": item.item_name,
                "unit": item.unit,
                "currency": item.currency,
                "budget_qty": budget_qty or 0,
                "budget_unit_price": budget_unit_price or 0,
                "budget_total": budget_total or 0,
                "actual_qty": actual_qty or 0,
                "actual_unit_price": actual_unit_price or 0,
                "actual_total": actual_total or 0,
                "supplier": item.supplier or "",
                "url": item.url or "",
                "remarks": item.remarks or "",
                "is_budget": is_budget_item,
                # 预先格式化为字符串
                "budget_qty_str": f"{budget_qty:.2f}" if budget_qty else "-",
                "budget_price_str": f"¥ {budget_unit_price:,.2f}" if budget_unit_price else "-",
                "budget_total_str": f"¥ {budget_total:,.2f}" if budget_total else "-",
                "actual_qty_str": f"{actual_qty:.2f}" if actual_qty else "-",
                "actual_price_str": f"¥ {actual_unit_price:,.2f}" if actual_unit_price else "-",
                "actual_total_str": f"{item.currency} {actual_total:,.2f}" if actual_total else "-",
            })
        return grouped

    @rx.var
    def category_subtotals(self) -> dict[str, dict[str, Any]]:
        """计算各科目的实际和预算小计，并在后端格式化。"""
        subtotals = {}
        for cat in PRODUCT_COST_CATEGORIES:
            # 兼容检品发货等人工费搜索
            cat_items = [
                i for i in self.cost_items 
                if i.category == cat or (cat == "检品发货等人工费" and "检品" in i.category)
            ]
            real_total = sum(i.actual_cost for i in cat_items)
            
            budget_map = {
                i.item_name: i.unit_price * i.quantity 
                for i in cat_items if i.supplier == "预算设定"
            }
            budget_total = sum(budget_map.values())
            for i in cat_items:
                if i.supplier != "预算设定" and i.item_name not in budget_map:
                    budget_total += i.actual_cost
                    
            real_unit = real_total / self.make_qty if self.make_qty > 0 else 0.0
            budget_unit = budget_total / self.make_qty if self.make_qty > 0 else 0.0
            
            subtotals[cat] = {
                "real_str": f"¥ {real_total:,.2f}",
                "budget_str": f"¥ {budget_total:,.2f}",
                "real_unit_str": f"¥ {real_unit:,.2f}",
                "budget_unit_str": f"¥ {budget_unit:,.2f}"
            }
        return subtotals


    @rx.var
    def profit_references(self) -> list[ProfitReferenceRow]:
        """按款式计算各平台毛利参考的表格数据。"""
        if self.make_qty <= 0 or not self.selected_product_name:
            return []

        db = self.get_db()
        try:
            service = CostService(db)
            prod = service.get_product_by_name(self.selected_product_name)
            if not prod:
                return []

            platforms_config = [
                ("weidian", "微店 (CNY)", False), 
                ("offline_cn", "中国线下 (CNY)", False),
                ("other", "其他 (CNY)", False), 
                ("booth", "Booth (JPY)", True),
                ("instagram", "Instagram (JPY)", True), 
                ("offline_jp", "日本线下 (JPY)", True),
                ("other_jpy", "其他 (JPY)", True),
            ]

            results = []
            unit_real = self.unit_real_cost
            rate = self.exchange_rate

            for color in prod.colors:
                for pf_key, label, is_jpy in platforms_config:
                    # 获取该款式该平台的定价
                    price_val = 0.0
                    if color.prices:
                        for p in color.prices:
                            if p.platform == pf_key:
                                price_val = p.price
                                break
                    
                    if price_val > 0:
                        fee_val = 0.0
                        if pf_key == "weidian":
                            fee_val = price_val * 0.006 
                        elif pf_key == "booth":
                            fee_val = math.ceil(price_val * 0.056 + 22) 
                            
                        price_cny = price_val * rate if is_jpy else price_val
                        fee_cny = fee_val * rate if is_jpy else fee_val
                        
                        margin = price_cny - fee_cny - unit_real
                        margin_rate = (margin / price_cny * 100) if price_cny > 0 else 0.0
                        total_profit = margin * color.quantity

                        results.append(ProfitReferenceRow(
                            color_name=color.color_name,
                            platform_label=label,
                            preset_price=price_val,
                            price_currency="JPY" if is_jpy else "CNY",
                            price_cny=price_cny,
                            estimated_fee_cny=fee_cny,
                            margin_cny=margin,
                            margin_rate=margin_rate,
                            expected_total_profit=total_profit,
                            quantity=color.quantity,
                            preset_price_str=f"{price_val:,.0f} JPY" if is_jpy else f"¥ {price_val:,.2f}",
                            estimated_fee_cny_str=f"¥ {fee_cny:,.2f}",
                            margin_cny_str=f"¥ {margin:,.2f}",
                            margin_rate_str=f"{margin_rate:.1f}%",
                            expected_total_profit_str=f"¥ {total_profit:,.2f}"
                        ))
            return results
        except Exception:
            return []
        finally:
            db.close()

    # ===================== 事件处理器 =====================

    @rx.event
    def load_cost_page(self):
        """拉取所有商品列表，并默认载入第一个商品。"""
        db = self.get_db()
        try:
            service = CostService(db)
            products = service.get_all_products()
            self.product_names = [p.name for p in products]
            if self.product_names and not self.selected_product_name:
                self.selected_product_name = self.product_names[0]
            
            if self.selected_product_name:
                self.load_current_product_costs(service)
        finally:
            db.close()

    @rx.event
    def select_product(self, prod_name: str):
        """选择核算商品。"""
        self.selected_product_name = prod_name
        db = self.get_db()
        try:
            service = CostService(db)
            self.load_current_product_costs(service)
        finally:
            db.close()

    def load_current_product_costs(self, service: CostService):
        """从服务加载当前商品明细。"""
        prod = service.get_product_by_name(self.selected_product_name)
        if not prod:
            return
        
        self.make_qty = prod.marketable_quantity if prod.marketable_quantity is not None else prod.total_quantity
        self.is_production_completed = prod.is_production_completed or False
        
        # 加载 WIP offset
        self.wip_offset = service.get_wip_offset(prod.id)
        
        # 载入所有的支出与预算条目
        items = service.get_cost_items(prod.id)
        cost_list = []
        for i in items:
            curr = getattr(i, 'currency', None) or "CNY"
            orig_amt = getattr(i, 'original_amount', None)
            if orig_amt is None:
                orig_amt = i.actual_cost

            cost_list.append(CostItemModel(
                id=i.id,
                item_name=i.item_name,
                category=i.category,
                unit=i.unit or "",
                currency=curr,
                quantity=i.quantity or 0.0,
                unit_price=i.unit_price or 0.0,
                actual_cost=i.actual_cost or 0.0,
                original_amount=orig_amt or 0.0,
                supplier=i.supplier or "",
                url=i.url or "",
                remarks=i.remarks or "",
                is_budget=(i.supplier == "预算设定")
            ))
        self.cost_items = cost_list

    # --- 预算添加相关 Setter ---
    @rx.event
    def set_b_cat(self, val: str): self.b_cat = val
    @rx.event
    def set_b_name(self, val: str): self.b_name = val
    @rx.event
    def set_b_unit_price(self, val: str):
        try: self.b_unit_price = float(val) if val else 0.0
        except ValueError: pass
    @rx.event
    def set_b_qty(self, val: str):
        try: self.b_qty = float(val) if val else 1.0
        except ValueError: pass
    @rx.event
    def set_b_unit_text(self, val: str): self.b_unit_text = val
    @rx.event
    def set_b_remarks(self, val: str): self.b_remarks = val

    @rx.event
    def add_budget_item(self):
        """保存预算项目。"""
        if not self.b_name.strip():
            return rx.toast("请输入预算项目名称", level="error")
        if not self.selected_product_name:
            return rx.toast("请先选择商品", level="error")
            
        db = self.get_db()
        try:
            service = CostService(db)
            prod = service.get_product_by_name(self.selected_product_name)
            
            # 计算总价
            qty = self.b_qty if self.is_detailed_b_cat else 1.0
            price = self.b_unit_price
            
            service.add_budget_item(
                product_id=prod.id,
                category=self.b_cat,
                name=self.b_name.strip(),
                unit_price=price,
                quantity=qty,
                unit=self.b_unit_text if self.is_detailed_b_cat else "",
                remarks=self.b_remarks.strip()
            )
            
            # 重置表单
            self.b_name = ""
            self.b_unit_price = 0.0
            self.b_qty = 1.0
            self.b_unit_text = ""
            self.b_remarks = ""
            
            # 刷新
            self.load_current_product_costs(service)
            return rx.toast("预算项目添加成功！")
        except Exception as e:
            return rx.toast(f"保存失败: {e}", level="error")
        finally:
            db.close()

    # --- 行编辑相关 ---
    @rx.event
    def open_edit_dialog(self, item: dict):
        """拉起行编辑对话框并将明细读入状态。"""
        self.edit_item_id = item["id"]
        self.edit_name = item["item_name"]
        self.edit_category = item["category"]
        self.edit_unit = item["unit"]
        self.edit_supplier = item["supplier"]
        self.edit_url = item["url"]
        self.edit_remarks = item["remarks"]
        self.edit_qty = item["budget_qty"] if item["is_budget"] else item["actual_qty"]
        self.edit_unit_price = item["budget_unit_price"] if item["is_budget"] else item["actual_unit_price"]
        self.edit_is_budget = item["is_budget"]
        self.is_edit_open = True

    @rx.event
    def close_edit_dialog(self):
        self.is_edit_open = False

    @rx.event
    def set_edit_unit(self, val: str): self.edit_unit = val
    @rx.event
    def set_edit_supplier(self, val: str): self.edit_supplier = val
    @rx.event
    def set_edit_url(self, val: str): self.edit_url = val
    @rx.event
    def set_edit_remarks(self, val: str): self.edit_remarks = val
    @rx.event
    def set_edit_qty(self, val: str):
        try: self.edit_qty = float(val) if val else 0.0
        except ValueError: pass
    @rx.event
    def set_edit_unit_price(self, val: str):
        try: self.edit_unit_price = float(val) if val else 0.0
        except ValueError: pass

    @rx.event
    def submit_edit_cost_item(self):
        """提交编辑更改。"""
        db = self.get_db()
        try:
            service = CostService(db)
            updates = {
                "unit": self.edit_unit.strip(),
                "supplier": self.edit_supplier.strip(),
                "url": self.edit_url.strip(),
                "remarks": self.edit_remarks.strip(),
                "is_budget": self.edit_is_budget
            }
            if self.edit_is_budget:
                updates["quantity"] = self.edit_qty
                updates["unit_price"] = self.edit_unit_price
                
            service.update_cost_item(self.edit_item_id, updates)
            self.is_edit_open = False
            self.load_current_product_costs(service)
            return rx.toast("项目修改已保存！")
        except Exception as e:
            return rx.toast(f"更新失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_cost_item(self, item_id: int):
        """物理删除成本项目，如有付款则回滚现金。"""
        db = self.get_db()
        try:
            service = CostService(db)
            service.delete_cost_item(item_id)
            self.load_current_product_costs(service)
            return rx.toast("记录删除成功！联动现金与库存指标已回退。")
        except Exception as e:
            return rx.toast(f"删除失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def wip_completed_fix(self):
        """生产结单并清零在制资产。"""
        if not self.selected_product_name:
            return rx.toast("请选择商品", level="error")
            
        db = self.get_db()
        try:
            service = CostService(db)
            prod = service.get_product_by_name(self.selected_product_name)
            service.perform_wip_fix(prod.id)
            self.load_current_product_costs(service)
            
            # 刷新全局缓存
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            return rx.toast("生产完成结单成功！在制已清存，大货资产已就绪。")
        except Exception as e:
            return rx.toast(f"操作失败: {e}", level="error")
        finally:
            db.close()
