# yurara_app/state/inventory_state.py
"""
仓库库存管理 State 模块。
负责处理库存变动录入、成套木桶原理计算、散落部件统计与移库联动。
"""
import reflex as rx
from datetime import date
from pydantic import BaseModel
from typing import Any
from ..state.app_state import AppState
from services.inventory_service import InventoryService
from constants import PRODUCT_COST_CATEGORIES, StockLogReason
from models import Product, ProductColor, Warehouse


class InventoryStatRow(BaseModel):
    variant: str = ""
    planned: int = 0
    produced: int = 0
    inspecting: int = 0
    actual_qty: int = 0
    status: str = "🟢 有货"


class ExcessPartRow(BaseModel):
    variant: str = ""
    part_name: str = ""
    qty: int = 0


class InventoryLogModel(BaseModel):
    id: int = 0
    date: str = ""
    product_name: str = ""
    variant: str = ""
    part_display: str = ""
    warehouse_name: str = ""
    change_qty: float = 0.0
    reason: str = ""
    note: str = ""


class WarehouseItemModel(BaseModel):
    id: int = 0
    name: str = ""
    remarks: str = ""
    is_empty: bool = True


class WarehouseStockRow(BaseModel):
    product_name: str = ""
    variant: str = ""
    part_name: str = ""
    physical_qty: int = 0
    assemblable_sets: int = 0


