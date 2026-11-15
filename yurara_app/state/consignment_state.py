# yurara_app/state/consignment_state.py
"""
寄售管理（归属销售管理模块）State。
提供：寄售店档案、仓库出库到寄售店、寄售店退回仓库、单笔/批量售出结算（含店铺手续费与入账账户）、
结算与退回历史查询及撤销回滚。
"""
import reflex as rx
from datetime import date
from pydantic import BaseModel
from typing import List

from .app_state import AppState
from services.consignment_service import ConsignmentService
from services.inventory_service import InventoryService
from constants import BalanceCategory, to_cny
from models import Product, Warehouse, CompanyBalanceItem, ConsignmentShop
from cache_manager import sync_all_caches


class ConsignmentShopRow(BaseModel):
    id: int = 0
    name: str = ""
    currency: str = "CNY"
    default_fee_rate: float = 0.0
    default_fee_fixed: float = 0.0
    default_account_name: str = ""
    contact_info: str = ""
    remarks: str = ""
    active_items_count: int = 0
    remaining_qty: int = 0
    sold_qty: int = 0
    returned_qty: int = 0
    settled_total: float = 0.0
    settled_cny: float = 0.0
    fee_desc: str = "0%"
    settled_str: str = "0.00"


class ConsignmentLedgerRow(BaseModel):
    id: int = 0
    date: str = ""
    shop_id: int = 0
    shop_name: str = ""
    warehouse_id: int = 0
    warehouse_name: str = "未指定"
    product_name: str = ""
    variant: str = "通用"
    part_name: str = "整套"
    quantity: int = 0
    sold_qty: int = 0
    returned_qty: int = 0
    remaining_qty: int = 0
    unit_price: float = 0.0
    unit_price_str: str = "0.00"
    currency: str = "CNY"
    status: str = "寄售中"
    status_color: str = "green"
    remarks: str = ""
    inventory_log_id: int | None = None
    is_selected: bool = False
    has_remaining: bool = True


class SettlementItemRow(BaseModel):
    id: int = 0
    consignment_item_id: int = 0
    product_name: str = ""
    variant: str = ""
    part_name: str = "整套"
    sold_qty: int = 0
    unit_price: float = 0.0
    gross_subtotal: float = 0.0
    net_subtotal: float = 0.0


class SettlementOrderRow(BaseModel):
    id: int = 0
    settlement_no: str = ""
    shop_id: int = 0
    shop_name: str = ""
    settlement_date: str = ""
    currency: str = "CNY"
    gross_amount: float = 0.0
    fee_rate: float = 0.0
    fee_amount: float = 0.0
    net_amount: float = 0.0
    account_id: int = 0
    account_name: str = ""
    sales_order_id: int = 0
    notes: str = ""
    total_sold_qty: int = 0
    items_summary: str = ""
    line_items: List[SettlementItemRow] = []


class ConsignmentReturnRow(BaseModel):
    id: int = 0
    consignment_item_id: int = 0
    shop_name: str = ""
    product_name: str = ""
    variant: str = ""
    part_name: str = "整套"
    warehouse_id: int = 0
    warehouse_name: str = ""
    return_qty: int = 0
    return_date: str = ""
    notes: str = ""


class DispatchEntryRow(BaseModel):
    key: str = ""
    variant: str = ""
    part_name: str = "整套"
    warehouse_stock: int = 0
    qty_input: str = ""


class ReturnLineRow(BaseModel):
    consignment_item_id: int = 0
    shop_name: str = ""
    product_name: str = ""
    variant: str = ""
    part_name: str = "整套"
    max_qty: int = 0
    return_qty_input: str = "1"


class SettleLineRow(BaseModel):
    consignment_item_id: int = 0
    shop_name: str = ""
    product_name: str = ""
    variant: str = ""
    part_name: str = "整套"
    max_qty: int = 0
    currency: str = "CNY"
    sold_qty_input: str = "1"
    unit_price_input: str = "0"
    subtotal_str: str = "0.00"


class AccountOption(BaseModel):
    id: int = 0
    name: str = ""
    currency: str = "CNY"
    amount: float = 0.0
    label: str = ""


