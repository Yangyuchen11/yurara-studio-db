# yurara_app/state/inventory_state.py
"""
仓库库存管理 State 模块。
负责处理库存变动录入、成套木桶原理计算、散落部件统计与移库联动。
"""
import reflex as rx
from datetime import date
import math
from pydantic import BaseModel
from typing import Any
from ..state.app_state import AppState
from services.inventory_service import InventoryService
from constants import PRODUCT_COST_CATEGORIES, StockLogReason
from models import Product, ProductColor, Warehouse


class PartStatRow(BaseModel):
    part_name: str = ""
    req_qty: int = 1
    produced: int = 0
    inspecting: int = 0
    repaired: int = 0
    actual_qty: int = 0
    calculable_sets: int = 0


class InventoryStatRow(BaseModel):
    variant: str = ""
    planned: int = 0
    produced: int = 0
    inspecting: int = 0
    repaired: int = 0
    actual_qty: int = 0
    status: str = "🟢 有货"
    parts: list[PartStatRow] = []


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


class BatchSetRow(BaseModel):
    key: str = ""
    variant: str = ""
    planned: int = 0
    stock_display: str = ""
    input_val: str = ""


class BatchPartRow(BaseModel):
    key: str = ""
    variant: str = ""
    part_name: str = ""
    req_qty: int = 1
    stock_display: str = ""
    input_val: str = ""