class InventoryState(AppState):
    active_tab: str = "stock"  # "stock" 或 "warehouse"
    product_names: list[str] = []
    selected_product_name: str = ""
    wip_balance: float = 0.0
    is_production_completed: bool = False
    
    # 库存数据
    stats: list[InventoryStatRow] = []
    excess_parts: list[ExcessPartRow] = []
    logs: list[InventoryLogModel] = []
    
    # 仓库列表和仓库库存明细
    warehouses: list[WarehouseItemModel] = []
    warehouse_stocks: dict[str, list[WarehouseStockRow]] = {}  # key 是 str(warehouse_id)
    filtered_warehouse_stocks: dict[str, list[WarehouseStockRow]] = {}  # 过滤后的库存明细
    
    # 物理仓库明细商品筛选
    wh_filter_product: str = ""  # 空字符串 = 显示全部商品
    
    # 变动录入状态
    op_date: str = ""
    op_type: str = StockLogReason.IN_INSPECT
    op_wh_id: str = ""
    op_to_wh_id: str = ""
    op_wh_name: str = ""
    op_to_wh_name: str = ""
    op_variant: str = ""
    op_is_set: bool = True
    op_part: str = ""
    op_qty: int = 1
    op_out_mode: str = "消耗"  # "消耗" 或 "其他"
    op_cons_cat: str = PRODUCT_COST_CATEGORIES[0]
    op_cons_content: str = ""
    op_remark: str = ""
    
    # 新建仓库状态
    new_wh_name: str = ""
    new_wh_remarks: str = ""
    
    # 日志详情编辑状态
    is_log_edit_open: bool = False
    edit_log_id: int = 0
    edit_log_note: str = ""

    # ===================== 计算属性 =====================

    @rx.var
    def has_products(self) -> bool:
        return len(self.product_names) > 0

    @rx.var
    def all_movement_types(self) -> list[str]:
        return [
            StockLogReason.IN_INSPECT, 
            StockLogReason.INSPECT_COMPLETED, 
            StockLogReason.OTHER_IN, 
            StockLogReason.OUT_STOCK, 
            StockLogReason.TRANSFER
        ]

    @rx.var
    def is_transfer_mode(self) -> bool:
        return self.op_type == StockLogReason.TRANSFER

    @rx.var
    def is_out_mode(self) -> bool:
        return self.op_type == StockLogReason.OUT_STOCK

    @rx.var
    def is_consumable_out(self) -> bool:
        return self.is_out_mode and self.op_out_mode == "消耗"

    @rx.var
    def active_variants(self) -> list[str]:
        """选定商品的款式列表。"""
        if not self.selected_product_name:
            return ["通用"]
        db = self.get_db()
        try:
            prod = db.query(Product).filter(Product.name == self.selected_product_name).first()
            if not prod:
                return ["通用"]
            colors = db.query(ProductColor).filter(ProductColor.product_id == prod.id).order_by(ProductColor.id.asc()).all()
            if not colors:
                return ["通用"]
            return [c.color_name for c in colors]
        except Exception:
            return ["通用"]
        finally:
            db.close()

    @rx.var
    def active_parts(self) -> list[str]:
        """当前款式所拥有的部件列表。"""
        if not self.selected_product_name or not self.op_variant or self.op_variant == "通用":
            return ["通用"]
        db = self.get_db()
        try:
            prod = db.query(Product).filter(Product.name == self.selected_product_name).first()
            if not prod:
                return ["通用"]
            color = db.query(ProductColor).filter(
                ProductColor.product_id == prod.id, 
                ProductColor.color_name == self.op_variant
            ).first()
            if not color or not color.parts:
                return ["通用"]
            return [p.part_name for p in color.parts]
        except Exception:
            return ["通用"]
        finally:
            db.close()

    @rx.var
    def has_parts_for_color(self) -> bool:
        """款式是否已经拆分了部件，用于控制是否渲染“整套操作”的复选框。"""
        return len(self.active_parts) > 0 and self.active_parts[0] != "通用"

    @rx.var
    def warehouse_options(self) -> list[str]:
        """仓库选择列表"""
        return [w.name for w in self.warehouses]

    @rx.var
    def transfer_warehouse_options(self) -> list[str]:
        """带“未分配仓库 (旧数据)”的仓库源列表，用于移出仓库的下拉选择。"""
        opts = ["未分配仓库 (旧数据)"]
        opts.extend(self.warehouse_options)
        return opts

    @rx.var
    def cost_categories(self) -> list[str]:
        return PRODUCT_COST_CATEGORIES

    @rx.var
    def has_excess_parts(self) -> bool:
        return len(self.excess_parts) > 0

    @rx.var
    def wip_balance_str(self) -> str:
        return f"¥ {self.wip_balance:,.2f}"

    @rx.var
    def wh_product_options(self) -> list[str]:
        """物理仓库明细商品筛选选项（含"全部商品"）。"""
        return ["全部商品"] + self.product_names

    @rx.var
    def wh_filter_display(self) -> str:
        """当前筛选显示名（用于 select 控件的 value）。"""
        return self.wh_filter_product if self.wh_filter_product else "全部商品"

    # ===================== 事件处理器 =====================

    @rx.event
    async def load_inventory_page(self):
        """初始化加载库存主页面。"""
        if not await self.is_authenticated_user():
            return
        self.op_date = date.today().strftime("%Y-%m-%d")
        db = self.get_db()
        try:
            service = InventoryService(db)
            products = service.get_all_products()
            self.product_names = [p.name for p in products]
            if self.product_names and not self.selected_product_name:
                self.selected_product_name = self.product_names[0]
                
            self.load_warehouse_list(service)
            if self.selected_product_name:
                self.load_current_inventory(service)
        finally:
            db.close()

    @rx.event
    def select_tab(self, tab_name: str):
        """切换标签页。"""
        self.active_tab = tab_name
        db = self.get_db()
        try:
            service = InventoryService(db)
            self.load_warehouse_list(service)
        finally:
            db.close()

    @rx.event
    def select_product(self, prod_name: str):
        """切换所选择的分析商品。"""
        self.selected_product_name = prod_name
        db = self.get_db()
        try:
            service = InventoryService(db)
            self.load_current_inventory(service)
        finally:
            db.close()

    def load_warehouse_list(self, service: InventoryService):
        """加载所有的仓库列表以及各仓库的库存明细。"""
        whs = service.get_all_warehouses()
        
        # 获取底层库存明细
        wh_details = service.get_warehouse_inventory_details()
        
        wh_list = []
        stocks_dict = {}
        
        # 1. 遍历物理仓库
        for w in whs:
            stock_rows = []
            w_stock = wh_details.get(w.id, {}).get("stock", {})
            
            # 以木桶原理计算能凑出的整套数
            for prod_n, v_dict in w_stock.items():
                for var_n, pt_dict in v_dict.items():
                    # 动态匹配部件配比
                    prod_obj = service.db.query(Product).filter(Product.name == prod_n).first()
                    reqs = {"整套": 1}
                    if prod_obj:
                        color_obj = next((c for c in prod_obj.colors if c.color_name == var_n), None)
                        if color_obj and color_obj.parts:
                            reqs = {p.part_name: p.quantity for p in color_obj.parts}
                    
                    possible_sets = 0
                    if reqs:
                        possible_sets = min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items())
                        
                    for pt_n, qty in pt_dict.items():
                        if qty != 0:
                            stock_rows.append(WarehouseStockRow(
                                product_name=prod_n,
                                variant=var_n,
                                part_name=pt_n,
                                physical_qty=qty,
                                assemblable_sets=max(0, possible_sets)
                            ))
            
            wh_list.append(WarehouseItemModel(
                id=w.id,
                name=w.name,
                remarks=w.remarks or "",
                is_empty=(len(stock_rows) == 0)
            ))
            stocks_dict[str(w.id)] = stock_rows
            
        self.warehouses = wh_list
        self.warehouse_stocks = stocks_dict
        self._apply_wh_filter()

    def load_current_inventory(self, service: InventoryService):
        """拉取指定商品的在制资产、款式生产进度表、操作日志。"""
        prod = service.db.query(Product).filter(Product.name == self.selected_product_name).first()
        if not prod:
            return
            
        self.wip_balance = service.get_wip_balance(prod.id)
        self.is_production_completed = prod.is_production_completed or False
        
        # 1. 部件维度的进度表计算
        stats_map = service.get_stock_overview_by_parts(prod.id, prod.name)
        stats_list = []
        excess_list = []
        
        for c in prod.colors:
            v_name = c.color_name
            s = stats_map.get(v_name, {})
            planned = s.get("planned", 0)
            produced = s.get("produced", 0)
            inspecting = s.get("inspecting", 0)
            actual_qty = s.get("actual", 0)
            status = "🔴 缺货" if actual_qty <= 0 else "🟢 有货"
            
            stats_list.append(InventoryStatRow(
                variant=v_name,
                planned=planned,
                produced=produced,
                inspecting=inspecting,
                actual_qty=actual_qty,
                status=status
            ))
            
            # 多余部件
            for pt, qty in s.get("excess", {}).items():
                excess_list.append(ExcessPartRow(
                    variant=v_name,
                    part_name=pt,
                    qty=qty
                ))
                
        self.stats = stats_list
        self.excess_parts = excess_list
        
        # 2. 拉取日志
        logs_list = []
        whs_map = {w.id: w.name for w in service.db.query(Warehouse).all()}
        
        logs = service.get_recent_logs(prod.name)
        for l in logs:
            part_display = l.part_name if l.part_name else "[成套]"
            wh_display = whs_map.get(l.warehouse_id, "未分配仓库")
            logs_list.append(InventoryLogModel(
                id=l.id,
                date=l.date.strftime("%Y-%m-%d") if l.date else "",
                product_name=l.product_name,
                variant=l.variant,
                part_display=part_display,
                warehouse_name=wh_display,
                change_qty=l.change_amount,
                reason=l.reason,
                note=l.note or ""
            ))
        self.logs = logs_list
        
        # 默认重置款式表单
        if self.active_variants and self.op_variant not in self.active_variants:
            self.op_variant = self.active_variants[0]
        if self.warehouse_options and not self.op_wh_name:
            self.op_wh_name = self.warehouse_options[0]
            self.op_wh_id = str(self.warehouses[0].id)
            self.op_to_wh_name = self.warehouse_options[0]
            self.op_to_wh_id = str(self.warehouses[0].id)

    def _apply_wh_filter(self):
        """根据 wh_filter_product 对 warehouse_stocks 进行过滤，结果写入 filtered_warehouse_stocks。"""
        if not self.wh_filter_product or self.wh_filter_product == "全部商品":
            self.filtered_warehouse_stocks = dict(self.warehouse_stocks)
        else:
            filtered = {}
            for wh_id, rows in self.warehouse_stocks.items():
                filtered[wh_id] = [r for r in rows if r.product_name == self.wh_filter_product]
            self.filtered_warehouse_stocks = filtered

    @rx.event
    def set_wh_filter_product(self, val: str):
        """切换物理仓库明细的商品筛选。"""
        self.wh_filter_product = val if val != "全部商品" else ""
        self._apply_wh_filter()

    # --- 录入事件相关 Setter ---
    @rx.event
    def set_op_date(self, val: str): self.op_date = val
    @rx.event
    def set_op_type(self, val: str): self.op_type = val
    @rx.event
    def set_op_wh_name(self, name: str):
        self.op_wh_name = name
        db = self.get_db()
        try:
            wh = db.query(Warehouse).filter(Warehouse.name == name).first()
            if wh:
                self.op_wh_id = str(wh.id)
            else:
                self.op_wh_id = "None"
        finally:
            db.close()

    @rx.event
    def set_op_to_wh_name(self, name: str):
        self.op_to_wh_name = name
        if name == "未分配仓库 (旧数据)":
            self.op_to_wh_id = "None"
            return
        db = self.get_db()
        try:
            wh = db.query(Warehouse).filter(Warehouse.name == name).first()
            if wh:
                self.op_to_wh_id = str(wh.id)
            else:
                self.op_to_wh_id = "None"
        finally:
            db.close()
    @rx.event
    def set_op_variant(self, val: str): self.op_variant = val
    @rx.event
    def set_op_is_set(self, val: bool): self.op_is_set = val
    @rx.event
    def set_op_part(self, val: str): self.op_part = val
    @rx.event
    def set_op_qty(self, val: str):
        try: self.op_qty = int(val) if val else 1
        except ValueError: pass
    @rx.event
    def set_op_out_mode(self, val: str): self.op_out_mode = val
    @rx.event
    def set_op_cons_cat(self, val: str): self.op_cons_cat = val
    @rx.event
    def set_op_cons_content(self, val: str): self.op_cons_content = val
    @rx.event
    def set_op_remark(self, val: str): self.op_remark = val

    @rx.event
    def clear_product_wip(self):
        """一键清零在制资产。"""
        if not self.selected_product_name:
            return rx.toast("请选择商品", level="error")
        db = self.get_db()
        try:
            service = InventoryService(db)
            prod = db.query(Product).filter(Product.name == self.selected_product_name).first()
            service.clear_wip_for_product(prod.id)
            self.load_current_inventory(service)
            
            # 刷新大货缓存
            from cache_manager import sync_all_caches
            sync_all_caches()
            return rx.toast("在制资产清零成功，预计销售数与大货重算完成！")
        except Exception as e:
            return rx.toast(f"操作失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def submit_inventory_movement(self):
        """提交库存移动记录，并在库存/财务中产生多方联动。"""
        if not self.selected_product_name:
            return rx.toast("请先选择商品", level="error")
        if self.is_consumable_out and not self.op_cons_content.strip():
            return rx.toast("请填写【消耗内容】", level="error")
            
        db = self.get_db()
        try:
            service = InventoryService(db)
            prod = db.query(Product).filter(Product.name == self.selected_product_name).first()
            
            # 转化仓库 id
            wh_id = int(self.op_wh_id) if self.op_wh_id and self.op_wh_id != "None" else None
            to_wh_id = int(self.op_to_wh_id) if self.op_to_wh_id and self.op_to_wh_id != "None" else None
            
            # 日期对象
            try:
                date_val = date.fromisoformat(self.op_date)
            except Exception:
                date_val = date.today()
                
            msg = service.add_inventory_movement(
                product_id=prod.id,
                product_name=prod.name,
                variant=self.op_variant,
                quantity=self.op_qty,
                move_type=self.op_type,
                date_obj=date_val,
                remark=self.op_remark.strip(),
                warehouse_id=wh_id,
                to_warehouse_id=to_wh_id,
                is_set=self.op_is_set if self.has_parts_for_color else True,
                part_name=self.op_part if (not self.op_is_set and self.has_parts_for_color) else None,
                out_type=self.op_out_mode,
                cons_cat=self.op_cons_cat,
                cons_content=self.op_cons_content.strip()
            )
            
            service.commit()
            
            # 刷新
            self.load_current_inventory(service)
            self.load_warehouse_list(service)
            
            # 重置特殊表单
            self.op_remark = ""
            self.op_cons_content = ""
            
            # 同步缓存
            from cache_manager import sync_all_caches
            sync_all_caches()
            
            return rx.toast(msg)
        except Exception as e:
            db.rollback()
            return rx.toast(f"提交失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_log_cascade(self, log_id: int):
        """级联回滚删除某条库存记录。"""
        db = self.get_db()
        try:
            service = InventoryService(db)
            msg = service.delete_log_cascade(log_id)
            self.load_current_inventory(service)
            self.load_warehouse_list(service)
            
            from cache_manager import sync_all_caches
            sync_all_caches()
            return rx.toast(f"级联删除成功: {msg}")
        except Exception as e:
            db.rollback()
            return rx.toast(f"删除失败: {e}", level="error")
        finally:
            db.close()

    # --- 仓库配置 Setter 与动作 ---
    @rx.event
    def set_new_wh_name(self, val: str): self.new_wh_name = val
    @rx.event
    def set_new_wh_remarks(self, val: str): self.new_wh_remarks = val

    @rx.event
    def add_warehouse(self):
        """创建新物理仓库。"""
        if not self.new_wh_name.strip():
            return rx.toast("仓库名称不能为空", level="error")
        db = self.get_db()
        try:
            service = InventoryService(db)
            service.add_warehouse(self.new_wh_name.strip(), self.new_wh_remarks.strip())
            self.new_wh_name = ""
            self.new_wh_remarks = ""
            self.load_warehouse_list(service)
            return rx.toast("仓库开立成功！")
        except Exception as e:
            return rx.toast(f"开立失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_warehouse(self, wh_id: int):
        """物理删除一个完全为空的仓库。"""
        db = self.get_db()
        try:
            service = InventoryService(db)
            service.delete_warehouse(wh_id)
            self.load_warehouse_list(service)
            return rx.toast("仓库已成功注销！")
        except Exception as e:
            return rx.toast(f"注销失败: {e}", level="error")
        finally:
            db.close()

    # --- 日志备注详情编辑 ---
    @rx.event
    def open_log_edit(self, log: dict):
        self.edit_log_id = log["id"]
        self.edit_log_note = log["note"]
        self.is_log_edit_open = True
        
    @rx.event
    def close_log_edit(self):
        self.is_log_edit_open = False
        
    @rx.event
    def set_edit_log_note(self, val: str):
        self.edit_log_note = val

    @rx.event
    def submit_log_edit(self):
        """更新库存备注。"""
        db = self.get_db()
        try:
            service = InventoryService(db)
            changes = {self.edit_log_id: {"详情": self.edit_log_note.strip()}}
            service.update_logs_batch(changes)
            self.is_log_edit_open = False
            self.load_current_inventory(service)
            return rx.toast("备注已更新！")
        except Exception as e:
            return rx.toast(f"更新失败: {e}", level="error")
        finally:
            db.close()
