"""
Inventory & Warehouses & Consignments, Fixed Assets, Consumables, and Schedule Gantt REST API Routes.
Reuses services.inventory_service, services.asset_service, services.consumable_service, and services.schedule_service.
"""
import calendar
import math
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import verify_auth_token, get_db_session, load_rates_map
from services.inventory_service import InventoryService
from services.asset_service import AssetService
from services.consumable_service import ConsumableService
from services.schedule_service import (
    ScheduleService,
    period_to_index,
    date_to_pixel_offset,
    format_period_range,
    get_current_period,
    PERIOD_MAP,
    PERIOD_LABELS,
)
STAGE_PRESETS = [
    "企划设计",
    "样衣打版",
    "产前样衣",
    "大货投产",
    "预售开启",
    "预售结束",
    "大货出货",
    "质检入库",
    "开售",
    "其他",
]

COLOR_OPTIONS = [
    ("violet", "💜 紫色"),
    ("blue", "💙 蓝色"),
    ("cyan", "🩵 青色"),
    ("green", "💚 绿色"),
    ("amber", "💛 琥珀"),
    ("orange", "🧡 橙色"),
    ("ruby", "❤️ 红色"),
]

STATUS_CHOICES = [
    ("planned", "🕒 计划中"),
    ("in_progress", "🔥 进行中"),
    ("completed", "✅ 已完成"),
    ("delayed", "⚠️ 已延期"),
]
from constants import (
    StockLogReason,
    PRODUCT_COST_CATEGORIES,
    AssetPrefix,
    BalanceCategory,
    to_cny,
)
from models import Product, Warehouse, CompanyBalanceItem
from cache_manager import sync_all_caches

router = APIRouter(tags=["Inventory, Assets & Schedule"])


# ==================== Request Schemas ====================

class MovementMatrixCellPayload(BaseModel):
    color_name: str
    part_name: str = "整套"
    quantity: int


class InventoryMovementRequest(BaseModel):
    product_name: str
    movement_type: str
    is_batch_mode: bool = True
    warehouse_id: Optional[int] = None
    from_warehouse_id: Optional[int] = None
    to_warehouse_id: Optional[int] = None
    date: str
    note: str = ""
    force_confirm_overprod: bool = False
    cells: List[MovementMatrixCellPayload] = []


class WipFixRequest(BaseModel):
    product_id: Optional[int] = None
    product_name: Optional[str] = None


class WarehouseSaveRequest(BaseModel):
    name: str
    location: str = ""
    manager: str = ""
    description: str = ""


class LogNoteUpdateRequest(BaseModel):
    note: str


class ConsignmentCreateRequest(BaseModel):
    recipient: str
    item_name: str
    quantity: int = 1
    unit_price: float = 0.0
    currency: str = "CNY"
    sent_date: str = ""
    note: str = ""


class ConsignmentStatusUpdateRequest(BaseModel):
    status: str
    note: str = ""


class FixedAssetUpdateRequest(BaseModel):
    name: str
    unit_price: float
    remaining_qty: int
    note: str = ""


class FixedAssetWriteOffRequest(BaseModel):
    write_off_qty: int
    write_off_reason: str = ""


class ConsumableChangeRequest(BaseModel):
    item_id: int
    op_mode: str = "consume_internal"  # "consume_internal", "sale_external", "restock"
    change_qty: float = 1.0
    date: str
    note: str = ""
    target_product_id: Optional[int] = None
    target_cost_cat: str = "大货材料费"
    sale_amount: float = 0.0
    sale_currency: str = "CNY"
    sale_account_id: Optional[int] = None
    restock_unit_price: Optional[float] = None


class ConsumableUpdateRequest(BaseModel):
    name: str
    category: str
    unit_price: float
    remaining_qty: float
    shop: str = ""
    note: str = ""
    url: str = ""


class ConsumableLogDateUpdateRequest(BaseModel):
    new_date: str


class ScheduleNodeUpsertRequest(BaseModel):
    item_type: str = "product"  # "product", "event", "other"
    product_id: Optional[int] = None
    platform_name: str = ""
    title: str = ""
    stage_name: str = "企划设计"
    custom_stage: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_year: int = 2026
    start_month: int = 1
    start_period: str = "early"
    end_year: int = 2026
    end_month: int = 1
    end_period: str = "early"
    status: str = "planned"
    color: str = "violet"
    remarks: str = ""


class ScheduleShiftRequest(BaseModel):
    delta_periods: int  # e.g. -1 or +1


class ScheduleLaneDeleteRequest(BaseModel):
    lane_type: str
    product_id: int = 0
    lane_title: str = ""


# ==================== 1. Inventory Management Endpoints ====================