class InventoryState(AppState):
    active_tab: str = "stock"  # "stock" 或 "warehouse"
    product_names: list[str] = []
    selected_product_name: str = ""
    wip_balance: float = 0.0
    is_production_completed: bool = False
    
    # 展开款式部件明细
    expanded_variant: str = ""
    
    # 库存数据
    stats: list[InventoryStatRow] = []
    excess_parts: list[ExcessPartRow] = []
    logs: list[InventoryLogModel] = []

    # 物理变动日志筛选与分页状态
    log_filter_product: str = "全部商品"
    log_filter_variant: str = "全部款式"
    log_filter_spec: str = "全部规格"
    log_filter_warehouse: str = "全部仓库"
    log_filter_reason: str = "全部类型"
    log_filter_date_start: str = ""
    log_filter_date_end: str = ""
    log_filter_search: str = ""
    log_page_index: int = 1
    log_page_size: int = 20
    
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
    op_auto_inspect_complete: bool = False  # 勾选时一键连贯完成【入库验收】+【验收完成入库】

    # 批量录入矩阵状态
    batch_mode: str = "set"  # "set"(成套) 或 "part"(散件)
    batch_inputs: dict[str, str] = {}
    
    # 新建仓库状态
    new_wh_name: str = ""
    new_wh_remarks: str = ""
    
    # 日志详情编辑状态
    is_log_edit_open: bool = False
    edit_log_id: int = 0
    edit_log_note: str = ""

    # 超计划入库拦截对话框状态
    is_overprod_dialog_open: bool = False
    overprod_variant: str = ""
    overprod_planned: int = 0
    overprod_current: int = 0
    overprod_incoming: int = 0
    overprod_diff: int = 0

    # ===================== 计算属性 =====================

    @rx.var
    def has_products(self) -> bool:
        return len(self.product_names) > 0

    @rx.var
    def all_movement_types(self) -> list[str]:
        return [
            StockLogReason.IN_INSPECT, 
            StockLogReason.INSPECT_COMPLETED, 
            StockLogReason.INSPECT_REVERSAL,
            StockLogReason.REPAIR_OUT,
            StockLogReason.REPAIR_IN,
            StockLogReason.OTHER_IN, 
            StockLogReason.OUT_STOCK, 
            StockLogReason.TRANSFER
        ]

    @rx.var
    def is_reversal_mode(self) -> bool:
        return self.op_type == StockLogReason.INSPECT_REVERSAL

    @rx.var
    def is_transfer_mode(self) -> bool:
        return self.op_type == StockLogReason.TRANSFER

    @rx.var
    def is_out_mode(self) -> bool:
        return self.op_type == StockLogReason.OUT_STOCK

    @rx.var
    def is_repair_in(self) -> bool:
        return self.op_type == StockLogReason.REPAIR_IN

    @rx.var
    def is_repair_out(self) -> bool:
        return self.op_type == StockLogReason.REPAIR_OUT

    @rx.var
    def is_in_inspect_mode(self) -> bool:
        return self.op_type == StockLogReason.IN_INSPECT

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
        """仓库源列表，用于移出仓库的下拉选择。"""
        return self.warehouse_options

    @rx.var
    def cost_categories(self) -> list[str]:
        return PRODUCT_COST_CATEGORIES

    @rx.var
    def transfer_source_available(self) -> int:
        """当前选中的移出源仓库中，选定款式的当前可用成套/散件物理库存"""
        if not self.op_wh_name or not self.op_variant or not self.selected_product_name:
            return 0
        wh = next((w for w in self.warehouses if w.name == self.op_wh_name), None)
        if not wh:
            return 0
        rows = self.warehouse_stocks.get(str(wh.id), [])
        target_part = self.op_part if (not self.op_is_set and self.has_parts_for_color) else "整套"
        for r in rows:
            if r.product_name == self.selected_product_name and r.variant == self.op_variant:
                if target_part == "整套":
                    if r.part_name == "整套":
                        return r.physical_qty
                    return r.assemblable_sets
                elif r.part_name == target_part:
                    return r.physical_qty
        return 0

    @rx.var
    def is_transfer_qty_excess(self) -> bool:
        """检查移库录入数量是否超出源仓库可用库存"""
        if not self.is_transfer_mode:
            return False
        return self.op_qty > self.transfer_source_available

    def _query_wh_stock(self, wh_name: str, variant: str, part_name: str = None) -> tuple[int, int]:
        """返回指定仓库指定款式/部件的 (physical_qty, assemblable_sets)"""
        if not wh_name or not self.selected_product_name:
            return 0, 0
        wh = next((w for w in self.warehouses if w.name == wh_name), None)
        if not wh:
            return 0, 0
        rows = self.warehouse_stocks.get(str(wh.id), [])
        prod_rows = [r for r in rows if r.product_name == self.selected_product_name and r.variant == variant]
        if not prod_rows:
            return 0, 0
        if part_name and part_name != "整套":
            p_row = next((r for r in prod_rows if r.part_name == part_name), None)
            return (p_row.physical_qty if p_row else 0), 0
        else:
            set_row = next((r for r in prod_rows if r.part_name == "整套"), None)
            if set_row:
                return set_row.physical_qty, set_row.physical_qty
            return prod_rows[0].assemblable_sets, prod_rows[0].assemblable_sets

    @rx.var
    def is_batch_set_mode(self) -> bool:
        return self.batch_mode == "set"

    @rx.var
    def batch_set_rows(self) -> list[BatchSetRow]:
        """成套批量录入矩阵的行数据（实时计算所选仓库在库成套数）"""
        res = []
        for s in self.stats:
            v = s.variant
            k = f"SET::{v}"
            inp = self.batch_inputs.get(k, "")
            if self.is_transfer_mode:
                src_sets = self._query_wh_stock(self.op_wh_name, v)[1]
                dst_sets = self._query_wh_stock(self.op_to_wh_name, v)[1]
                stock_str = f"源: {src_sets}套 -> 目的: {dst_sets}套"
            else:
                cur_sets = self._query_wh_stock(self.op_wh_name, v)[1]
                stock_str = f"当前在库: {cur_sets} 套"
            res.append(BatchSetRow(
                key=k,
                variant=v,
                planned=s.planned,
                stock_display=stock_str,
                input_val=inp
            ))
        return res

    @rx.var
    def batch_part_rows(self) -> list[BatchPartRow]:
        """散件细分批量录入矩阵的行数据（实时计算所选仓库在库物理件数）"""
        res = []
        for s in self.stats:
            v = s.variant
            for p in s.parts:
                k = f"PART::{v}::{p.part_name}"
                inp = self.batch_inputs.get(k, "")
                if self.is_transfer_mode:
                    src_qty = self._query_wh_stock(self.op_wh_name, v, p.part_name)[0]
                    dst_qty = self._query_wh_stock(self.op_to_wh_name, v, p.part_name)[0]
                    stock_str = f"源: {src_qty}件 -> 目的: {dst_qty}件"
                else:
                    cur_qty = self._query_wh_stock(self.op_wh_name, v, p.part_name)[0]
                    stock_str = f"当前在库: {cur_qty} 件"
                res.append(BatchPartRow(
                    key=k,
                    variant=v,
                    part_name=p.part_name,
                    req_qty=p.req_qty,
                    stock_display=stock_str,
                    input_val=inp
                ))
        return res

    @rx.var
    def batch_summary_text(self) -> str:
        prefix = "SET::" if self.batch_mode == "set" else "PART::"
        cnt = 0
        total_q = 0
        for k, v in self.batch_inputs.items():
            if k.startswith(prefix) and v and v.strip():
                try:
                    q = int(v.strip())
                    if q > 0:
                        cnt += 1
                        total_q += q
                except ValueError:
                    pass
        unit = "套" if self.batch_mode == "set" else "件"
        if cnt == 0:
            return "未输入任何数量（留空或 0 自动忽略）"
        return f"已填报 {cnt} 项，本次将批量原子化写入 {cnt} 笔明细，合计变动 {total_q} {unit}"

    @rx.var
    def batch_has_valid_inputs(self) -> bool:
        prefix = "SET::" if self.batch_mode == "set" else "PART::"
        for k, v in self.batch_inputs.items():
            if k.startswith(prefix) and v and v.strip():
                try:
                    if int(v.strip()) > 0:
                        return True
                except ValueError:
                    pass
        return False

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

    # --- 物理变动日志筛选与分页计算属性 ---
    @rx.var
    def log_product_options(self) -> list[str]:
        """物理流水商品筛选选项（全部商品 + 所有商品名）"""
        return ["全部商品"] + self.product_names

    @rx.var
    def log_variant_options(self) -> list[str]:
        """根据当前筛选的商品动态计算款式选项"""
        if self.log_filter_product and self.log_filter_product != "全部商品":
            variants = sorted(list({l.variant for l in self.logs if l.product_name == self.log_filter_product and l.variant}))
        else:
            variants = sorted(list({l.variant for l in self.logs if l.variant}))
        return ["全部款式"] + variants

    @rx.var
    def log_spec_options(self) -> list[str]:
        return ["全部规格", "仅成套", "仅散件"]

    @rx.var
    def log_warehouse_options(self) -> list[str]:
        whs = sorted(list({l.warehouse_name for l in self.logs if l.warehouse_name}))
        return ["全部仓库"] + whs

    @rx.var
    def log_reason_options(self) -> list[str]:
        reasons = sorted(list({l.reason for l in self.logs if l.reason}))
        return ["全部类型"] + reasons

    @rx.var
    def log_page_size_options(self) -> list[str]:
        return ["20", "50", "100"]

    @rx.var
    def log_page_size_str(self) -> str:
        return str(self.log_page_size)

    @rx.var
    def filtered_logs(self) -> list[InventoryLogModel]:
        res = []
        search = self.log_filter_search.strip().lower()

        for l in self.logs:
            # 1. 商品筛选
            if self.log_filter_product and self.log_filter_product != "全部商品":
                if l.product_name != self.log_filter_product:
                    continue

            # 2. 款式筛选
            if self.log_filter_variant and self.log_filter_variant != "全部款式":
                if l.variant != self.log_filter_variant:
                    continue

            # 3. 规格筛选
            if self.log_filter_spec == "仅成套":
                if l.part_display != "[成套]":
                    continue
            elif self.log_filter_spec == "仅散件":
                if l.part_display == "[成套]":
                    continue

            # 4. 仓库筛选
            if self.log_filter_warehouse and self.log_filter_warehouse != "全部仓库":
                if l.warehouse_name != self.log_filter_warehouse:
                    continue

            # 5. 变动类型筛选
            if self.log_filter_reason and self.log_filter_reason != "全部类型":
                if l.reason != self.log_filter_reason:
                    continue

            # 6. 关键字匹配搜索 (支持匹配日期、说明/备注、商品名、款式、部件、仓库、类型)
            if search:
                matched = (
                    search in (l.date or "").lower() or
                    search in (l.note or "").lower() or
                    search in (l.product_name or "").lower() or
                    search in (l.variant or "").lower() or
                    search in (l.part_display or "").lower() or
                    search in (l.warehouse_name or "").lower() or
                    search in (l.reason or "").lower()
                )
                if not matched:
                    continue

            res.append(l)

        return res

    @rx.var
    def paginated_logs(self) -> list[InventoryLogModel]:
        start = (self.log_page_index - 1) * self.log_page_size
        end = start + self.log_page_size
        return self.filtered_logs[start:end]

    @rx.var
    def log_total_pages(self) -> int:
        n = len(self.filtered_logs)
        if n == 0:
            return 1
        return math.ceil(n / self.log_page_size)

    @rx.var
    def log_page_info(self) -> str:
        total = len(self.filtered_logs)
        if total == 0:
            return "0 条记录"
        start = (self.log_page_index - 1) * self.log_page_size + 1
        end = min(self.log_page_index * self.log_page_size, total)
        return f"显示第 {start}-{end} 条，共 {total} 条记录 (第 {self.log_page_index}/{self.log_total_pages} 页)"

    @rx.var
    def log_has_prev_page(self) -> bool:
        return self.log_page_index > 1

    @rx.var
    def log_has_next_page(self) -> bool:
        return self.log_page_index < self.log_total_pages

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
    def toggle_expanded_variant(self, variant: str):
        """切换款式部件详情的展开/收回状态。"""
        if self.expanded_variant == variant:
            self.expanded_variant = ""
        else:
            self.expanded_variant = variant

    @rx.event
    def select_product(self, prod_name: str):
        """切换所选择的分析商品。"""
        self.selected_product_name = prod_name
        self.expanded_variant = ""
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
            repaired = s.get("repaired", 0)
            actual_qty = s.get("actual", 0)
            status = "🔴 缺货" if actual_qty <= 0 else "🟢 有货"
            
            parts_list = [
                PartStatRow(
                    part_name=pt.get("part_name", ""),
                    req_qty=pt.get("req_qty", 1),
                    produced=pt.get("produced", 0),
                    inspecting=pt.get("inspecting", 0),
                    repaired=pt.get("repaired", 0),
                    actual_qty=pt.get("actual_qty", 0),
                    calculable_sets=pt.get("calculable_sets", 0)
                )
                for pt in s.get("parts", [])
            ]
            
            stats_list.append(InventoryStatRow(
                variant=v_name,
                planned=planned,
                produced=produced,
                inspecting=inspecting,
                repaired=repaired,
                actual_qty=actual_qty,
                status=status,
                parts=parts_list
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
        
        logs = service.get_recent_logs(product_name=None, limit=None)
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
    def set_op_type(self, val: str):
        self.op_type = val

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
        try:
            parsed = int(val) if val else 1
            self.op_qty = max(1, parsed)
        except ValueError:
            pass
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
    def set_op_type(self, val: str):
        self.op_type = val
        if val != StockLogReason.IN_INSPECT:
            self.op_auto_inspect_complete = False

    @rx.event
    def set_op_auto_inspect_complete(self, val: bool):
        self.op_auto_inspect_complete = val

    @rx.event
    def set_batch_mode(self, mode: str):
        if "散件" in mode or mode == "part":
            self.batch_mode = "part"
        else:
            self.batch_mode = "set"

    @rx.event
    def set_batch_input(self, key: str, val: str):
        clean_val = "".join([c for c in val if c.isdigit()])
        new_d = dict(self.batch_inputs)
        new_d[key] = clean_val
        self.batch_inputs = new_d

    @rx.event
    def clear_batch_inputs(self):
        self.batch_inputs = {}

    @rx.event
    def submit_batch_inventory_movement(self):
        """提交多款式/多散件批量库存移动。"""
        return self._do_submit_batch_inventory_movement(force_overprod=False)

    @rx.event
    def submit_inventory_movement(self):
        """提交单项库存移动（专用于【入库冲销】单项纠错）。"""
        return self._do_submit_inventory_movement(force_overprod=False)

    @rx.event
    def close_overprod_dialog(self):
        self.is_overprod_dialog_open = False

    @rx.event
    def confirm_overprod_movement(self):
        self.is_overprod_dialog_open = False
        if self.is_reversal_mode:
            return self._do_submit_inventory_movement(force_overprod=True)
        return self._do_submit_batch_inventory_movement(force_overprod=True)

    def _do_submit_batch_inventory_movement(self, force_overprod: bool = False):
        """实际执行多款式/多散件批量库存移动提交逻辑。"""
        if not self.selected_product_name:
            return rx.toast("请先选择商品", level="error")
        if self.is_consumable_out and not self.op_cons_content.strip():
            return rx.toast("请填写【消耗内容】", level="error")

        prefix = "SET::" if self.batch_mode == "set" else "PART::"
        entries = []
        for k, v in self.batch_inputs.items():
            if k.startswith(prefix) and v and v.strip():
                try:
                    q = int(v.strip())
                    if q > 0:
                        if self.batch_mode == "set":
                            var_n = k.replace("SET::", "")
                            entries.append({"variant": var_n, "part_name": None, "quantity": q})
                        else:
                            parts = k.split("::")
                            entries.append({"variant": parts[1], "part_name": parts[2], "quantity": q})
                except ValueError:
                    pass

        if not entries:
            return rx.toast("未检测到有效变动数量，请至少在一个款式或部件输入大于 0 的数量！", level="error")

        db = self.get_db()
        try:
            service = InventoryService(db)
            prod = db.query(Product).filter(Product.name == self.selected_product_name).first()
            if not prod:
                return rx.toast("商品不存在", level="error")

            # 💡 防人为失误：批量超计划生产入库强提醒拦截 (Scheme 2 批量适配，包含一键验收合格入库)
            is_check_overprod = (self.op_type == StockLogReason.INSPECT_COMPLETED) or (self.op_type == StockLogReason.IN_INSPECT and self.op_auto_inspect_complete)
            if is_check_overprod and not force_overprod:
                stats_map = service.get_stock_overview_by_parts(prod.id, prod.name)
                if self.batch_mode == "set":
                    var_qty_map = {}
                    for e in entries:
                        v = e["variant"]
                        var_qty_map[v] = var_qty_map.get(v, 0) + e["quantity"]

                    for v, in_q in var_qty_map.items():
                        v_stat = stats_map.get(v, {})
                        planned = v_stat.get("planned", 0)
                        produced = v_stat.get("produced", 0)
                        if planned > 0 and (produced + in_q) > planned:
                            self.overprod_variant = v
                            self.overprod_planned = planned
                            self.overprod_current = produced
                            self.overprod_incoming = in_q
                            self.overprod_diff = (produced + in_q) - planned
                            self.is_overprod_dialog_open = True
                            return
                else:
                    # 分部件/散件细分录入模式：按部件配比折算成套数校验超产
                    var_part_map = {}
                    for e in entries:
                        v = e["variant"]
                        p_name = e.get("part_name")
                        q = e.get("quantity", 0)
                        if v not in var_part_map:
                            var_part_map[v] = {}
                        var_part_map[v][p_name] = var_part_map[v].get(p_name, 0) + q

                    for v, part_inputs in var_part_map.items():
                        v_stat = stats_map.get(v, {})
                        planned = v_stat.get("planned", 0)
                        produced = v_stat.get("produced", 0)
                        v_parts = v_stat.get("parts", [])

                        if not v_parts:
                            in_q = sum(part_inputs.values())
                            if planned > 0 and (produced + in_q) > planned:
                                self.overprod_variant = v
                                self.overprod_planned = planned
                                self.overprod_current = produced
                                self.overprod_incoming = in_q
                                self.overprod_diff = (produced + in_q) - planned
                                self.is_overprod_dialog_open = True
                                return
                        else:
                            # 结合各部件已累计生产数与本次录入数，按木桶原理计算本次提交后能达到的成套数
                            new_produced_sets = min(
                                (pt.get("produced", 0) + part_inputs.get(pt.get("part_name"), 0)) // (pt.get("req_qty", 1) or 1)
                                for pt in v_parts
                            )
                            in_sets = max(0, new_produced_sets - produced)
                            if planned > 0 and new_produced_sets > planned and new_produced_sets > produced:
                                self.overprod_variant = v
                                self.overprod_planned = planned
                                self.overprod_current = produced
                                self.overprod_incoming = in_sets
                                self.overprod_diff = new_produced_sets - planned
                                self.is_overprod_dialog_open = True
                                return

            # 转化仓库 id
            wh_id = int(self.op_wh_id) if self.op_wh_id and self.op_wh_id != "None" else None
            to_wh_id = int(self.op_to_wh_id) if self.op_to_wh_id and self.op_to_wh_id != "None" else None

            # 日期对象
            try:
                date_val = date.fromisoformat(self.op_date)
            except Exception:
                date_val = date.today()

            msg = service.add_batch_inventory_movements(
                product_id=prod.id,
                product_name=prod.name,
                entries=entries,
                move_type=self.op_type,
                date_obj=date_val,
                batch_remark=self.op_remark.strip(),
                warehouse_id=wh_id,
                to_warehouse_id=to_wh_id,
                out_type=self.op_out_mode,
                cons_cat=self.op_cons_cat,
                cons_content=self.op_cons_content.strip(),
                auto_inspect_complete=self.op_auto_inspect_complete
            )

            service.commit()

            # 清空输入状态
            self.batch_inputs = {}
            self.op_remark = ""
            self.op_cons_content = ""

            # 刷新
            self.load_current_inventory(service)
            self.load_warehouse_list(service)

            # 同步缓存
            from cache_manager import sync_all_caches
            sync_all_caches()

            return rx.toast(msg)
        except Exception as e:
            db.rollback()
            return rx.toast(f"批量提交失败: {e}", level="error")
        finally:
            db.close()

    def _do_submit_inventory_movement(self, force_overprod: bool = False):
        """实际执行单项库存移动提交逻辑。"""
        if not self.selected_product_name:
            return rx.toast("请先选择商品", level="error")
        if self.op_qty <= 0:
            return rx.toast("变动数量必须大于 0", level="error")
        if self.is_consumable_out and not self.op_cons_content.strip():
            return rx.toast("请填写【消耗内容】", level="error")
            
        db = self.get_db()
        try:
            service = InventoryService(db)
            prod = db.query(Product).filter(Product.name == self.selected_product_name).first()
            if not prod:
                return rx.toast("商品不存在", level="error")

            # 💡 防人为失误：超计划生产入库强提醒拦截
            is_check_overprod = (self.op_type == StockLogReason.INSPECT_COMPLETED) or (self.op_type == StockLogReason.IN_INSPECT and self.op_auto_inspect_complete)
            if is_check_overprod and not force_overprod:
                stats_map = service.get_stock_overview_by_parts(prod.id, prod.name)
                v_stat = stats_map.get(self.op_variant, {})
                planned = v_stat.get("planned", 0)
                produced = v_stat.get("produced", 0)
                v_parts = v_stat.get("parts", [])

                is_set_op = self.op_is_set if self.has_parts_for_color else True
                actual_part_name = self.op_part if (not self.op_is_set and self.has_parts_for_color) else None

                if is_set_op or not v_parts:
                    if planned > 0 and (produced + self.op_qty) > planned:
                        self.overprod_variant = self.op_variant
                        self.overprod_planned = planned
                        self.overprod_current = produced
                        self.overprod_incoming = self.op_qty
                        self.overprod_diff = (produced + self.op_qty) - planned
                        self.is_overprod_dialog_open = True
                        return
                else:
                    new_produced_sets = min(
                        (pt.get("produced", 0) + (self.op_qty if pt.get("part_name") == actual_part_name else 0)) // (pt.get("req_qty", 1) or 1)
                        for pt in v_parts
                    )
                    in_sets = max(0, new_produced_sets - produced)
                    if planned > 0 and new_produced_sets > planned and new_produced_sets > produced:
                        self.overprod_variant = self.op_variant
                        self.overprod_planned = planned
                        self.overprod_current = produced
                        self.overprod_incoming = in_sets
                        self.overprod_diff = new_produced_sets - planned
                        self.is_overprod_dialog_open = True
                        return

            # 转化仓库 id
            wh_id = int(self.op_wh_id) if self.op_wh_id and self.op_wh_id != "None" else None
            to_wh_id = int(self.op_to_wh_id) if self.op_to_wh_id and self.op_to_wh_id != "None" else None
            
            # 日期对象
            try:
                date_val = date.fromisoformat(self.op_date)
            except Exception:
                date_val = date.today()

            is_set_op = self.op_is_set if self.has_parts_for_color else True
            actual_part_name = self.op_part if (not self.op_is_set and self.has_parts_for_color) else None
                
            if self.op_type == StockLogReason.IN_INSPECT and self.op_auto_inspect_complete:
                service.add_inventory_movement(
                    product_id=prod.id, product_name=prod.name, variant=self.op_variant,
                    quantity=self.op_qty, move_type=StockLogReason.IN_INSPECT,
                    date_obj=date_val, remark=self.op_remark.strip(),
                    warehouse_id=wh_id, to_warehouse_id=to_wh_id,
                    is_set=is_set_op, part_name=actual_part_name,
                    out_type=self.op_out_mode, cons_cat=self.op_cons_cat, cons_content=self.op_cons_content.strip()
                )
                service.add_inventory_movement(
                    product_id=prod.id, product_name=prod.name, variant=self.op_variant,
                    quantity=self.op_qty, move_type=StockLogReason.INSPECT_COMPLETED,
                    date_obj=date_val, remark=self.op_remark.strip(),
                    warehouse_id=wh_id, to_warehouse_id=to_wh_id,
                    is_set=is_set_op, part_name=actual_part_name,
                    out_type=self.op_out_mode, cons_cat=self.op_cons_cat, cons_content=self.op_cons_content.strip()
                )
                msg = f"一键验收+合格入库成功（已生成入库验收与合格入库流水各1笔）"
            else:
                msg = service.add_inventory_movement(
                    product_id=prod.id, product_name=prod.name, variant=self.op_variant,
                    quantity=self.op_qty, move_type=self.op_type,
                    date_obj=date_val, remark=self.op_remark.strip(),
                    warehouse_id=wh_id, to_warehouse_id=to_wh_id,
                    is_set=is_set_op, part_name=actual_part_name,
                    out_type=self.op_out_mode, cons_cat=self.op_cons_cat, cons_content=self.op_cons_content.strip()
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

    # --- 物理变动日志筛选与分页事件处理器 ---
    @rx.event
    def set_log_filter_product(self, val: str):
        self.log_filter_product = val
        self.log_filter_variant = "全部款式"
        self.log_page_index = 1

    @rx.event
    def set_log_filter_variant(self, val: str):
        self.log_filter_variant = val
        self.log_page_index = 1

    @rx.event
    def set_log_filter_spec(self, val: str):
        self.log_filter_spec = val
        self.log_page_index = 1

    @rx.event
    def set_log_filter_warehouse(self, val: str):
        self.log_filter_warehouse = val
        self.log_page_index = 1

    @rx.event
    def set_log_filter_reason(self, val: str):
        self.log_filter_reason = val
        self.log_page_index = 1

    @rx.event
    def set_log_filter_date_start(self, val: str):
        self.log_filter_date_start = val
        self.log_page_index = 1

    @rx.event
    def set_log_filter_date_end(self, val: str):
        self.log_filter_date_end = val
        self.log_page_index = 1

    @rx.event
    def set_log_filter_search(self, val: str):
        self.log_filter_search = val
        self.log_page_index = 1

    @rx.event
    def set_log_page_size(self, val: str):
        try:
            self.log_page_size = int(val)
        except ValueError:
            self.log_page_size = 20
        self.log_page_index = 1

    @rx.event
    def log_prev_page(self):
        if self.log_page_index > 1:
            self.log_page_index -= 1

    @rx.event
    def log_next_page(self):
        if self.log_page_index < self.log_total_pages:
            self.log_page_index += 1

    @rx.event
    def log_first_page(self):
        self.log_page_index = 1

    @rx.event
    def log_last_page(self):
        self.log_page_index = self.log_total_pages

    @rx.event
    def reset_log_filters(self):
        self.log_filter_product = "全部商品"
        self.log_filter_variant = "全部款式"
        self.log_filter_spec = "全部规格"
        self.log_filter_warehouse = "全部仓库"
        self.log_filter_reason = "全部类型"
        self.log_filter_date_start = ""
        self.log_filter_date_end = ""
        self.log_filter_search = ""
        self.log_page_index = 1

    @rx.event
    def filter_current_product_logs(self):
        if self.selected_product_name:
            self.log_filter_product = self.selected_product_name
            self.log_filter_variant = "全部款式"
            self.log_page_index = 1

    @rx.event
    def filter_all_products_logs(self):
        self.log_filter_product = "全部商品"
        self.log_filter_variant = "全部款式"
        self.log_page_index = 1