class ConsignmentState(AppState):
    """寄售管理模块状态与业务调度。"""

    active_tab: str = "ledger"

    # 核心数据
    shops: List[ConsignmentShopRow] = []
    items: List[ConsignmentLedgerRow] = []
    settlements: List[SettlementOrderRow] = []
    returns: List[ConsignmentReturnRow] = []
    accounts: List[AccountOption] = []
    warehouse_names: List[str] = []
    warehouse_id_map: dict[str, int] = {}
    product_names: List[str] = []
    product_variants_map: dict[str, List[str]] = {}
    product_parts_map: dict[str, List[str]] = {}  # key: "product::variant" -> parts
    product_prices_map: dict[str, float] = {}  # key: "product::variant::currency" -> price
    currency_options: List[str] = ["CNY", "JPY", "USD", "HKD", "TWD", "EUR"]

    # 筛选与多选
    filter_shop: str = "全部店铺"
    filter_status: str = "全部状态"
    filter_product: str = "全部商品"
    filter_search: str = ""
    selected_ids: List[int] = []

    # 1. 出库到寄售店弹窗
    is_dispatch_open: bool = False
    dispatch_shop_select: str = "__custom__"
    dispatch_custom_shop: str = ""
    dispatch_warehouse_name: str = ""
    dispatch_product_name: str = ""
    dispatch_date: str = ""
    dispatch_remarks: str = ""
    dispatch_rows: List[DispatchEntryRow] = []

    # 2. 手工补录寄售弹窗
    is_manual_add_open: bool = False
    manual_shop_select: str = "__custom__"
    manual_custom_shop: str = ""
    manual_product_name: str = ""
    manual_variant: str = "通用"
    manual_part_name: str = "整套"
    manual_qty: str = "1"
    manual_remaining_qty: str = "1"
    manual_unit_price: str = "0"
    manual_currency: str = "CNY"
    manual_date: str = ""
    manual_remarks: str = ""

    # 3. 编辑寄售条目弹窗
    is_edit_open: bool = False
    edit_item_id: int = 0
    edit_shop_name: str = ""
    edit_product_info: str = ""
    edit_remaining_qty: str = "0"
    edit_unit_price: str = "0"
    edit_remarks: str = ""

    # 4. 退回仓库弹窗
    is_return_open: bool = False
    return_warehouse_name: str = ""
    return_date: str = ""
    return_notes: str = ""
    return_lines: List[ReturnLineRow] = []

    # 5. 寄售结算弹窗
    is_settle_open: bool = False
    settle_shop_id: int = 0
    settle_shop_name: str = ""
    settle_date: str = ""
    settle_currency: str = "CNY"
    settle_account_label: str = ""
    settle_gross_str: str = "0.00"
    settle_fee_rate: str = "0"
    settle_fee_amount: str = "0.00"
    settle_net_amount: str = "0.00"
    settle_notes: str = ""
    settle_lines: List[SettleLineRow] = []

    # 6. 寄售店档案新增/编辑弹窗
    is_shop_modal_open: bool = False
    shop_edit_id: int = 0
    shop_form_name: str = ""
    shop_form_currency: str = "CNY"
    shop_form_fee_rate: str = "0"
    shop_form_fee_fixed: str = "0"
    shop_form_account_name: str = ""
    shop_form_contact: str = ""
    shop_form_remarks: str = ""

    # 7. 结算详情展开ID
    expanded_settlement_id: int = 0

    # ==================== Computed Vars ====================

    @rx.var
    def shop_names(self) -> List[str]:
        return [s.name for s in self.shops]

    @rx.var
    def filter_shop_options(self) -> List[str]:
        seen = []
        for s in self.shops:
            if s.name and s.name not in seen:
                seen.append(s.name)
        for it in self.items:
            if it.shop_name and it.shop_name not in seen:
                seen.append(it.shop_name)
        return ["全部店铺"] + seen

    @rx.var
    def filter_product_options(self) -> List[str]:
        seen = []
        for it in self.items:
            if it.product_name and it.product_name not in seen:
                seen.append(it.product_name)
        return ["全部商品"] + seen

    @rx.var
    def account_labels(self) -> List[str]:
        return [a.label for a in self.accounts]

    @rx.var
    def shop_account_options(self) -> List[str]:
        return ["不指定"] + [a.name for a in self.accounts]

    @rx.var
    def manual_variant_options(self) -> List[str]:
        return self.product_variants_map.get(self.manual_product_name, ["通用"])

    @rx.var
    def manual_part_options(self) -> List[str]:
        key = f"{self.manual_product_name}::{self.manual_variant}"
        return self.product_parts_map.get(key, ["整套"])

    @rx.var
    def filtered_items(self) -> List[ConsignmentLedgerRow]:
        sel_set = set(self.selected_ids)
        q = self.filter_search.strip().lower()
        res = []
        for it in self.items:
            if self.filter_shop != "全部店铺" and it.shop_name != self.filter_shop:
                continue
            if self.filter_status != "全部状态" and it.status != self.filter_status:
                continue
            if self.filter_product != "全部商品" and it.product_name != self.filter_product:
                continue
            if q:
                hay = f"{it.shop_name} {it.product_name} {it.variant} {it.part_name} {it.remarks}".lower()
                if q not in hay:
                    continue
            row = it.model_copy(update={"is_selected": (it.id in sel_set)})
            res.append(row)
        return res

    @rx.var
    def selected_count(self) -> int:
        return len(self.selected_ids)

    @rx.var
    def kpi_shop_count(self) -> int:
        return len(self.shops)

    @rx.var
    def kpi_remaining_qty(self) -> int:
        return sum(i.remaining_qty for i in self.items)

    @rx.var
    def kpi_sold_qty(self) -> int:
        return sum(i.sold_qty for i in self.items)

    @rx.var
    def kpi_returned_qty(self) -> int:
        return sum(i.returned_qty for i in self.items)

    @rx.var
    def kpi_settled_cny(self) -> str:
        total = sum(s.settled_cny for s in self.shops)
        if total == 0 and self.settlements:
            rates = self.rates_map or {"CNY": 1.0}
            total = sum(to_cny(st.net_amount, st.currency, rates) for st in self.settlements)
        return f"¥ {total:,.2f}"

    # ==================== Data Loading ====================

    @rx.event
    async def load_consignment_page(self):
        if not await self.is_authenticated_user():
            return
        await self.load_exchange_rate()
        db = self.get_db()
        try:
            self._reload_all(db)
        finally:
            db.close()

    def _reload_all(self, db):
        service = ConsignmentService(db)
        rates_map = self.rates_map or {"CNY": 1.0}
        self.currency_options = list(rates_map.keys()) if rates_map else ["CNY", "JPY", "USD"]

        # 1. Shops
        raw_shops = service.get_shop_summaries()
        shop_rows = []
        for s in raw_shops:
            rate = float(s.get("default_fee_rate", 0.0) or 0.0)
            rate_pct = round(rate * 100.0, 2)
            fixed = float(s.get("default_fee_fixed", 0.0) or 0.0)
            fee_parts = []
            if rate_pct > 0:
                fee_parts.append(f"{rate_pct:g}%")
            if fixed > 0:
                fee_parts.append(f"+{fixed:.2f} {s.get('currency', 'CNY')}")
            fee_desc = " ".join(fee_parts) if fee_parts else "0%"

            # Compute CNY total using app rates_map
            shop_settlements = [st for st in service.get_settlements(shop_id=s["id"])]
            settled_cny = sum(
                to_cny(float(st.net_amount or 0.0), st.currency or "CNY", rates_map)
                for st in shop_settlements
            )
            settled_orig = float(s.get("settled_total", 0.0) or 0.0)
            shop_rows.append(
                ConsignmentShopRow(
                    id=s["id"],
                    name=s["name"],
                    currency=s.get("currency", "CNY") or "CNY",
                    default_fee_rate=rate,
                    default_fee_fixed=fixed,
                    default_account_name=s.get("default_account_name", "") or "",
                    contact_info=s.get("contact_info", "") or "",
                    remarks=s.get("remarks", "") or "",
                    active_items_count=int(s.get("active_items_count", 0) or 0),
                    remaining_qty=int(s.get("remaining_qty", 0) or 0),
                    sold_qty=int(s.get("sold_qty", 0) or 0),
                    returned_qty=int(s.get("returned_qty", 0) or 0),
                    settled_total=round(settled_orig, 2),
                    settled_cny=round(settled_cny, 2),
                    fee_desc=fee_desc,
                    settled_str=f"{settled_orig:,.2f} {s.get('currency', 'CNY')}",
                )
            )
        self.shops = shop_rows

        # 2. Warehouses
        whs = db.query(Warehouse).order_by(Warehouse.id.asc()).all()
        self.warehouse_names = [w.name for w in whs]
        self.warehouse_id_map = {w.name: w.id for w in whs}

        # 3. Accounts (asset cash accounts)
        accs = (
            db.query(CompanyBalanceItem)
            .filter(
                CompanyBalanceItem.category == BalanceCategory.ASSET,
                CompanyBalanceItem.asset_type == "现金",
            )
            .order_by(CompanyBalanceItem.id.asc())
            .all()
        )
        self.accounts = [
            AccountOption(
                id=a.id,
                name=a.name,
                currency=a.currency or "CNY",
                amount=round(float(a.amount or 0.0), 2),
                label=f"{a.name} ({a.currency or 'CNY'} | 余额 {float(a.amount or 0.0):,.2f})",
            )
            for a in accs
        ]

        # 4. Products / Variants / Parts / Prices
        prods = db.query(Product).order_by(Product.id.desc()).all()
        self.product_names = [p.name for p in prods]
        v_map: dict[str, List[str]] = {}
        p_map: dict[str, List[str]] = {}
        pr_map: dict[str, float] = {}
        for p in prods:
            colors = [c.color_name for c in p.colors] if p.colors else ["通用"]
            v_map[p.name] = colors
            for c in p.colors:
                pts = ["整套"] + [pt.part_name for pt in (c.parts or [])]
                p_map[f"{p.name}::{c.color_name}"] = pts
                for pr in (c.prices or []):
                    cur = pr.currency or "CNY"
                    k = f"{p.name}::{c.color_name}::{cur}"
                    if k not in pr_map and float(pr.price or 0.0) > 0:
                        pr_map[k] = float(pr.price)
                if c.prices:
                    first_valid = next((float(pr.price) for pr in c.prices if float(pr.price or 0.0) > 0), 0.0)
                    if first_valid > 0:
                        pr_map[f"{p.name}::{c.color_name}::__ANY__"] = first_valid
            p_map.setdefault(f"{p.name}::通用", ["整套"])
        self.product_variants_map = v_map
        self.product_parts_map = p_map
        self.product_prices_map = pr_map

        # 5. Consignment Items
        wh_name_by_id = {w.id: w.name for w in whs}
        raw_items = service.get_all_consignments()
        item_rows = []
        valid_ids = set()
        for c in raw_items:
            rem = int(c.remaining_qty or 0)
            st = c.status or "寄售中"
            if st == "已结清":
                s_color = "blue"
            elif st == "部分结算":
                s_color = "amber"
            else:
                s_color = "green"
            up = float(c.unit_price or 0.0)
            wh_name = wh_name_by_id.get(c.warehouse_id, "未指定") if c.warehouse_id else "未指定"
            valid_ids.add(c.id)
            item_rows.append(
                ConsignmentLedgerRow(
                    id=c.id,
                    date=c.date.strftime("%Y-%m-%d") if c.date else "",
                    shop_id=c.shop_id or 0,
                    shop_name=c.shop_name or "",
                    warehouse_id=c.warehouse_id or 0,
                    warehouse_name=wh_name,
                    product_name=c.product_name or "",
                    variant=c.variant or "通用",
                    part_name=c.part_name or "整套",
                    quantity=int(c.quantity or 0),
                    sold_qty=int(c.sold_qty or 0),
                    returned_qty=int(c.returned_qty or 0),
                    remaining_qty=rem,
                    unit_price=round(up, 2),
                    unit_price_str=f"{up:.2f}" if up > 0 else "-",
                    currency=c.currency or "CNY",
                    status=st,
                    status_color=s_color,
                    remarks=c.remarks or "",
                    inventory_log_id=c.inventory_log_id,
                    is_selected=(c.id in self.selected_ids),
                    has_remaining=(rem > 0),
                )
            )
        self.items = item_rows
        self.selected_ids = [sid for sid in self.selected_ids if sid in valid_ids]

        # 6. Settlements
        raw_settlements = service.get_settlements()
        st_rows = []
        for st in raw_settlements:
            si_rows = [
                SettlementItemRow(
                    id=si.id,
                    consignment_item_id=si.consignment_item_id or 0,
                    product_name=si.product_name or "",
                    variant=si.variant or "",
                    part_name=si.part_name or "整套",
                    sold_qty=int(si.sold_qty or 0),
                    unit_price=round(float(si.unit_price or 0.0), 2),
                    gross_subtotal=round(float(si.gross_subtotal or 0.0), 2),
                    net_subtotal=round(float(si.net_subtotal or 0.0), 2),
                )
                for si in st.items
            ]
            summary_parts = [
                f"{si.product_name}({si.variant}{('/' + si.part_name) if si.part_name != '整套' else ''}) x{si.sold_qty}"
                for si in si_rows
            ]
            summary_str = "；".join(summary_parts[:3]) + (f" 等{len(summary_parts)}项" if len(summary_parts) > 3 else "")
            st_rows.append(
                SettlementOrderRow(
                    id=st.id,
                    settlement_no=st.settlement_no or "",
                    shop_id=st.shop_id or 0,
                    shop_name=st.shop_name or "",
                    settlement_date=st.settlement_date.strftime("%Y-%m-%d") if st.settlement_date else "",
                    currency=st.currency or "CNY",
                    gross_amount=round(float(st.gross_amount or 0.0), 2),
                    fee_rate=round(float(st.fee_rate or 0.0) * 100.0, 2),
                    fee_amount=round(float(st.fee_amount or 0.0), 2),
                    net_amount=round(float(st.net_amount or 0.0), 2),
                    account_id=st.account_id or 0,
                    account_name=st.account_name or "",
                    sales_order_id=st.sales_order_id or 0,
                    notes=st.notes or "",
                    total_sold_qty=sum(si.sold_qty for si in si_rows),
                    items_summary=summary_str or "无明细",
                    line_items=si_rows,
                )
            )
        self.settlements = st_rows

        # 7. Returns
        raw_returns = service.get_return_history()
        self.returns = [
            ConsignmentReturnRow(
                id=r.id,
                consignment_item_id=r.consignment_item_id or 0,
                shop_name=r.shop_name or "",
                product_name=r.product_name or "",
                variant=r.variant or "",
                part_name=r.part_name or "整套",
                warehouse_id=r.warehouse_id or 0,
                warehouse_name=r.warehouse_name or "",
                return_qty=int(r.return_qty or 0),
                return_date=r.return_date.strftime("%Y-%m-%d") if r.return_date else "",
                notes=r.notes or "",
            )
            for r in raw_returns
        ]

    # ==================== Navigation & Filter Events ====================

    @rx.event
    def set_active_tab(self, tab: str):
        self.active_tab = tab

    @rx.event
    def set_filter_shop(self, val: str):
        self.filter_shop = val

    @rx.event
    def set_filter_status(self, val: str):
        self.filter_status = val

    @rx.event
    def set_filter_product(self, val: str):
        self.filter_product = val

    @rx.event
    def set_filter_search(self, val: str):
        self.filter_search = val

    @rx.event
    def reset_filters(self):
        self.filter_shop = "全部店铺"
        self.filter_status = "全部状态"
        self.filter_product = "全部商品"
        self.filter_search = ""

    @rx.event
    def toggle_select_item(self, item_id: int):
        if item_id in self.selected_ids:
            self.selected_ids = [i for i in self.selected_ids if i != item_id]
        else:
            self.selected_ids = [*self.selected_ids, item_id]

    @rx.event
    def clear_selection(self):
        self.selected_ids = []

    @rx.event
    def select_all_filtered_remaining(self):
        target_ids = [r.id for r in self.filtered_items if r.remaining_qty > 0]
        self.selected_ids = target_ids

    @rx.event
    def toggle_settlement_expand(self, st_id: int):
        self.expanded_settlement_id = 0 if self.expanded_settlement_id == st_id else st_id

    # ==================== 1. Dispatch from Warehouse ====================

    @rx.event
    def open_dispatch_modal(self):
        if self.shops:
            self.dispatch_shop_select = self.shops[0].name
            self.dispatch_custom_shop = ""
        else:
            self.dispatch_shop_select = "__custom__"
            self.dispatch_custom_shop = ""
        self.dispatch_warehouse_name = self.warehouse_names[0] if self.warehouse_names else ""
        self.dispatch_product_name = self.product_names[0] if self.product_names else ""
        self.dispatch_date = date.today().strftime("%Y-%m-%d")
        self.dispatch_remarks = ""
        db = self.get_db()
        try:
            self._build_dispatch_rows(db)
        finally:
            db.close()
        self.is_dispatch_open = True

    @rx.event
    def close_dispatch_modal(self):
        self.is_dispatch_open = False

    def _build_dispatch_rows(self, db):
        if not self.dispatch_product_name:
            self.dispatch_rows = []
            return
        prod = db.query(Product).filter(Product.name == self.dispatch_product_name).first()
        if not prod:
            self.dispatch_rows = []
            return
        wh_id = self.warehouse_id_map.get(self.dispatch_warehouse_name, 0)
        stock_lookup: dict[tuple[str, str], int] = {}
        if wh_id:
            inv_service = InventoryService(db)
            wh_details = inv_service.get_warehouse_inventory_details()
            prod_stock = wh_details.get(wh_id, {}).get("stock", {}).get(prod.name, {})
            for v_name, parts_dict in prod_stock.items():
                for pt_name, qty in parts_dict.items():
                    stock_lookup[(v_name, pt_name)] = int(qty or 0)

        rows = []
        for c in prod.colors:
            v_name = c.color_name
            parts = [pt.part_name for pt in (c.parts or [])]
            if not parts:
                stk = stock_lookup.get((v_name, "整套"), 0)
                rows.append(DispatchEntryRow(
                    key=f"{v_name}::整套",
                    variant=v_name,
                    part_name="整套",
                    warehouse_stock=stk,
                    qty_input="",
                ))
            else:
                for p_name in parts:
                    stk = stock_lookup.get((v_name, p_name), 0)
                    rows.append(DispatchEntryRow(
                        key=f"{v_name}::{p_name}",
                        variant=v_name,
                        part_name=p_name,
                        warehouse_stock=stk,
                        qty_input="",
                    ))
        self.dispatch_rows = rows

    @rx.event
    def set_dispatch_shop_select(self, val: str):
        self.dispatch_shop_select = val

    @rx.event
    def set_dispatch_custom_shop(self, val: str):
        self.dispatch_custom_shop = val

    @rx.event
    def set_dispatch_warehouse_name(self, val: str):
        self.dispatch_warehouse_name = val
        db = self.get_db()
        try:
            self._build_dispatch_rows(db)
        finally:
            db.close()

    @rx.event
    def set_dispatch_product_name(self, val: str):
        self.dispatch_product_name = val
        db = self.get_db()
        try:
            self._build_dispatch_rows(db)
        finally:
            db.close()

    @rx.event
    def set_dispatch_date(self, val: str):
        self.dispatch_date = val

    @rx.event
    def set_dispatch_remarks(self, val: str):
        self.dispatch_remarks = val

    @rx.event
    def set_dispatch_row_qty(self, key: str, val: str):
        updated = []
        for r in self.dispatch_rows:
            if r.key == key:
                updated.append(r.model_copy(update={"qty_input": val}))
            else:
                updated.append(r)
        self.dispatch_rows = updated

    @rx.event
    def submit_dispatch(self):
        shop_name = (
            self.dispatch_custom_shop.strip()
            if self.dispatch_shop_select == "__custom__"
            else self.dispatch_shop_select.strip()
        )
        if not shop_name:
            return rx.toast("请选择或输入寄售店铺名称", level="error")
        wh_id = self.warehouse_id_map.get(self.dispatch_warehouse_name)
        if not wh_id:
            return rx.toast("请选择出库物理仓库", level="error")
        if not self.dispatch_product_name:
            return rx.toast("请选择寄售商品", level="error")

        entries = []
        for r in self.dispatch_rows:
            raw = (r.qty_input or "").strip()
            if not raw:
                continue
            try:
                q = int(raw)
            except ValueError:
                return rx.toast(f"{r.variant}/{r.part_name} 出库数量必须为整数", level="error")
            if q > 0:
                entries.append({"variant": r.variant, "part_name": r.part_name, "quantity": q})

        if not entries:
            return rx.toast("请至少填写一项大于 0 的出库数量", level="error")

        try:
            d = date.fromisoformat(self.dispatch_date) if self.dispatch_date else date.today()
        except Exception:
            d = date.today()

        db = self.get_db()
        try:
            service = ConsignmentService(db)
            msg = service.dispatch_from_warehouse(
                shop_id=None,
                shop_name=shop_name,
                warehouse_id=wh_id,
                product_name=self.dispatch_product_name,
                entries=entries,
                dispatch_date=d,
                remarks=self.dispatch_remarks.strip(),
            )
            db.commit()
            sync_all_caches()
            self.is_dispatch_open = False
            self._reload_all(db)
            return rx.toast(msg or f"已从「{self.dispatch_warehouse_name}」出库 {len(entries)} 项至「{shop_name}」！")
        except Exception as e:
            db.rollback()
            return rx.toast(f"出库失败: {e}", level="error")
        finally:
            db.close()

    # ==================== 2. Manual Add Consignment ====================

    @rx.event
    def open_manual_add_modal(self):
        if self.shops:
            self.manual_shop_select = self.shops[0].name
            self.manual_custom_shop = ""
        else:
            self.manual_shop_select = "__custom__"
            self.manual_custom_shop = ""
        prod = self.product_names[0] if self.product_names else ""
        self.manual_product_name = prod
        variants = self.product_variants_map.get(prod, ["通用"])
        self.manual_variant = variants[0] if variants else "通用"
        parts = self.product_parts_map.get(f"{prod}::{self.manual_variant}", ["整套"])
        self.manual_part_name = parts[0] if parts else "整套"
        self.manual_qty = "1"
        self.manual_remaining_qty = "1"
        cur = self.shops[0].currency if self.shops else "CNY"
        self.manual_currency = cur
        default_price = self._lookup_default_price(prod, self.manual_variant, cur)
        self.manual_unit_price = f"{default_price:.2f}" if default_price > 0 else "0"
        self.manual_date = date.today().strftime("%Y-%m-%d")
        self.manual_remarks = ""
        self.is_manual_add_open = True

    @rx.event
    def close_manual_add_modal(self):
        self.is_manual_add_open = False

    def _lookup_default_price(self, prod: str, variant: str, currency: str) -> float:
        return (
            self.product_prices_map.get(f"{prod}::{variant}::{currency}")
            or self.product_prices_map.get(f"{prod}::{variant}::__ANY__")
            or 0.0
        )

    @rx.event
    def set_manual_shop_select(self, val: str):
        self.manual_shop_select = val
        shop = next((s for s in self.shops if s.name == val), None)
        if shop:
            self.manual_currency = shop.currency
            dp = self._lookup_default_price(self.manual_product_name, self.manual_variant, shop.currency)
            if dp > 0:
                self.manual_unit_price = f"{dp:.2f}"

    @rx.event
    def set_manual_custom_shop(self, val: str):
        self.manual_custom_shop = val

    @rx.event
    def set_manual_product_name(self, val: str):
        self.manual_product_name = val
        variants = self.product_variants_map.get(val, ["通用"])
        self.manual_variant = variants[0] if variants else "通用"
        parts = self.product_parts_map.get(f"{val}::{self.manual_variant}", ["整套"])
        self.manual_part_name = parts[0] if parts else "整套"
        dp = self._lookup_default_price(val, self.manual_variant, self.manual_currency)
        if dp > 0:
            self.manual_unit_price = f"{dp:.2f}"

    @rx.event
    def set_manual_variant(self, val: str):
        self.manual_variant = val
        parts = self.product_parts_map.get(f"{self.manual_product_name}::{val}", ["整套"])
        self.manual_part_name = parts[0] if parts else "整套"
        dp = self._lookup_default_price(self.manual_product_name, val, self.manual_currency)
        if dp > 0:
            self.manual_unit_price = f"{dp:.2f}"

    @rx.event
    def set_manual_part_name(self, val: str):
        self.manual_part_name = val

    @rx.event
    def set_manual_qty(self, val: str):
        self.manual_qty = val
        self.manual_remaining_qty = val

    @rx.event
    def set_manual_remaining_qty(self, val: str):
        self.manual_remaining_qty = val

    @rx.event
    def set_manual_unit_price(self, val: str):
        self.manual_unit_price = val

    @rx.event
    def set_manual_currency(self, val: str):
        self.manual_currency = val

    @rx.event
    def set_manual_date(self, val: str):
        self.manual_date = val

    @rx.event
    def set_manual_remarks(self, val: str):
        self.manual_remarks = val

    @rx.event
    def submit_manual_add(self):
        shop_name = (
            self.manual_custom_shop.strip()
            if self.manual_shop_select == "__custom__"
            else self.manual_shop_select.strip()
        )
        if not shop_name:
            return rx.toast("请选择或输入寄售店铺名称", level="error")
        if not self.manual_product_name:
            return rx.toast("请选择商品", level="error")
        try:
            qty = int(self.manual_qty)
            rem = int(self.manual_remaining_qty) if self.manual_remaining_qty.strip() else qty
            up = float(self.manual_unit_price or 0.0)
        except ValueError:
            return rx.toast("数量或单价格式无效", level="error")
        if qty <= 0:
            return rx.toast("总数量必须大于 0", level="error")
        try:
            d = date.fromisoformat(self.manual_date) if self.manual_date else date.today()
        except Exception:
            d = date.today()

        db = self.get_db()
        try:
            service = ConsignmentService(db)
            service.add_manual_consignment(
                shop_id=None,
                shop_name=shop_name,
                product_name=self.manual_product_name,
                variant=self.manual_variant or "通用",
                part_name=self.manual_part_name or "整套",
                quantity=qty,
                remaining_qty=rem,
                unit_price=up,
                currency=self.manual_currency or "CNY",
                date_obj=d,
                remarks=self.manual_remarks.strip(),
            )
            db.commit()
            self.is_manual_add_open = False
            self._reload_all(db)
            return rx.toast("寄售记录已补录添加！")
        except Exception as e:
            db.rollback()
            return rx.toast(f"添加失败: {e}", level="error")
        finally:
            db.close()

    # ==================== 3. Edit / Delete Item ====================

    @rx.event
    def open_edit_modal(self, item_id: int):
        target = next((i for i in self.items if i.id == item_id), None)
        if not target:
            return rx.toast("未找到寄售记录", level="error")
        self.edit_item_id = target.id
        self.edit_shop_name = target.shop_name
        self.edit_product_info = f"{target.product_name} · {target.variant}" + (f" ({target.part_name})" if target.part_name != "整套" else "")
        self.edit_remaining_qty = str(target.remaining_qty)
        self.edit_unit_price = f"{target.unit_price:.2f}"
        self.edit_remarks = target.remarks
        self.is_edit_open = True

    @rx.event
    def close_edit_modal(self):
        self.is_edit_open = False

    @rx.event
    def set_edit_shop_name(self, val: str):
        self.edit_shop_name = val

    @rx.event
    def set_edit_remaining_qty(self, val: str):
        self.edit_remaining_qty = val

    @rx.event
    def set_edit_unit_price(self, val: str):
        self.edit_unit_price = val

    @rx.event
    def set_edit_remarks(self, val: str):
        self.edit_remarks = val

    @rx.event
    def submit_edit(self):
        try:
            rem = int(self.edit_remaining_qty)
            up = float(self.edit_unit_price or 0.0)
        except ValueError:
            return rx.toast("数量或单价必须为有效数字", level="error")
        if rem < 0 or up < 0:
            return rx.toast("剩余数量与单价不能为负数", level="error")

        db = self.get_db()
        try:
            service = ConsignmentService(db)
            service.update_consignment_item(
                self.edit_item_id,
                remaining_qty=rem,
                unit_price=up,
                remarks=self.edit_remarks,
                shop_name=self.edit_shop_name.strip() or None,
            )
            db.commit()
            self.is_edit_open = False
            self._reload_all(db)
            return rx.toast("寄售记录已更新！")
        except Exception as e:
            db.rollback()
            return rx.toast(f"更新失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_consignment_item(self, item_id: int):
        db = self.get_db()
        try:
            service = ConsignmentService(db)
            service.delete_consignment_item(item_id)
            db.commit()
            self._reload_all(db)
            return rx.toast("寄售记录已删除！")
        except Exception as e:
            db.rollback()
            return rx.toast(f"删除失败: {e}", level="error")
        finally:
            db.close()

    # ==================== 4. Return to Warehouse ====================

    @rx.event
    def open_return_single(self, item_id: int):
        target = next((i for i in self.items if i.id == item_id), None)
        if not target or target.remaining_qty <= 0:
            return rx.toast("该条目没有可退回的在店数量", level="error")
        self._prepare_return_modal([target])

    @rx.event
    def open_return_batch(self):
        targets = [i for i in self.items if i.id in self.selected_ids and i.remaining_qty > 0]
        if not targets:
            return rx.toast("请先勾选有在店余量的寄售条目", level="error")
        self._prepare_return_modal(targets)

    def _prepare_return_modal(self, targets: List[ConsignmentLedgerRow]):
        if not self.warehouse_names:
            return
        default_wh = targets[0].warehouse_name
        if default_wh not in self.warehouse_names:
            default_wh = self.warehouse_names[0]
        self.return_warehouse_name = default_wh
        self.return_date = date.today().strftime("%Y-%m-%d")
        self.return_notes = ""
        self.return_lines = [
            ReturnLineRow(
                consignment_item_id=t.id,
                shop_name=t.shop_name,
                product_name=t.product_name,
                variant=t.variant,
                part_name=t.part_name,
                max_qty=t.remaining_qty,
                return_qty_input=str(t.remaining_qty),
            )
            for t in targets
        ]
        self.is_return_open = True

    @rx.event
    def close_return_modal(self):
        self.is_return_open = False

    @rx.event
    def set_return_warehouse_name(self, val: str):
        self.return_warehouse_name = val

    @rx.event
    def set_return_date(self, val: str):
        self.return_date = val

    @rx.event
    def set_return_notes(self, val: str):
        self.return_notes = val

    @rx.event
    def set_return_line_qty(self, item_id: int, val: str):
        self.return_lines = [
            r.model_copy(update={"return_qty_input": val}) if r.consignment_item_id == item_id else r
            for r in self.return_lines
        ]

    @rx.event
    def submit_return(self):
        wh_id = self.warehouse_id_map.get(self.return_warehouse_name)
        if not wh_id:
            return rx.toast("请选择退回入库的目标仓库", level="error")
        entries = []
        for r in self.return_lines:
            raw = (r.return_qty_input or "").strip()
            if not raw:
                continue
            try:
                q = int(raw)
            except ValueError:
                return rx.toast(f"{r.product_name} 退回数量必须为整数", level="error")
            if q < 0 or q > r.max_qty:
                return rx.toast(f"{r.product_name} 退回数量须在 0~{r.max_qty} 之间", level="error")
            if q > 0:
                entries.append({"consignment_item_id": r.consignment_item_id, "return_qty": q})
        if not entries:
            return rx.toast("请至少填写一项大于 0 的退回数量", level="error")

        try:
            d = date.fromisoformat(self.return_date) if self.return_date else date.today()
        except Exception:
            d = date.today()

        db = self.get_db()
        try:
            service = ConsignmentService(db)
            created = service.return_to_warehouse(
                entries=entries,
                warehouse_id=wh_id,
                return_date=d,
                notes=self.return_notes.strip(),
            )
            db.commit()
            sync_all_caches()
            self.is_return_open = False
            self.selected_ids = []
            self._reload_all(db)
            return rx.toast(f"已将 {len(created)} 项寄售商品退回至「{self.return_warehouse_name}」并恢复仓库库存！")
        except Exception as e:
            db.rollback()
            return rx.toast(f"退回失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def revoke_return_record(self, return_id: int):
        db = self.get_db()
        try:
            service = ConsignmentService(db)
            service.revoke_return(return_id)
            db.commit()
            sync_all_caches()
            self._reload_all(db)
            return rx.toast("已撤销该退回单并回滚仓库库存！")
        except Exception as e:
            db.rollback()
            return rx.toast(f"撤销失败: {e}", level="error")
        finally:
            db.close()

    # ==================== 5. Consignment Settlement ====================

    @rx.event
    def open_settle_single(self, item_id: int):
        target = next((i for i in self.items if i.id == item_id), None)
        if not target or target.remaining_qty <= 0:
            return rx.toast("该条目没有可结算的剩余数量", level="error")
        return self._prepare_settle_modal([target])

    @rx.event
    def open_settle_batch(self):
        targets = [i for i in self.items if i.id in self.selected_ids and i.remaining_qty > 0]
        if not targets:
            return rx.toast("请先勾选需要结算且有余量的寄售条目", level="error")
        shop_names = {t.shop_name for t in targets}
        if len(shop_names) > 1:
            return rx.toast("批量结算一次只能针对同一家寄售店，请只勾选同店铺条目", level="error")
        return self._prepare_settle_modal(targets)

    def _prepare_settle_modal(self, targets: List[ConsignmentLedgerRow]):
        if not self.accounts:
            return rx.toast("尚未配置现金类资产账户，请先到公司余额页添加收款账户", level="error")

        shop_name = targets[0].shop_name
        shop = next((s for s in self.shops if s.name == shop_name), None)
        self.settle_shop_id = shop.id if shop else (targets[0].shop_id or 0)
        self.settle_shop_name = shop_name
        self.settle_date = date.today().strftime("%Y-%m-%d")
        currency = shop.currency if shop else (targets[0].currency or "CNY")
        self.settle_currency = currency

        # Match default receiving account
        acc_label = ""
        if shop and shop.default_account_name:
            matched_acc = next((a for a in self.accounts if a.name == shop.default_account_name), None)
            if matched_acc:
                acc_label = matched_acc.label
        if not acc_label:
            same_cur_acc = next((a for a in self.accounts if a.currency == currency), None)
            acc_label = same_cur_acc.label if same_cur_acc else self.accounts[0].label
        self.settle_account_label = acc_label

        fee_rate_pct = (shop.default_fee_rate * 100.0) if shop else 0.0
        self.settle_fee_rate = f"{fee_rate_pct:g}" if fee_rate_pct > 0 else "0"
        self.settle_notes = ""

        lines = []
        for t in targets:
            up = t.unit_price if t.unit_price > 0 else self._lookup_default_price(t.product_name, t.variant, currency)
            qty = t.remaining_qty
            sub = qty * up
            lines.append(
                SettleLineRow(
                    consignment_item_id=t.id,
                    shop_name=t.shop_name,
                    product_name=t.product_name,
                    variant=t.variant,
                    part_name=t.part_name,
                    max_qty=t.remaining_qty,
                    currency=currency,
                    sold_qty_input=str(qty),
                    unit_price_input=f"{up:.2f}" if up > 0 else "0",
                    subtotal_str=f"{sub:,.2f}",
                )
            )
        self.settle_lines = lines
        self._recalc_settle_totals_from_rate(fixed_fee=(shop.default_fee_fixed if shop else 0.0))
        self.is_settle_open = True

    def _compute_settle_gross(self) -> float:
        gross = 0.0
        updated_lines = []
        for l in self.settle_lines:
            try:
                q = int((l.sold_qty_input or "0").strip())
            except ValueError:
                q = 0
            try:
                p = float((l.unit_price_input or "0").strip())
            except ValueError:
                p = 0.0
            sub = max(0, q) * max(0.0, p)
            gross += sub
            updated_lines.append(l.model_copy(update={"subtotal_str": f"{sub:,.2f}"}))
        self.settle_lines = updated_lines
        self.settle_gross_str = f"{gross:,.2f}"
        return gross

    def _recalc_settle_totals_from_rate(self, fixed_fee: float = 0.0):
        gross = self._compute_settle_gross()
        try:
            rate = float((self.settle_fee_rate or "0").strip())
        except ValueError:
            rate = 0.0
        fee = round(gross * rate / 100.0 + fixed_fee, 2)
        net = round(max(0.0, gross - fee), 2)
        self.settle_fee_amount = f"{fee:.2f}"
        self.settle_net_amount = f"{net:.2f}"

    @rx.event
    def close_settle_modal(self):
        self.is_settle_open = False

    @rx.event
    def set_settle_date(self, val: str):
        self.settle_date = val

    @rx.event
    def set_settle_currency(self, val: str):
        self.settle_currency = val

    @rx.event
    def set_settle_account_label(self, val: str):
        self.settle_account_label = val

    @rx.event
    def set_settle_notes(self, val: str):
        self.settle_notes = val

    @rx.event
    def set_settle_line_qty(self, item_id: int, val: str):
        self.settle_lines = [
            l.model_copy(update={"sold_qty_input": val}) if l.consignment_item_id == item_id else l
            for l in self.settle_lines
        ]
        self._recalc_settle_totals_from_rate()

    @rx.event
    def set_settle_line_price(self, item_id: int, val: str):
        self.settle_lines = [
            l.model_copy(update={"unit_price_input": val}) if l.consignment_item_id == item_id else l
            for l in self.settle_lines
        ]
        self._recalc_settle_totals_from_rate()

    @rx.event
    def set_settle_fee_rate(self, val: str):
        self.settle_fee_rate = val
        self._recalc_settle_totals_from_rate()

    @rx.event
    def set_settle_fee_amount(self, val: str):
        self.settle_fee_amount = val
        gross = self._compute_settle_gross()
        try:
            fee = float((val or "0").strip())
        except ValueError:
            return
        net = round(max(0.0, gross - fee), 2)
        self.settle_net_amount = f"{net:.2f}"
        if gross > 0:
            self.settle_fee_rate = f"{round(fee / gross * 100.0, 2):g}"

    @rx.event
    def set_settle_net_amount(self, val: str):
        self.settle_net_amount = val
        gross = self._compute_settle_gross()
        try:
            net = float((val or "0").strip())
        except ValueError:
            return
        fee = round(max(0.0, gross - net), 2)
        self.settle_fee_amount = f"{fee:.2f}"
        if gross > 0:
            self.settle_fee_rate = f"{round(fee / gross * 100.0, 2):g}"

    @rx.event
    def submit_settlement(self):
        acc = next((a for a in self.accounts if a.label == self.settle_account_label), None)
        if not acc:
            return rx.toast("请选择入账账户", level="error")

        items_payload = []
        for l in self.settle_lines:
            try:
                q = int((l.sold_qty_input or "0").strip())
                p = float((l.unit_price_input or "0").strip())
            except ValueError:
                return rx.toast(f"{l.product_name} 售出数量或单价格式错误", level="error")
            if q < 0 or q > l.max_qty:
                return rx.toast(f"{l.product_name} 售出数量须在 0~{l.max_qty} 之间", level="error")
            if q > 0:
                items_payload.append({
                    "consignment_item_id": l.consignment_item_id,
                    "sold_qty": q,
                    "unit_price": p,
                })
        if not items_payload:
            return rx.toast("请至少填写一项大于 0 的售出数量", level="error")

        try:
            fee_rate = float((self.settle_fee_rate or "0").strip()) / 100.0
            fee_amt = float((self.settle_fee_amount or "0").strip())
            net_amt = float((self.settle_net_amount or "0").strip())
        except ValueError:
            return rx.toast("手续费或实收金额格式有误", level="error")

        try:
            d = date.fromisoformat(self.settle_date) if self.settle_date else date.today()
        except Exception:
            d = date.today()

        db = self.get_db()
        try:
            service = ConsignmentService(db)
            st = service.create_settlement(
                shop_id=self.settle_shop_id or None,
                shop_name=self.settle_shop_name,
                items=items_payload,
                account_id=acc.id,
                settlement_date=d,
                currency=self.settle_currency or "CNY",
                fee_rate=fee_rate,
                fee_amount=fee_amt,
                net_amount=net_amt,
                notes=self.settle_notes.strip(),
            )
            db.commit()
            sync_all_caches()
            self.is_settle_open = False
            self.selected_ids = []
            self._reload_all(db)
            return rx.toast(f"寄售结算完成 ({st.settlement_no})！实收 {st.net_amount:,.2f} {st.currency} 已计入「{acc.name}」")
        except Exception as e:
            db.rollback()
            return rx.toast(f"结算失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_settlement_record(self, settlement_id: int):
        db = self.get_db()
        try:
            service = ConsignmentService(db)
            service.delete_settlement(settlement_id)
            db.commit()
            sync_all_caches()
            self._reload_all(db)
            return rx.toast("结算单已撤销回滚！")
        except Exception as e:
            db.rollback()
            return rx.toast(f"撤销结算失败: {e}", level="error")
        finally:
            db.close()

    # ==================== 6. Shop Profile CRUD ====================

    @rx.event
    def open_shop_create(self):
        self.shop_edit_id = 0
        self.shop_form_name = ""
        self.shop_form_currency = "CNY"
        self.shop_form_fee_rate = "0"
        self.shop_form_fee_fixed = "0"
        self.shop_form_account_name = "不指定"
        self.shop_form_contact = ""
        self.shop_form_remarks = ""
        self.is_shop_modal_open = True

    @rx.event
    def open_shop_edit(self, shop_id: int):
        target = next((s for s in self.shops if s.id == shop_id), None)
        if not target:
            return rx.toast("未找到寄售店铺", level="error")
        self.shop_edit_id = target.id
        self.shop_form_name = target.name
        self.shop_form_currency = target.currency or "CNY"
        self.shop_form_fee_rate = f"{target.default_fee_rate * 100.0:g}"
        self.shop_form_fee_fixed = f"{target.default_fee_fixed:g}"
        self.shop_form_account_name = target.default_account_name if target.default_account_name else "不指定"
        self.shop_form_contact = target.contact_info
        self.shop_form_remarks = target.remarks
        self.is_shop_modal_open = True

    @rx.event
    def close_shop_modal(self):
        self.is_shop_modal_open = False

    @rx.event
    def set_shop_form_name(self, val: str):
        self.shop_form_name = val

    @rx.event
    def set_shop_form_currency(self, val: str):
        self.shop_form_currency = val

    @rx.event
    def set_shop_form_fee_rate(self, val: str):
        self.shop_form_fee_rate = val

    @rx.event
    def set_shop_form_fee_fixed(self, val: str):
        self.shop_form_fee_fixed = val

    @rx.event
    def set_shop_form_account_name(self, val: str):
        self.shop_form_account_name = val

    @rx.event
    def set_shop_form_contact(self, val: str):
        self.shop_form_contact = val

    @rx.event
    def set_shop_form_remarks(self, val: str):
        self.shop_form_remarks = val

    @rx.event
    def submit_shop_form(self):
        if not self.shop_form_name.strip():
            return rx.toast("寄售店铺名称不能为空", level="error")
        try:
            rate = float((self.shop_form_fee_rate or "0").strip()) / 100.0
            fixed = float((self.shop_form_fee_fixed or "0").strip())
        except ValueError:
            return rx.toast("费率或固定手续费必须为有效数字", level="error")

        acc_name = "" if self.shop_form_account_name in ("", "不指定") else self.shop_form_account_name.strip()

        db = self.get_db()
        try:
            service = ConsignmentService(db)
            if self.shop_edit_id > 0:
                service.update_shop(
                    self.shop_edit_id,
                    name=self.shop_form_name.strip(),
                    currency=self.shop_form_currency or "CNY",
                    default_fee_rate=rate,
                    default_fee_fixed=fixed,
                    default_account_name=acc_name,
                    contact_info=self.shop_form_contact.strip(),
                    remarks=self.shop_form_remarks.strip(),
                )
                msg = "寄售店铺档案已更新！"
            else:
                service.create_shop(
                    name=self.shop_form_name.strip(),
                    currency=self.shop_form_currency or "CNY",
                    default_fee_rate=rate,
                    default_fee_fixed=fixed,
                    default_account_name=acc_name,
                    contact_info=self.shop_form_contact.strip(),
                    remarks=self.shop_form_remarks.strip(),
                )
                msg = "寄售店铺已创建！"
            db.commit()
            self.is_shop_modal_open = False
            self._reload_all(db)
            return rx.toast(msg)
        except Exception as e:
            db.rollback()
            return rx.toast(f"保存失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_shop_record(self, shop_id: int):
        db = self.get_db()
        try:
            service = ConsignmentService(db)
            service.delete_shop(shop_id)
            db.commit()
            self._reload_all(db)
            return rx.toast("寄售店铺已删除！")
        except Exception as e:
            db.rollback()
            return rx.toast(f"删除失败: {e}", level="error")
        finally:
            db.close()