@router.get("/inventory/page")
def get_inventory_page(
    log_product: str = "全部",
    log_variant: str = "全部",
    log_part: str = "全部",
    log_reason: str = "全部",
    log_warehouse: str = "全部",
    log_start_date: str = "",
    log_end_date: str = "",
    log_search: str = "",
    log_page: int = 1,
    log_page_size: int = 40,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    from services.cost_service import CostService
    rates_map = load_rates_map(db)
    service = InventoryService(db)
    cost_service = CostService(db)
    products = service.get_all_products()

    # 1. Product cards with barrel-principle stock overview
    product_cards = []
    for p in products:
        wip_bal = round(float(service.get_wip_balance(p.id) or 0.0), 2)
        m_qty = float(p.marketable_quantity or 0.0)
        make_qty = m_qty if m_qty > 0 else float(p.total_quantity or 0.0)
        c_items = cost_service.get_cost_items(p.id)
        tot_real_cost = sum(float(i.actual_cost or 0.0) for i in c_items)
        unit_cost = round(tot_real_cost / make_qty, 2) if make_qty > 0 else 0.0
        stats_map = service.get_stock_overview_by_parts(p.id, p.name)

        color_details = []
        actual_total_sets = 0
        inspecting_total_sets = 0
        repairing_total_sets = 0
        waiting_total_sets = 0

        for c in (p.colors or []):
            v_name = c.color_name
            s = stats_map.get(v_name, {})
            planned = int(s.get("planned", 0))
            produced = int(s.get("produced", 0))
            inspecting = int(s.get("inspecting", 0))
            repaired = int(s.get("repaired", 0))
            actual_qty = int(s.get("actual", 0))
            waiting_qty = max(0, planned - produced - inspecting - repaired)

            actual_total_sets += actual_qty
            inspecting_total_sets += inspecting
            repairing_total_sets += repaired
            waiting_total_sets += waiting_qty

            raw_parts = s.get("parts", [])
            min_equiv = min((int(pt.get("calculable_sets", 0)) for pt in raw_parts), default=0)
            part_dtos = []
            for pt in raw_parts:
                pt_req = int(pt.get("req_qty", 1) or 1)
                pt_prod = int(pt.get("produced", 0))
                pt_insp = int(pt.get("inspecting", 0))
                pt_rep = int(pt.get("repaired", 0))
                pt_act = int(pt.get("actual_qty", 0))
                pt_eq = int(pt.get("calculable_sets", 0))
                pt_wait = max(0, planned * pt_req - pt_prod - pt_insp - pt_rep)
                part_dtos.append({
                    "part_name": pt.get("part_name", ""),
                    "req_per_set": pt_req,
                    "actual_stock": pt_act,
                    "inspecting_stock": pt_insp,
                    "repairing_stock": pt_rep,
                    "waiting_stock": pt_wait,
                    "equivalent_sets": pt_eq,
                    "is_bottleneck": len(raw_parts) > 1 and pt_eq == min_equiv,
                })

            excess_strs = [f"{pt_n} +{ex_q}" for pt_n, ex_q in s.get("excess", {}).items() if int(ex_q) > 0]
            color_details.append({
                "color_name": v_name,
                "actual_sets": actual_qty,
                "inspecting_sets": inspecting,
                "repairing_sets": repaired,
                "waiting_sets": waiting_qty,
                "parts": part_dtos,
                "excess_parts": excess_strs,
            })

        stock_val_cny = round(actual_total_sets * unit_cost, 2)
        product_cards.append({
            "product_id": p.id,
            "product_name": p.name,
            "production_quantity": int(p.total_quantity or 0),
            "marketable_quantity": int(p.marketable_quantity or 0),
            "unit_cost": unit_cost,
            "actual_total_sets": actual_total_sets,
            "inspecting_total_sets": inspecting_total_sets,
            "repairing_total_sets": repairing_total_sets,
            "waiting_total_sets": waiting_total_sets,
            "stock_value_cny": stock_val_cny,
            "wip_value_cny": wip_bal,
            "colors": color_details,
        })

    # 2. Warehouses & stock breakdown
    whs = service.get_all_warehouses()
    wh_details = service.get_warehouse_inventory_details()
    wh_cards = []
    for w in whs:
        w_stock = wh_details.get(w.id, {}).get("stock", {})
        prod_stocks = []
        wh_total_sets = 0
        for prod_n, v_dict in w_stock.items():
            p_match = next((p for p in products if p.name == prod_n), None)
            color_stocks = []
            for var_n, pt_dict in v_dict.items():
                reqs = {"整套": 1}
                if p_match:
                    c_match = next((c for c in p_match.colors if c.color_name == var_n), None)
                    if c_match and c_match.parts:
                        reqs = {pt.part_name: max(1, int(pt.quantity or 1)) for pt in c_match.parts}
                possible_sets = max(0, min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items())) if reqs else 0
                wh_total_sets += possible_sets
                parts_txt = ", ".join(f"{pt_n}:{qty}" for pt_n, qty in pt_dict.items() if qty != 0)
                if parts_txt or possible_sets > 0:
                    color_stocks.append({
                        "color_name": var_n,
                        "complete_sets": possible_sets,
                        "parts_summary": parts_txt,
                    })
            if color_stocks:
                prod_stocks.append({
                    "product_name": prod_n,
                    "colors": color_stocks,
                })

        wh_cards.append({
            "id": w.id,
            "name": w.name,
            "location": "",
            "manager": "",
            "description": w.remarks or "",
            "total_sets": wh_total_sets,
            "products": prod_stocks,
        })

    # 3. Consignments
    raw_cons = service.get_all_consignments()
    cons_list = []
    for c in raw_cons:
        date_str = c.date.strftime("%Y-%m-%d") if c.date else ""
        rem_q = c.remaining_qty if c.remaining_qty is not None else (c.quantity or 0)
        init_q = c.quantity or 0
        if rem_q <= 0:
            s_label = "已结算/归还"
        elif rem_q < init_q:
            s_label = f"部分售出(余{rem_q}/{init_q})"
        else:
            s_label = "寄售/借出中"

        item_disp = f"{c.product_name or ''} - {c.variant or '通用'}" if c.product_name else (c.variant or "通用")
        cons_list.append({
            "id": c.id,
            "recipient": c.shop_name or "",
            "item_name": item_disp,
            "quantity": init_q,
            "unit_price": 0.0,
            "currency": "CNY",
            "total_value": 0.0,
            "cny_equiv": 0.0,
            "status": s_label,
            "sent_date": date_str,
            "note": c.remarks or "",
        })

    # 4. Physical Inventory Logs with 7-dimension filter
    whs_map = {w.id: w.name for w in whs}
    raw_logs = service.get_recent_logs(product_name=None, limit=None)
    all_reasons = sorted(list({l.reason for l in raw_logs if l.reason}))

    filtered_logs = []
    q_log = log_search.strip().lower()
    for l in raw_logs:
        part_display = l.part_name if l.part_name else "整套"
        wh_display = whs_map.get(l.warehouse_id, "默认仓")
        date_str = l.date.strftime("%Y-%m-%d") if l.date else ""

        if log_product not in ("", "全部", "全部商品") and l.product_name != log_product:
            continue
        if log_variant not in ("", "全部", "全部款式") and l.variant != log_variant:
            continue
        if log_part not in ("", "全部", "全部规格"):
            if log_part in ("整套", "仅成套") and part_display != "整套":
                continue
            elif log_part == "仅散件" and part_display == "整套":
                continue
            elif log_part not in ("整套", "仅成套", "仅散件") and part_display != log_part:
                continue
        if log_warehouse not in ("", "全部", "全部仓库") and wh_display != log_warehouse:
            continue
        if log_reason not in ("", "全部", "全部类型") and l.reason != log_reason:
            continue
        if log_start_date and date_str < log_start_date:
            continue
        if log_end_date and date_str > log_end_date:
            continue
        if q_log:
            if not (
                q_log in date_str.lower()
                or q_log in (l.note or "").lower()
                or q_log in (l.product_name or "").lower()
                or q_log in (l.variant or "").lower()
                or q_log in part_display.lower()
                or q_log in wh_display.lower()
                or q_log in (l.reason or "").lower()
            ):
                continue

        filtered_logs.append({
            "id": l.id,
            "date_str": date_str,
            "product_name": l.product_name or "",
            "variant": l.variant or "",
            "part_name": part_display,
            "change_amount": int(l.change_amount or 0),
            "reason": l.reason or "",
            "warehouse_name": wh_display,
            "note": l.note or "",
        })

    total_logs = len(filtered_logs)
    total_pages = max(1, math.ceil(total_logs / log_page_size))
    p_idx = max(1, min(log_page, total_pages))
    start_i = (p_idx - 1) * log_page_size
    paginated_logs = filtered_logs[start_i: start_i + log_page_size]

    return {
        "product_cards": product_cards,
        "warehouses": wh_cards,
        "consignments": cons_list,
        "logs": paginated_logs,
        "log_total_items": total_logs,
        "log_total_pages": total_pages,
        "log_page_number": p_idx,
        "log_reasons": all_reasons,
        "movement_types": [
            StockLogReason.IN_INSPECT,
            StockLogReason.INSPECT_COMPLETED,
            StockLogReason.REPAIR_OUT,
            StockLogReason.REPAIR_IN,
            StockLogReason.OTHER_IN,
            StockLogReason.OUT_STOCK,
            StockLogReason.TRANSFER,
            StockLogReason.INSPECT_REVERSAL,
        ],
        "currencies": list(rates_map.keys()),
    }


@router.post("/inventory/movement")
def submit_inventory_movement(
    req: InventoryMovementRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    service = InventoryService(db)
    prod = db.query(Product).filter(Product.name == req.product_name).first()
    if not prod:
        raise HTTPException(status_code=404, detail="商品不存在")

    wh_id = req.from_warehouse_id if req.movement_type == StockLogReason.TRANSFER else req.warehouse_id
    to_wh_id = req.to_warehouse_id

    try:
        date_val = date.fromisoformat(req.date)
    except Exception:
        date_val = date.today()

    entries = [
        {
            "variant": c.color_name,
            "part_name": None if c.part_name in ("", "整套") else c.part_name,
            "quantity": c.quantity,
        }
        for c in req.cells
        if c.quantity > 0
    ]
    if not entries:
        raise HTTPException(status_code=400, detail="请至少输入一个大于 0 的变动数量")

    is_check_overprod = req.movement_type == StockLogReason.INSPECT_COMPLETED

    try:
        if is_check_overprod and not req.force_confirm_overprod:
            stats_map = service.get_stock_overview_by_parts(prod.id, prod.name)
            for e in entries:
                v = e["variant"]
                in_q = e["quantity"]
                v_stat = stats_map.get(v, {})
                planned = int(v_stat.get("planned", 0))
                produced = int(v_stat.get("produced", 0))
                if e["part_name"] is None and planned > 0 and (produced + in_q) > planned:
                    return {
                        "requires_overprod_confirm": True,
                        "overprod_warning_msg": f"款式【{v}】本次入库后将超出计划数 {(produced + in_q) - planned} 套 (计划:{planned}, 已产:{produced}, 本次:{in_q})，是否确认继续入库？",
                        "message": "",
                    }

        msg = service.add_batch_inventory_movements(
            product_id=prod.id,
            product_name=prod.name,
            entries=entries,
            move_type=req.movement_type,
            date_obj=date_val,
            batch_remark=req.note.strip(),
            warehouse_id=wh_id,
            to_warehouse_id=to_wh_id,
        )
        service.commit()
        sync_all_caches()
        return {
            "requires_overprod_confirm": False,
            "overprod_warning_msg": "",
            "message": msg,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"库存操作失败: {e}")


@router.post("/inventory/clear-wip")
def clear_product_wip(
    req: WipFixRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    prod = None
    if req.product_id:
        prod = db.query(Product).filter(Product.id == req.product_id).first()
    elif req.product_name:
        prod = db.query(Product).filter(Product.name == req.product_name).first()
    if not prod:
        raise HTTPException(status_code=404, detail="商品不存在")
    try:
        service = InventoryService(db)
        service.clear_wip_for_product(prod.id)
        sync_all_caches()
        return {"message": "在制资产清零成功，预计销售数与大货重算完成！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"操作失败: {e}")


@router.post("/inventory/warehouses")
def add_warehouse(
    req: WarehouseSaveRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="仓库名称不能为空")
    try:
        service = InventoryService(db)
        remarks_parts = [p for p in [req.location.strip(), req.manager.strip(), req.description.strip()] if p]
        service.add_warehouse(req.name.strip(), " | ".join(remarks_parts))
        return {"message": "仓库开立成功！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"开立失败: {e}")


@router.put("/inventory/warehouses/{wh_id}")
def update_warehouse(
    wh_id: int,
    req: WarehouseSaveRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    wh = db.query(Warehouse).filter(Warehouse.id == wh_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="仓库不存在")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="仓库名称不能为空")
    try:
        wh.name = req.name.strip()
        remarks_parts = [p for p in [req.location.strip(), req.manager.strip(), req.description.strip()] if p]
        wh.remarks = " | ".join(remarks_parts)
        db.commit()
        return {"message": "仓库信息已更新！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"更新失败: {e}")


@router.delete("/inventory/warehouses/{wh_id}")
def delete_warehouse(
    wh_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = InventoryService(db)
        service.delete_warehouse(wh_id)
        return {"message": "仓库已成功注销！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"注销失败: {e}")


@router.put("/inventory/logs/{log_id}")
def update_inventory_log_note(
    log_id: int,
    req: LogNoteUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = InventoryService(db)
        service.update_logs_batch({log_id: {"详情": req.note.strip()}})
        return {"message": "库存流水备注已更新！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"更新失败: {e}")


@router.delete("/inventory/logs/{log_id}")
def delete_inventory_log_cascade(
    log_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = InventoryService(db)
        msg = service.delete_log_cascade(log_id)
        sync_all_caches()
        return {"message": f"级联删除成功: {msg}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除失败: {e}")


@router.post("/inventory/consignments")
def add_consignment(
    req: ConsignmentCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.recipient.strip() or not req.item_name.strip():
        raise HTTPException(status_code=400, detail="寄售接收方和物品名称不能为空")
    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="寄售数量必须大于 0")
    try:
        d = date.fromisoformat(req.sent_date) if req.sent_date else date.today()
    except Exception:
        d = date.today()

    try:
        service = InventoryService(db)
        parts = [p.strip() for p in req.item_name.split("-", 1)]
        prod_name = parts[0]
        var_name = parts[1] if len(parts) > 1 else "通用"
        service.add_consignment_item(
            shop_name=req.recipient.strip(),
            product_name=prod_name,
            variant=var_name,
            quantity=req.quantity,
            remaining_qty=req.quantity,
            remarks=req.note.strip(),
            date_obj=d,
        )
        service.commit()
        return {"message": "寄售记录已成功添加！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"添加失败: {e}")


@router.put("/inventory/consignments/{item_id}/status")
def update_consignment_status(
    item_id: int,
    req: ConsignmentStatusUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    from models import ConsignmentItem
    item = db.query(ConsignmentItem).filter(ConsignmentItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="寄售记录不存在")
    try:
        rem_qty = 0 if req.status in ("已结算/归还", "已售罄") else (item.quantity or 1)
        service = InventoryService(db)
        service.update_consignment_item(
            item_id=item_id,
            remaining_qty=rem_qty,
            remarks=req.note.strip() or (item.remarks or ""),
            shop_name=item.shop_name,
        )
        service.commit()
        return {"message": f"寄售状态已更新为: {req.status}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"更新失败: {e}")


@router.delete("/inventory/consignments/{item_id}")
def delete_consignment(
    item_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = InventoryService(db)
        service.delete_consignment_item(item_id)
        service.commit()
        return {"message": "寄售记录已删除！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除失败: {e}")


# ==================== 2. Fixed Assets Endpoints ====================

@router.get("/assets")
def list_fixed_assets(
    search_query: str = "",
    log_page: int = 1,
    log_page_size: int = 30,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    assets = AssetService.get_all_assets(db)
    _, remain_val_cny, _ = AssetService.calculate_asset_totals(assets, rates_map)

    currency_totals: Dict[str, float] = {}
    for a in assets:
        curr = getattr(a, "currency", "CNY") or "CNY"
        rem_orig = float(a.unit_price or 0.0) * int(a.remaining_qty or 0)
        if rem_orig > 0:
            currency_totals[curr] = currency_totals.get(curr, 0.0) + rem_orig

    kw = search_query.strip().lower()
    asset_rows = []
    for a in sorted(assets, key=lambda x: x.id, reverse=True):
        if kw and not (
            kw in (a.name or "").lower()
            or kw in (a.shop_name or "").lower()
            or kw in (a.remarks or "").lower()
        ):
            continue
        curr = getattr(a, "currency", "CNY") or "CNY"
        u_price = float(a.unit_price or 0.0)
        rem_q = int(a.remaining_qty or 0)
        init_q = int(a.quantity or 0)
        rem_orig = u_price * rem_q
        rem_cny = to_cny(rem_orig, curr, rates_map)
        note_str = " | ".join(p for p in [a.shop_name or "", a.remarks or ""] if p)

        asset_rows.append({
            "id": a.id,
            "name": a.name or "",
            "purchase_date": a.purchase_date.strftime("%Y-%m-%d") if a.purchase_date else "",
            "unit_price": round(u_price, 2),
            "currency": curr,
            "initial_qty": init_q,
            "remaining_qty": rem_q,
            "total_val": round(rem_orig, 2),
            "cny_val": round(rem_cny, 2),
            "note": note_str,
        })

    all_logs = AssetService.get_asset_logs(db, limit=500)
    total_logs = len(all_logs)
    total_pages = max(1, math.ceil(total_logs / log_page_size))
    p_idx = max(1, min(log_page, total_pages))
    start_i = (p_idx - 1) * log_page_size
    page_logs = all_logs[start_i: start_i + log_page_size]

    log_rows = [
        {
            "id": l.id,
            "date": l.date.strftime("%Y-%m-%d") if l.date else "",
            "asset_name": l.asset_name or "",
            "change_qty": -abs(int(l.decrease_qty or 0)),
            "note": l.reason or "",
        }
        for l in page_logs
    ]

    return {
        "total_cny": round(remain_val_cny, 2),
        "currency_breakdown": [
            {
                "currency": k,
                "original_amount": round(v, 2),
                "cny_equiv": round(to_cny(v, k, rates_map), 2),
            }
            for k, v in sorted(currency_totals.items())
        ],
        "assets": asset_rows,
        "logs": log_rows,
        "log_total_items": total_logs,
        "log_total_pages": total_pages,
        "log_page_number": p_idx,
    }


@router.put("/assets/{asset_id}")
def update_fixed_asset(
    asset_id: int,
    req: FixedAssetUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="资产名称不能为空")
    ok = AssetService.update_asset_info(
        db,
        asset_id,
        {
            "name": req.name.strip(),
            "unit_price": req.unit_price,
            "remaining_qty": req.remaining_qty,
            "remarks": req.note.strip(),
        },
    )
    if not ok:
        raise HTTPException(status_code=404, detail="固定资产不存在")
    sync_all_caches()
    return {"message": "固定资产信息已更新"}


@router.post("/assets/{asset_id}/write-off")
def write_off_fixed_asset(
    asset_id: int,
    req: FixedAssetWriteOffRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if req.write_off_qty <= 0:
        raise HTTPException(status_code=400, detail="核销数量必须大于 0")
    try:
        name = AssetService.write_off_asset(
            db,
            asset_id,
            req.write_off_qty,
            req.write_off_reason.strip() or "常规报废/核销",
        )
        sync_all_caches()
        return {"message": f"已成功核销固定资产【{name}】x{req.write_off_qty}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/assets/{asset_id}")
def delete_fixed_asset(
    asset_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    from models import FixedAsset
    asset = db.query(FixedAsset).filter(FixedAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="固定资产不存在")
    try:
        db.delete(asset)
        db.commit()
        sync_all_caches()
        return {"message": "固定资产记录已删除"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除失败: {e}")


# ==================== 3. Consumables Endpoints ====================

@router.get("/consumables")
def list_consumables(
    search_query: str = "",
    filter_category: str = "全部",
    log_page: int = 1,
    log_page_size: int = 30,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    service = ConsumableService(db)
    items = service.get_all_consumables()

    all_cats = sorted(list({i.category for i in items if i.category}))
    currency_totals: Dict[str, float] = {}
    total_remain_cny = 0.0

    for i in items:
        curr = getattr(i, "currency", "CNY") or "CNY"
        rem_val = float(i.unit_price or 0.0) * float(i.remaining_qty or 0)
        if rem_val > 0:
            currency_totals[curr] = currency_totals.get(curr, 0.0) + rem_val
            total_remain_cny += to_cny(rem_val, curr, rates_map)

    kw = search_query.strip().lower()
    item_rows = []
    for i in sorted(items, key=lambda x: x.id, reverse=True):
        if filter_category not in ("", "全部") and i.category != filter_category:
            continue
        if kw and not (
            kw in (i.name or "").lower()
            or kw in (i.category or "").lower()
            or kw in (i.shop_name or "").lower()
            or kw in (i.remarks or "").lower()
        ):
            continue
        curr = getattr(i, "currency", "CNY") or "CNY"
        u_price = float(i.unit_price or 0.0)
        rem_q = float(i.remaining_qty or 0)
        rem_orig = u_price * rem_q
        rem_cny = to_cny(rem_orig, curr, rates_map)

        item_rows.append({
            "id": i.id,
            "name": i.name or "",
            "category": i.category or "未分类",
            "purchase_date": i.purchase_date.strftime("%Y-%m-%d") if i.purchase_date else "",
            "unit_price": round(u_price, 4),
            "currency": curr,
            "initial_qty": float(i.initial_quantity or 0),
            "remaining_qty": rem_q,
            "total_val": round(rem_orig, 2),
            "cny_val": round(rem_cny, 2),
            "shop": i.shop_name or "",
            "note": i.remarks or "",
            "url": getattr(i, "url", "") or "",
        })

    all_logs = service.get_logs()
    total_logs = len(all_logs)
    total_pages = max(1, math.ceil(total_logs / log_page_size))
    p_idx = max(1, min(log_page, total_pages))
    start_i = (p_idx - 1) * log_page_size
    page_logs = all_logs[start_i: start_i + log_page_size]

    log_rows = [
        {
            "id": l.id,
            "date": l.date.strftime("%Y-%m-%d") if l.date else "",
            "item_name": l.item_name or "",
            "change_qty": float(l.change_qty or 0),
            "value_cny": round(float(l.value_cny or 0.0), 2),
            "note": l.note or "",
        }
        for l in page_logs
    ]

    cash_accounts = db.query(CompanyBalanceItem).filter(
        CompanyBalanceItem.name.like(f"{AssetPrefix.CASH}%"),
        CompanyBalanceItem.category == BalanceCategory.ASSET,
    ).all()
    products = service.get_all_products()

    return {
        "total_cny": round(total_remain_cny, 2),
        "currency_breakdown": [
            {
                "currency": k,
                "original_amount": round(v, 2),
                "cny_equiv": round(to_cny(v, k, rates_map), 2),
            }
            for k, v in sorted(currency_totals.items())
        ],
        "items": item_rows,
        "categories": all_cats,
        "products": [{"id": p.id, "name": p.name} for p in products],
        "cash_accounts": [
            {
                "id": a.id,
                "name": a.name,
                "currency": a.currency or "CNY",
                "amount": round(float(a.amount or 0.0), 2),
            }
            for a in cash_accounts
        ],
        "cost_categories": PRODUCT_COST_CATEGORIES,
        "logs": log_rows,
        "log_total_items": total_logs,
        "log_total_pages": total_pages,
        "log_page_number": p_idx,
    }


@router.post("/consumables/change")
def process_consumable_change(
    req: ConsumableChangeRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if req.change_qty <= 0:
        raise HTTPException(status_code=400, detail="变动数量必须大于 0")

    service = ConsumableService(db)
    item = service.get_consumable_by_id(req.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="耗材不存在")

    is_restock = req.op_mode == "restock"
    delta_qty = int(round(req.change_qty)) if is_restock else -int(round(req.change_qty))

    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    rates_map = load_rates_map(db)
    sale_info = None
    cost_info = None
    svc_mode = "normal"

    if req.op_mode == "consume_internal":
        if req.target_product_id:
            svc_mode = "cost"
            cost_info = {
                "product_id": req.target_product_id,
                "category": req.target_cost_cat or "材料费",
                "remark": req.note.strip(),
            }
    elif req.op_mode == "sale_external":
        if req.sale_amount <= 0:
            raise HTTPException(status_code=400, detail="变卖销售金额必须大于 0")
        svc_mode = "sale"
        sale_info = {
            "content": f"出售耗材: {item.name}",
            "source": "外部出售",
            "amount": req.sale_amount,
            "currency": req.sale_currency or "CNY",
            "account_id": req.sale_account_id,
            "remark": req.note.strip(),
        }

    try:
        if is_restock and req.restock_unit_price is not None and req.restock_unit_price > 0:
            item.unit_price = req.restock_unit_price
        item_name, d_qty, link_msg = service.process_inventory_change(
            item_name=item.name,
            date_obj=dt,
            delta_qty=delta_qty,
            rates_map=rates_map,
            mode=svc_mode,
            sale_info=sale_info,
            cost_info=cost_info,
            base_remark=req.note.strip(),
        )
        sync_all_caches()
        return {"message": f"已记录【{item_name}】库存变动 ({d_qty:+d}){link_msg}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/consumables/{item_id}")
def update_consumable_item(
    item_id: int,
    req: ConsumableUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsumableService(db)
        existing = service.get_consumable_by_id(item_id)
        if not existing:
            raise HTTPException(status_code=404, detail="耗材不存在")
        service.update_items_batch({
            item_id: {
                "name": req.name.strip(),
                "category": req.category.strip(),
                "currency": getattr(existing, "currency", "CNY") or "CNY",
                "unit_price": req.unit_price,
                "remaining_qty": int(round(req.remaining_qty)),
                "shop_name": req.shop.strip(),
                "remarks": req.note.strip(),
                "url": req.url.strip(),
            }
        })
        sync_all_caches()
        return {"message": "其他资产/耗材信息已更新"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"修改失败: {e}")


@router.delete("/consumables/{item_id}")
def delete_consumable_item(
    item_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsumableService(db)
        item = service.get_consumable_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="耗材不存在")
        db.delete(item)
        db.commit()
        sync_all_caches()
        return {"message": "耗材记录已删除"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除失败: {e}")


@router.put("/consumables/logs/{log_id}/date")
def update_consumable_log_date(
    log_id: int,
    req: ConsumableLogDateUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        dt = date.fromisoformat(req.new_date)
    except Exception:
        raise HTTPException(status_code=400, detail="日期格式无效，请使用 YYYY-MM-DD")
    try:
        service = ConsumableService(db)
        service.update_logs_batch({log_id: {"日期": dt}})
        return {"message": "日志日期已更新"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"修改失败: {e}")


# ==================== 4. Schedule Management Endpoints ====================

@router.get("/schedule")
def get_schedule_data(
    filter_type: str = "all",
    custom_min_year: Optional[int] = None,
    custom_max_year: Optional[int] = None,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    c_y, c_m, c_p = get_current_period()
    curr_year_col_index = (c_m - 1) * 3 + PERIOD_MAP.get(c_p, 0) + 1

    service = ScheduleService(db)
    prods = service.get_all_products()
    product_options = [{"id": p.id, "name": p.name} for p in prods]

    plats = service.get_all_platforms()
    platform_options = [p.name for p in plats] if plats else ["微店", "Booth", "线下展会", "淘宝", "小红书"]

    all_nodes = service.get_nodes(year=None, item_type="all")
    actual_min_param = custom_min_year if isinstance(custom_min_year, int) else None
    actual_max_param = custom_max_year if isinstance(custom_max_year, int) else None
    min_y = min(actual_min_param or (c_y - 1), c_y - 1)
    max_y = max(actual_max_param or (c_y + 1), c_y + 1)
    for an in all_nodes:
        if an.start_year and an.start_year < min_y:
            min_y = an.start_year
        if an.end_year and an.end_year > max_y:
            max_y = an.end_year

    timeline_years = list(range(min_y, max_y + 1))
    total_timeline_px = float(len(timeline_years) * 3600)
    curr_col_index = (c_y - min_y) * 36 + curr_year_col_index if (min_y <= c_y <= max_y) else 0

    raw_nodes = (
        all_nodes
        if filter_type == "all"
        else [n for n in all_nodes if n.item_type == filter_type]
    )

    status_map = dict(STATUS_CHOICES)
    node_items = []
    total = 0
    in_prog = 0
    comp = 0
    delay = 0

    for n in raw_nodes:
        total += 1
        if n.status == "in_progress":
            in_prog += 1
        elif n.status == "completed":
            comp += 1
        elif n.status == "delayed":
            delay += 1

        p_name = n.product.name if n.product else ""
        if n.item_type == "product":
            if n.stage_name == "开售":
                stage_disp = f"开售 ({n.platform_name or '全部平台'})"
            elif n.stage_name == "其他":
                stage_disp = n.custom_stage or "其他"
            else:
                stage_disp = n.stage_name or "工期"
            display_title = f"{n.title or p_name} - {stage_disp}"
            bar_title = stage_disp
        else:
            display_title = n.title
            bar_title = display_title

        if n.start_date:
            try:
                s_dt = datetime.strptime(n.start_date, "%Y-%m-%d")
                s_y, s_m, s_d = s_dt.year, s_dt.month, s_dt.day
            except Exception:
                s_y, s_m, s_d = n.start_year, n.start_month, 1
        else:
            s_y, s_m = n.start_year, n.start_month
            s_d = 1 if n.start_period == "early" else (11 if n.start_period == "mid" else 21)

        if n.end_date:
            try:
                e_dt = datetime.strptime(n.end_date, "%Y-%m-%d")
                e_y, e_m, e_d = e_dt.year, e_dt.month, e_dt.day
            except Exception:
                e_y, e_m, e_d = n.end_year, n.end_month, 28
        else:
            e_y, e_m = n.end_year, n.end_month
            days_in_m = calendar.monthrange(e_y, e_m)[1]
            e_d = 10 if n.end_period == "early" else (20 if n.end_period == "mid" else days_in_m)

        start_x = (
            0.0
            if s_y < min_y
            else (
                (s_y - min_y) * 3600.0 + date_to_pixel_offset(s_y, s_m, s_d, is_end=False)
                if s_y <= max_y
                else total_timeline_px
            )
        )
        end_x = (
            total_timeline_px
            if e_y > max_y
            else (
                (e_y - min_y) * 3600.0 + date_to_pixel_offset(e_y, e_m, e_d, is_end=True)
                if e_y >= min_y
                else 0.0
            )
        )

        is_vis = not (e_y < min_y or s_y > max_y or end_x <= start_x)
        if is_vis:
            left_px = round(max(0.0, min(total_timeline_px, start_x)), 1)
            right_px = round(max(0.0, min(total_timeline_px, end_x)), 1)
            width_px = round(max(52.0, right_px - left_px), 1)
        else:
            left_px, width_px = 0.0, 52.0

        range_txt = format_period_range(
            n.start_year, n.start_month, n.start_period,
            n.end_year, n.end_month, n.end_period,
            n.start_date or "", n.end_date or "",
        )
        s_lbl = PERIOD_LABELS.get(n.start_period, "上旬")
        e_lbl = PERIOD_LABELS.get(n.end_period, "上旬")
        if n.start_date and n.end_date:
            date_badge = f"📅 {n.start_date}" if n.start_date == n.end_date else f"📅 {n.start_date} ~ {n.end_date}"
        elif n.start_date:
            date_badge = f"📅 {n.start_date} ~ {n.end_month}月{e_lbl}"
        elif n.end_date:
            date_badge = f"📅 {n.start_month}月{s_lbl} ~ {n.end_date}"
        else:
            date_badge = f"🗓️ {n.start_month}月{s_lbl} ~ {n.end_month}月{e_lbl}"

        node_items.append({
            "id": n.id,
            "item_type": n.item_type,
            "product_id": n.product_id or 0,
            "product_name": p_name,
            "platform_name": n.platform_name or "",
            "title": n.title,
            "stage_name": n.stage_name or "",
            "custom_stage": n.custom_stage or "",
            "display_title": display_title,
            "bar_title": bar_title,
            "start_date": n.start_date or "",
            "end_date": n.end_date or "",
            "start_year": n.start_year,
            "start_month": n.start_month,
            "start_period": n.start_period,
            "end_year": n.end_year,
            "end_month": n.end_month,
            "end_period": n.end_period,
            "range_str": range_txt,
            "display_date_range": date_badge,
            "status": n.status,
            "status_label": status_map.get(n.status, "🕒 计划中"),
            "color": n.color or "violet",
            "remarks": n.remarks or "",
            "left_px": left_px,
            "width_px": width_px,
            "is_visible_in_year": is_vis,
        })

    # Build Lanes
    lanes_list = []
    prod_node_map: Dict[int, List[Dict[str, Any]]] = {}
    for ni in node_items:
        if ni["item_type"] == "product":
            prod_node_map.setdefault(ni["product_id"] or 0, []).append(ni)

    if filter_type in ("all", "product"):
        for p_dict in product_options:
            p_id = p_dict["id"]
            p_name = p_dict["name"]
            if p_id in prod_node_map:
                p_nodes = prod_node_map[p_id]
                lanes_list.append({
                    "lane_id": f"prod_{p_id}",
                    "lane_type": "product",
                    "product_id": p_id,
                    "lane_title": f"👗 {p_name}",
                    "badge_label": "商品工期",
                    "nodes": p_nodes,
                    "node_count": len(p_nodes),
                })

    event_node_map: Dict[str, List[Dict[str, Any]]] = {}
    for ni in node_items:
        if ni["item_type"] == "event":
            t_key = ni["title"].strip() if ni["title"] else "展会与活动"
            event_node_map.setdefault(t_key, []).append(ni)

    if filter_type in ("all", "event"):
        for t_name, e_nodes in event_node_map.items():
            lanes_list.append({
                "lane_id": f"event_{t_name}",
                "lane_type": "event",
                "product_id": 0,
                "lane_title": f"🎪 {t_name}",
                "badge_label": "展会活动",
                "nodes": e_nodes,
                "node_count": len(e_nodes),
            })

    other_node_map: Dict[str, List[Dict[str, Any]]] = {}
    for ni in node_items:
        if ni["item_type"] == "other":
            t_key = ni["title"].strip() if (ni["title"] and ni["title"] != "运营与综合事务") else "其他"
            other_node_map.setdefault(t_key, []).append(ni)

    if filter_type in ("all", "other"):
        for t_name, o_nodes in other_node_map.items():
            lanes_list.append({
                "lane_id": f"other_{t_name}",
                "lane_type": "other",
                "product_id": 0,
                "lane_title": f"📌 {t_name}",
                "badge_label": "其他日程",
                "nodes": o_nodes,
                "node_count": len(o_nodes),
            })

    # Upcoming nodes (within current period to +4 periods)
    curr_global_idx = period_to_index(c_y, c_m, c_p)
    upcoming = []
    for ni in node_items:
        n_s_idx = period_to_index(ni["start_year"], ni["start_month"], ni["start_period"])
        n_e_idx = period_to_index(ni["end_year"], ni["end_month"], ni["end_period"])
        if n_e_idx >= curr_global_idx and n_s_idx <= curr_global_idx + 4:
            upcoming.append(ni)

    return {
        "curr_year": c_y,
        "curr_month": c_m,
        "curr_period": c_p,
        "current_period_display": f"{c_y} 年 {c_m} 月 {PERIOD_LABELS.get(c_p, '下旬')}",
        "curr_col_index": curr_col_index,
        "timeline_years": timeline_years,
        "stats": {
            "total": total,
            "in_progress": in_prog,
            "completed": comp,
            "delayed": delay,
        },
        "lanes": lanes_list,
        "upcoming_nodes": upcoming[:8],
        "product_options": product_options,
        "platform_options": platform_options,
        "stage_presets": STAGE_PRESETS,
        "color_choices": [{"code": c[0], "label": c[1]} for c in COLOR_OPTIONS],
        "status_choices": [{"code": s[0], "label": s[1]} for s in STATUS_CHOICES],
    }


@router.post("/schedule/nodes")
def create_schedule_node(
    req: ScheduleNodeUpsertRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ScheduleService(db)
        node = service.create_node(req.model_dump())
        return {"message": f"工期节点【{node.title or node.stage_name}】已创建", "id": node.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"创建节点失败: {e}")


@router.put("/schedule/nodes/{node_id}")
def update_schedule_node(
    node_id: int,
    req: ScheduleNodeUpsertRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ScheduleService(db)
        node = service.update_node(node_id, req.model_dump())
        return {"message": f"工期节点【{node.title or node.stage_name}】已更新", "id": node.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"更新节点失败: {e}")


@router.post("/schedule/nodes/{node_id}/shift")
def shift_schedule_node(
    node_id: int,
    req: ScheduleShiftRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ScheduleService(db)
        node = service.shift_node(node_id, req.delta_periods)
        direction = "后移" if req.delta_periods > 0 else "前移"
        return {"message": f"节点已{direction} {abs(req.delta_periods)} 旬", "id": node.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"平移节点失败: {e}")


@router.delete("/schedule/nodes/{node_id}")
def delete_schedule_node(
    node_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ScheduleService(db)
        ok = service.delete_node(node_id)
        if not ok:
            raise HTTPException(status_code=404, detail="节点不存在")
        return {"message": "工期节点已删除"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除节点失败: {e}")


@router.post("/schedule/lanes/delete")
def delete_schedule_lane(
    req: ScheduleLaneDeleteRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ScheduleService(db)
        count = service.delete_lane_nodes(req.lane_type, req.product_id, req.lane_title)
        return {"message": f"已删除泳道【{req.lane_title}】及其下属 {count} 个节点"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除泳道失败: {e}")
