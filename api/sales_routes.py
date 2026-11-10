"""
Online Sales Orders, Presale Lifecycle, Offline POS, Sales Analytics, and Platforms REST API Routes.
Reuses services.sales_order_service, services.offline_sales_service, services.sales_service, and state helpers.
"""
import io
import re
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
import pandas as pd

from api.deps import verify_auth_token, get_db_session, is_test_mode_header, load_rates_map, format_currency
from services.sales_order_service import SalesOrderService
from services.offline_sales_service import OfflineSalesService
from services.sales_service import SalesService
from services.inventory_service import InventoryService
from constants import OrderStatus, to_cny
from models import (
    Product,
    SalesPlatform,
    Warehouse,
    CompanyBalanceItem,
    SalesOrder,
    InventoryLog,
)
from cache_manager import sync_all_caches

router = APIRouter(tags=["Sales & Orders"])


# ==================== Helper Functions ====================

def _clean_order_no(val: Any) -> str:
    if not val:
        return ""
    s = str(val)
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _get_sales_form_metadata(db: Session) -> Dict[str, Any]:
    platforms = db.query(SalesPlatform).order_by(SalesPlatform.id.asc()).all()
    plat_list = [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "currency": p.currency or "CNY",
            "fee_rate": float(p.fee_rate or 0.0),
            "fee_fixed": float(p.fee_fixed or 0.0),
        }
        for p in platforms
    ] or [
        {"id": 1, "code": "weidian", "name": "微店", "currency": "CNY", "fee_rate": 0.006, "fee_fixed": 0.0},
        {"id": 2, "code": "booth", "name": "Booth", "currency": "JPY", "fee_rate": 0.056, "fee_fixed": 45.0},
    ]

    accounts = db.query(CompanyBalanceItem).filter(
        CompanyBalanceItem.category == "asset",
        CompanyBalanceItem.asset_type == "现金",
    ).all()
    acc_list = [
        {"id": a.id, "name": a.name, "currency": a.currency or "CNY", "amount": round(float(a.amount or 0.0), 2)}
        for a in accounts
    ]

    warehouses = db.query(Warehouse).order_by(Warehouse.id.asc()).all()
    wh_list = [{"id": w.id, "name": w.name} for w in warehouses]

    products = db.query(Product).order_by(Product.id.desc()).all()
    prod_list = []
    for p in products:
        colors = []
        for c in p.colors:
            prices = [
                {
                    "platform": pr.platform,
                    "currency": pr.currency,
                    "price": float(pr.price or 0.0),
                }
                for pr in (c.prices or [])
            ]
            parts = ["整套"] + [pt.part_name for pt in (c.parts or [])]
            colors.append({
                "color_name": c.color_name,
                "prices": prices,
                "parts": parts,
            })
        prod_list.append({
            "id": p.id,
            "name": p.name,
            "colors": colors,
        })

    return {
        "platforms": plat_list,
        "accounts": acc_list,
        "warehouses": wh_list,
        "products": prod_list,
    }


def _build_order_detail_and_refund_payload(db: Session, order: SalesOrder) -> Dict[str, Any]:
    wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}
    all_prods = db.query(Product).all()

    items_list = []
    ret_items = []
    res_items = []

    for i in order.items:
        wh_name = wh_dict.get(i.warehouse_id, "未分配")
        items_list.append({
            "id": i.id,
            "product_name": i.product_name,
            "variant": i.variant,
            "warehouse_id": i.warehouse_id or 0,
            "warehouse_name": wh_name,
            "quantity": i.quantity,
            "unit_price": round(float(i.unit_price or 0.0), 2),
            "subtotal": round(float(i.subtotal or 0.0), 2),
        })
        ret_items.append({
            "order_item_id": i.id,
            "product_name": i.product_name,
            "variant": i.variant,
            "max_quantity": i.quantity,
            "quantity": 0,
            "warehouse_id": i.warehouse_id or 0,
            "warehouse_name": wh_name,
        })
        p_obj = next((p for p in all_prods if p.name == i.product_name), None)
        color_obj = next((c for c in p_obj.colors if c.color_name == i.variant), None) if p_obj else None
        part_opts = ["整套"]
        if color_obj and color_obj.parts:
            for pt in color_obj.parts:
                part_opts.append(pt.part_name)
        res_items.append({
            "order_item_id": i.id,
            "product_name": i.product_name,
            "variant": i.variant,
            "quantity": 0,
            "warehouse_id": i.warehouse_id or 0,
            "warehouse_name": wh_name,
            "part_name": "整套",
            "part_options": part_opts,
        })

    refunds_list = []
    for r in order.refunds:
        refunds_list.append({
            "id": r.id,
            "refund_date": r.refund_date.strftime("%Y-%m-%d") if r.refund_date else "",
            "refund_reason": r.refund_reason or "",
            "refund_amount": round(float(r.refund_amount or 0.0), 2),
            "is_returned": bool(r.is_returned),
            "returned_quantity": int(r.returned_quantity or 0),
            "is_resend": bool(getattr(r, "is_resend", False)),
            "resend_quantity": int(getattr(r, "resend_quantity", 0) or 0),
        })

    can_close_unpaid = (
        order.order_type == "预售"
        and order.status in [OrderStatus.PRESALE_PENDING_FINAL, OrderStatus.PRESALE_PENDING_DEPOSIT]
        and not order.final_order_no
    )
    can_split = (
        order.order_type == "预售"
        and order.status == OrderStatus.PRESALE_PENDING_FINAL
        and not order.final_order_no
        and sum(it.quantity for it in order.items) > 1
    )
    split_next_no = ""
    split_items = []
    if order.order_type == "预售":
        existing_splits = db.query(SalesOrder.order_no).filter(
            SalesOrder.order_no.like(f"{order.order_no}-%")
        ).all()
        max_idx = 0
        pattern = re.compile(rf"^{re.escape(order.order_no)}-(\d+)$")
        for (ex_no,) in existing_splits:
            m = pattern.match(ex_no)
            if m:
                max_idx = max(max_idx, int(m.group(1)))
        split_next_no = f"{order.order_no}-{max_idx + 1}"
        for it in order.items:
            u_dep = it.subtotal / it.quantity if it.quantity > 0 else 0.0
            split_items.append({
                "item_id": it.id,
                "product_name": it.product_name,
                "variant": it.variant,
                "warehouse_name": wh_dict.get(it.warehouse_id, "未分配仓"),
                "max_qty": it.quantity,
                "split_qty": 0,
                "unit_deposit": round(float(u_dep), 2),
            })

    return {
        "id": order.id,
        "order_no": _clean_order_no(order.order_no),
        "final_order_no": _clean_order_no(order.final_order_no) or "-",
        "order_type": order.order_type,
        "status": order.status,
        "platform": order.platform,
        "currency": order.currency,
        "created_date": order.created_date.strftime("%Y-%m-%d") if order.created_date else "",
        "shipped_date": order.shipped_date.strftime("%Y-%m-%d") if order.shipped_date else "未发货",
        "completed_date": order.completed_date.strftime("%Y-%m-%d") if order.completed_date else "未完成",
        "target_account": order.target_account_name or "系统默认",
        "notes": order.notes or "",
        "discount_note": getattr(order, "discount_note", "") or "",
        "deposit_amount": round(float(order.deposit_amount or 0.0), 2),
        "final_amount": round(float(order.final_amount or 0.0), 2),
        "total_amount": round(float(order.total_amount or 0.0), 2),
        "items": items_list,
        "refunds": refunds_list,
        "refund_return_candidates": ret_items,
        "refund_resend_candidates": res_items,
        "can_close_unpaid": can_close_unpaid,
        "can_split": can_split,
        "split_next_order_no": split_next_no,
        "split_items": split_items,
    }


# ==================== Request Schemas ====================

class CartItemPayload(BaseModel):
    product_name: str
    variant: str
    warehouse_name: str
    quantity: int
    unit_price: float = 0.0
    subtotal: float = 0.0


class OnlineOrderCreateRequest(BaseModel):
    order_no: str
    platform: str
    currency: str = "CNY"
    target_account: str
    order_date: str
    total_override: float
    discount_note: str = ""
    notes: str = ""
    fee_enabled: bool = False
    fee_rate: float = 0.6
    peel_shipping: bool = True
    shipping_fee: float = 370.0
    cart_items: List[CartItemPayload]


class OrderNotesUpdateRequest(BaseModel):
    discount_note: str = ""
    notes: str = ""


class BatchShipRequest(BaseModel):
    order_ids: List[int]
    ship_date: Optional[str] = None


class BatchCompleteRequest(BaseModel):
    order_ids: List[int]
    complete_date: Optional[str] = None


class ReturnedItemPayload(BaseModel):
    product_name: str
    variant: str
    quantity: int
    warehouse_id: Optional[int] = None


class ResendItemPayload(BaseModel):
    product_name: str
    variant: str
    quantity: int
    warehouse_id: Optional[int] = None
    part_name: str = "整套"


class RefundAddRequest(BaseModel):
    refund_amount: float
    refund_reason: str
    is_returned: bool = False
    returned_items: List[ReturnedItemPayload] = []
    is_resend: bool = False
    resend_items: List[ResendItemPayload] = []


class RefundEditRequest(BaseModel):
    refund_amount: float
    refund_reason: str


class ImportConfirmRequest(BaseModel):
    orders: List[Dict[str, Any]]
    mode: str = "normal"  # "normal", "deposit", or "final"


class PresaleDepositCreateRequest(BaseModel):
    order_no: str
    platform: str
    currency: str = "CNY"
    target_account: str
    order_date: str
    deposit_override: float
    discount_note: str = ""
    notes: str = ""
    fee_enabled: bool = False
    fee_rate: float = 0.6
    cart_items: List[CartItemPayload]


class PresaleBindFinalRequest(BaseModel):
    deposit_order_ids: List[int]
    final_order_no: str
    final_amount: float
    notes: str = ""
    fee_enabled: bool = False
    fee_rate: float = 0.6
    peel_shipping: bool = True
    shipping_fee: float = 370.0


class SplitItemPayload(BaseModel):
    item_id: int
    split_quantity: int


class PresaleSplitRequest(BaseModel):
    items: List[SplitItemPayload]


class BatchWarehouseRequest(BaseModel):
    order_ids: List[int]
    warehouse_name: str


class PosCartItemPayload(BaseModel):
    product_name: str
    variant: str
    qty: int
    unit_price: float


class PosCheckoutRequest(BaseModel):
    template_id: int
    payment_method: str = "Cash"  # "Cash" or "PayPay"
    fee_rate: float = 0.0198
    account_id: int
    cart_items: List[PosCartItemPayload]


class PosTemplateItemInput(BaseModel):
    product_name: str
    variant: str
    preset_price: float
    quantity: int


class PosTemplateSaveRequest(BaseModel):
    template_id: Optional[int] = None
    name: str
    code: str
    currency: str = "JPY"
    warehouse_id: int
    platform: str = "线下展会"
    items: List[PosTemplateItemInput]


class PlatformCreateRequest(BaseModel):
    code: str
    name: str
    currency: str = "CNY"
    fee_rate_pct: float = 0.0
    fee_fixed: float = 0.0


# ==================== 1. Online Orders Endpoints ====================

@router.get("/orders")
def list_online_orders(
    status_filter: str = "全部",
    product_filter: str = "全部商品",
    search_query: str = "",
    page_number: int = 1,
    page_size: int = 50,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    ex_rate = rates_map.get("JPY", 0.048)

    service = SalesOrderService(db)
    all_orders = service.get_all_orders(order_type="线上", limit=5000)
    wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}

    count_pending_ship = sum(1 for o in all_orders if o.status == OrderStatus.PENDING)
    count_shipped = sum(1 for o in all_orders if o.status == OrderStatus.SHIPPED)
    count_completed = sum(1 for o in all_orders if o.status == OrderStatus.COMPLETED)
    count_after_sale = sum(1 for o in all_orders if o.status == OrderStatus.AFTER_SALES or len(o.refunds) > 0)

    filtered = all_orders
    if status_filter != "全部":
        if status_filter in ("有售后记录", "售后中"):
            filtered = [o for o in filtered if len(o.refunds) > 0 or o.status == OrderStatus.AFTER_SALES]
        else:
            filtered = [o for o in filtered if o.status == status_filter]

    if product_filter and product_filter != "全部商品":
        filtered = [o for o in filtered if any(i.product_name == product_filter for i in o.items)]

    kw = search_query.strip().lower()
    if kw:
        res = []
        for o in filtered:
            if (
                kw in (o.order_no or "").lower()
                or kw in (o.platform or "").lower()
                or kw in (o.notes or "").lower()
                or any(kw in (i.product_name or "").lower() or kw in (i.variant or "").lower() for i in o.items)
            ):
                res.append(o)
        filtered = res

    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page_num = max(1, min(page_number, total_pages))
    start_idx = (page_num - 1) * page_size
    paginated = filtered[start_idx: start_idx + page_size]

    rows = []
    for o in paginated:
        parts = []
        wh_names = set()
        for idx, i in enumerate(o.items):
            if i.warehouse_id and i.warehouse_id in wh_dict:
                wh_names.add(wh_dict[i.warehouse_id])
            if idx < 2:
                parts.append(f"{i.product_name}[{i.variant}] x{i.quantity}")
        items_str = " + ".join(parts)
        if len(o.items) > 2:
            items_str += f" 等({sum(i.quantity for i in o.items)}件)"

        ref_amt = sum(float(r.refund_amount or 0.0) for r in o.refunds)
        cny_eq = o.total_amount * ex_rate if o.currency == "JPY" else o.total_amount

        rows.append({
            "id": o.id,
            "order_no": _clean_order_no(o.order_no),
            "platform": o.platform,
            "status": o.status,
            "items_summary": items_str or "无明细",
            "warehouse_summary": ", ".join(wh_names) if wh_names else "未分配",
            "total_amount": round(float(o.total_amount or 0.0), 2),
            "currency": o.currency,
            "cny_equiv": round(float(cny_eq or 0.0), 2),
            "created_date": o.created_date.strftime("%Y-%m-%d") if o.created_date else "",
            "shipped_date": o.shipped_date.strftime("%Y-%m-%d") if o.shipped_date else "-",
            "completed_date": o.completed_date.strftime("%Y-%m-%d") if o.completed_date else "-",
            "target_account": o.target_account_name or "默认",
            "has_refunds": len(o.refunds) > 0,
            "refund_amount": round(ref_amt, 2),
            "notes": o.notes or "",
            "discount_note": getattr(o, "discount_note", "") or "",
        })

    return {
        "orders": rows,
        "total_items": total_items,
        "total_pages": total_pages,
        "page_number": page_num,
        "stats": {
            "all": len(all_orders),
            "pending_ship": count_pending_ship,
            "shipped": count_shipped,
            "completed": count_completed,
            "after_sale": count_after_sale,
        },
        "meta": _get_sales_form_metadata(db),
    }


@router.get("/orders/variant-info")
def get_variant_price_and_stock(
    product_name: str = Query(...),
    variant: str = Query(...),
    platform: str = Query("微店"),
    warehouse_name: str = Query(""),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    inv_svc = InventoryService(db)
    wh = db.query(Warehouse).filter(Warehouse.name == warehouse_name).first() if warehouse_name else None
    wh_id = wh.id if wh else None

    wh_details = inv_svc.get_warehouse_inventory_details()
    avail_stock = 0
    if wh_id and wh_id in wh_details:
        pt_dict = wh_details[wh_id].get("stock", {}).get(product_name, {}).get(variant, {})
        prod_obj = db.query(Product).filter(Product.name == product_name).first()
        color_obj = next((c for c in prod_obj.colors if c.color_name == variant), None) if prod_obj else None
        reqs = {p.part_name: p.quantity for p in color_obj.parts} if (color_obj and color_obj.parts) else {"整套": 1}
        if reqs:
            avail_stock = max(0, min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items()))

    prod = db.query(Product).filter(Product.name == product_name).first()
    unit_price = 0.0
    if prod:
        color_obj = next((c for c in prod.colors if c.color_name == variant), None)
        if color_obj and color_obj.prices:
            plat_obj = db.query(SalesPlatform).filter(
                (SalesPlatform.name == platform) | (SalesPlatform.code == platform.lower())
            ).first()
            p_code = plat_obj.code if plat_obj else platform.lower()
            p_match = next(
                (pr for pr in color_obj.prices if pr.platform in (platform, p_code)),
                None,
            )
            if not p_match:
                p_match = color_obj.prices[0]
            unit_price = float(p_match.price or 0.0)

    return {
        "available_stock": avail_stock,
        "unit_price": round(unit_price, 2),
    }


@router.get("/orders/{order_id}")
def get_order_detail(
    order_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    service = SalesOrderService(db)
    o = service.get_order_by_id(order_id)
    if not o:
        raise HTTPException(status_code=404, detail="单据不存在")
    return _build_order_detail_and_refund_payload(db, o)


@router.post("/orders")
def create_online_order(
    req: OnlineOrderCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.order_no.strip():
        raise HTTPException(status_code=400, detail="请填写订单号")
    if not req.cart_items:
        raise HTTPException(status_code=400, detail="请至少添加一件商品明细")

    wh_dict = {w.name: w.id for w in db.query(Warehouse).all()}
    total_qty = sum(it.quantity for it in req.cart_items)

    actual_total = req.total_override
    fee_note = ""
    if "booth" in req.platform.lower() and req.peel_shipping and req.shipping_fee > 0:
        actual_total = max(0.0, actual_total - req.shipping_fee)
        fee_note += f"[剥离运费 {req.shipping_fee}]"
    if req.fee_enabled and req.fee_rate > 0:
        deducted = round(actual_total * (req.fee_rate / 100.0), 2)
        actual_total = round(actual_total - deducted, 2)
        fee_note += f"[扣手续费 {req.fee_rate}% (-{deducted})]"

    final_notes = req.notes.strip()
    if fee_note:
        final_notes = f"{final_notes} {fee_note}".strip()

    unit_avg = actual_total / total_qty if total_qty > 0 else 0.0
    items_payload = []
    for it in req.cart_items:
        items_payload.append({
            "product_name": it.product_name,
            "variant": it.variant,
            "quantity": it.quantity,
            "unit_price": unit_avg,
            "warehouse_id": wh_dict.get(it.warehouse_name),
        })

    try:
        dt = datetime.strptime(req.order_date, "%Y-%m-%d").date()
    except Exception:
        dt = date.today()

    try:
        service = SalesOrderService(db)
        order, err = service.create_order(
            items_data=items_payload,
            platform=req.platform.strip(),
            currency=req.currency,
            notes=final_notes,
            order_date=dt,
            order_no=req.order_no.strip(),
            target_account_name=req.target_account.strip() or None,
        )
        if err:
            raise HTTPException(status_code=400, detail=err)
        if req.discount_note.strip():
            service.update_order_info(order.id, {"discount_note": req.discount_note.strip()})
        sync_all_caches()
        return {"message": f"通贩订单 {req.order_no.strip()} 创建成功"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"创建订单失败: {e}")


@router.put("/orders/{order_id}/notes")
def update_order_notes(
    order_id: int,
    req: OrderNotesUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = SalesOrderService(db)
        service.update_order_info(order_id, {
            "discount_note": req.discount_note.strip(),
            "notes": req.notes.strip(),
        })
        sync_all_caches()
        return {"message": "订单优惠及备注修改成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"保存修改失败: {e}")


@router.delete("/orders/{order_id}")
def delete_order(
    order_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = SalesOrderService(db)
        msg = service.delete_order(order_id)
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除订单失败: {e}")


@router.post("/orders/batch-ship")
def batch_ship_orders(
    req: BatchShipRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.order_ids:
        raise HTTPException(status_code=400, detail="请先勾选需要发货的订单")

    try:
        ship_dt = datetime.strptime(req.ship_date, "%Y-%m-%d").date() if req.ship_date else date.today()
    except Exception:
        ship_dt = date.today()

    service = SalesOrderService(db)
    success, errors = service.batch_ship_orders(req.order_ids, ship_date=ship_dt)
    if success == 0 and errors:
        raise HTTPException(status_code=400, detail=errors[0])
    sync_all_caches()
    return {
        "message": f"📦 确认发货出库完成：成功 {success} 单" + (f"，失败 {len(errors)} 单 ({errors[0]})" if errors else ""),
        "success": success,
        "errors": errors,
    }


@router.post("/orders/batch-complete")
def batch_complete_orders(
    req: BatchCompleteRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.order_ids:
        raise HTTPException(status_code=400, detail="请先勾选需要结清完成的订单")

    try:
        comp_dt = datetime.strptime(req.complete_date, "%Y-%m-%d").date() if req.complete_date else date.today()
    except Exception:
        comp_dt = date.today()

    service = SalesOrderService(db)
    success, errors = service.batch_complete_orders(req.order_ids, complete_date=comp_dt)
    if success == 0 and errors:
        raise HTTPException(status_code=400, detail=errors[0])
    sync_all_caches()
    return {
        "message": f"✅ 确认收货完成入账：成功 {success} 单" + (f"，失败 {len(errors)} 单 ({errors[0]})" if errors else ""),
        "success": success,
        "errors": errors,
    }


# ==================== Refunds Endpoints ====================

@router.post("/orders/{order_id}/refunds")
def add_order_refund(
    order_id: int,
    req: RefundAddRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if req.refund_amount < 0:
        raise HTTPException(status_code=400, detail="售后金额不能为负数")
    if not req.refund_reason.strip():
        raise HTTPException(status_code=400, detail="请输入售后原因以作记录审计")

    rates_map = load_rates_map(db)
    ex_rate = rates_map.get("JPY", 0.048)

    returned_list = []
    if req.is_returned:
        for item in req.returned_items:
            if item.quantity > 0:
                returned_list.append({
                    "product_name": item.product_name,
                    "variant": item.variant,
                    "quantity": item.quantity,
                    "warehouse_id": item.warehouse_id if (item.warehouse_id and item.warehouse_id > 0) else None,
                })

    resend_list = []
    if req.is_resend:
        for item in req.resend_items:
            if item.quantity > 0:
                resend_list.append({
                    "product_name": item.product_name,
                    "variant": item.variant,
                    "quantity": item.quantity,
                    "warehouse_id": item.warehouse_id if (item.warehouse_id and item.warehouse_id > 0) else None,
                    "part_name": None if item.part_name == "整套" else item.part_name,
                })

    try:
        service = SalesOrderService(db)
        returned_qty = sum(x["quantity"] for x in returned_list) if req.is_returned else 0
        resend_qty = sum(x["quantity"] for x in resend_list) if req.is_resend else 0
        msg = service.add_refund(
            order_id=order_id,
            refund_amount=req.refund_amount,
            refund_reason=req.refund_reason.strip(),
            is_returned=req.is_returned,
            returned_quantity=returned_qty,
            returned_items=returned_list if req.is_returned else None,
            exchange_rate=ex_rate,
            is_resend=req.is_resend,
            resend_quantity=resend_qty,
            resend_items=resend_list if req.is_resend else None,
        )
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"申请售后失败: {e}")


@router.put("/orders/refunds/{refund_id}")
def edit_order_refund(
    refund_id: int,
    req: RefundEditRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    ex_rate = rates_map.get("JPY", 0.048)
    try:
        service = SalesOrderService(db)
        msg = service.update_refund(
            refund_id=refund_id,
            refund_amount=req.refund_amount,
            refund_reason=req.refund_reason.strip(),
            exchange_rate=ex_rate,
        )
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"修改售后失败: {e}")


@router.delete("/orders/refunds/{refund_id}")
def delete_order_refund(
    refund_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = SalesOrderService(db)
        msg = service.delete_refund(refund_id)
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"回滚售后失败: {e}")


# ==================== Excel Import Endpoints ====================

@router.post("/orders/import/preview")
async def preview_excel_import(
    file: UploadFile = File(...),
    mode: str = Form("normal"),  # "normal", "deposit", or "final"
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    raw_bytes = await file.read()
    rates_map = load_rates_map(db)
    ex_rate = rates_map.get("JPY", 0.048)

    try:
        df = pd.read_excel(io.BytesIO(raw_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel 文件读取失败: {e}")

    presale_mode = None
    if mode == "deposit":
        presale_mode = "定金"
    elif mode == "final":
        presale_mode = "尾款"

    service = SalesOrderService(db)
    parsed_orders, errors = service.validate_and_parse_import_data(
        df, exchange_rate=ex_rate, presale_mode=presale_mode
    )
    if parsed_orders is None:
        err_list = errors if isinstance(errors, list) else [str(errors)]
        return {
            "orders": [],
            "errors": err_list,
            "summary": f"校验未通过：{'; '.join(err_list)}",
        }
    return {
        "orders": parsed_orders,
        "errors": errors or [],
        "summary": f"解析完成：共识别 {len(parsed_orders)} 笔可导入单据" + (f"，发现 {len(errors)} 条错误" if errors else ""),
    }


@router.post("/orders/import/confirm")
def confirm_excel_import(
    req: ImportConfirmRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.orders:
        raise HTTPException(status_code=400, detail="没有可导入的订单数据")

    presale_mode = None
    if req.mode == "deposit":
        presale_mode = "定金"
    elif req.mode == "final":
        presale_mode = "尾款"

    try:
        service = SalesOrderService(db)
        created_count = service.batch_create_orders(req.orders, presale_mode=presale_mode)
        sync_all_caches()
        return {
            "message": f"批量导入成功：共入库 {created_count} 笔单据！",
            "success_count": created_count,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"批量导入失败: {e}")


# ==================== 2. Presale Orders Endpoints ====================

@router.get("/presale")
def list_presale_orders(
    status_filter: str = "全部",
    product_filter: str = "全部商品",
    search_query: str = "",
    page_number: int = 1,
    page_size: int = 50,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    ex_rate = rates_map.get("JPY", 0.048)

    service = SalesOrderService(db)
    all_orders = service.get_all_orders(order_type="预售", limit=5000)
    wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}

    count_pending_dep = sum(1 for o in all_orders if o.status == OrderStatus.PRESALE_PENDING_DEPOSIT)
    count_pending_fin = sum(1 for o in all_orders if o.status == OrderStatus.PRESALE_PENDING_FINAL)
    count_pending_ship = sum(1 for o in all_orders if o.status == OrderStatus.PENDING)
    count_shipped = sum(1 for o in all_orders if o.status == OrderStatus.SHIPPED)
    count_completed = sum(1 for o in all_orders if o.status == OrderStatus.COMPLETED)
    count_after_sale = sum(1 for o in all_orders if o.status == OrderStatus.AFTER_SALES or len(o.refunds) > 0)

    filtered = all_orders
    if status_filter != "全部":
        if status_filter in ("有售后记录", "售后中"):
            filtered = [o for o in filtered if len(o.refunds) > 0 or o.status == OrderStatus.AFTER_SALES]
        else:
            filtered = [o for o in filtered if o.status == status_filter]

    if product_filter and product_filter != "全部商品":
        filtered = [o for o in filtered if any(i.product_name == product_filter for i in o.items)]

    kw = search_query.strip().lower()
    if kw:
        res = []
        for o in filtered:
            if (
                kw in (o.order_no or "").lower()
                or kw in (o.final_order_no or "").lower()
                or kw in (o.platform or "").lower()
                or kw in (o.notes or "").lower()
                or any(kw in (i.product_name or "").lower() or kw in (i.variant or "").lower() for i in o.items)
            ):
                res.append(o)
        filtered = res

    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page_num = max(1, min(page_number, total_pages))
    start_idx = (page_num - 1) * page_size
    paginated = filtered[start_idx: start_idx + page_size]

    rows = []
    for o in paginated:
        parts = []
        wh_names = set()
        for idx, i in enumerate(o.items):
            if i.warehouse_id and i.warehouse_id in wh_dict:
                wh_names.add(wh_dict[i.warehouse_id])
            if idx < 2:
                parts.append(f"{i.product_name}[{i.variant}] x{i.quantity}")
        items_str = " + ".join(parts)
        if len(o.items) > 2:
            items_str += f" 等({sum(i.quantity for i in o.items)}件)"

        ref_amt = sum(float(r.refund_amount or 0.0) for r in o.refunds)
        cny_eq = o.total_amount * ex_rate if o.currency == "JPY" else o.total_amount

        rows.append({
            "id": o.id,
            "order_no": _clean_order_no(o.order_no),
            "final_order_no": _clean_order_no(o.final_order_no) or "-",
            "platform": o.platform,
            "status": o.status,
            "items_summary": items_str or "无明细",
            "warehouse_summary": ", ".join(wh_names) if wh_names else "未分配",
            "deposit_amount": round(float(o.deposit_amount or 0.0), 2),
            "final_amount": round(float(o.final_amount or 0.0), 2),
            "total_amount": round(float(o.total_amount or 0.0), 2),
            "currency": o.currency,
            "cny_equiv": round(float(cny_eq or 0.0), 2),
            "created_date": o.created_date.strftime("%Y-%m-%d") if o.created_date else "",
            "shipped_date": o.shipped_date.strftime("%Y-%m-%d") if o.shipped_date else "-",
            "completed_date": o.completed_date.strftime("%Y-%m-%d") if o.completed_date else "-",
            "target_account": o.target_account_name or "默认",
            "has_refunds": len(o.refunds) > 0,
            "refund_amount": round(ref_amt, 2),
            "notes": o.notes or "",
            "discount_note": getattr(o, "discount_note", "") or "",
        })

    return {
        "orders": rows,
        "total_items": total_items,
        "total_pages": total_pages,
        "page_number": page_num,
        "stats": {
            "all": len(all_orders),
            "pending_deposit": count_pending_dep,
            "pending_final": count_pending_fin,
            "pending_ship": count_pending_ship,
            "shipped": count_shipped,
            "completed": count_completed,
            "after_sale": count_after_sale,
        },
        "meta": _get_sales_form_metadata(db),
    }


@router.post("/presale/deposit")
def create_presale_deposit(
    req: PresaleDepositCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.order_no.strip():
        raise HTTPException(status_code=400, detail="请填写定金单号")
    if not req.cart_items:
        raise HTTPException(status_code=400, detail="请至少添加一件商品明细")

    wh_dict = {w.name: w.id for w in db.query(Warehouse).all()}
    total_qty = sum(it.quantity for it in req.cart_items)

    actual_dep = req.deposit_override
    fee_note = ""
    if req.fee_enabled and req.fee_rate > 0:
        deducted = round(actual_dep * (req.fee_rate / 100.0), 2)
        actual_dep = round(actual_dep - deducted, 2)
        fee_note = f"[定金扣手续费 {req.fee_rate}% (-{deducted})]"

    final_notes = f"{req.notes.strip()} {fee_note}".strip()
    unit_avg = actual_dep / total_qty if total_qty > 0 else 0.0

    items_payload = []
    for it in req.cart_items:
        items_payload.append({
            "product_name": it.product_name,
            "variant": it.variant,
            "quantity": it.quantity,
            "unit_price": unit_avg,
            "warehouse_id": wh_dict.get(it.warehouse_name),
        })

    try:
        dt = datetime.strptime(req.order_date, "%Y-%m-%d").date()
    except Exception:
        dt = date.today()

    try:
        service = SalesOrderService(db)
        order, err = service.create_presale_deposit_order(
            items_data=items_payload,
            platform=req.platform.strip(),
            currency=req.currency,
            notes=final_notes,
            order_date=dt,
            order_no=req.order_no.strip(),
            target_account_name=req.target_account.strip() or None,
            discount_note=req.discount_note.strip(),
        )
        if err:
            raise HTTPException(status_code=400, detail=err)
        sync_all_caches()
        return {"message": f"预售定金单 {req.order_no.strip()} 录入成功"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"创建预售定金单失败: {e}")


@router.post("/presale/batch-complete-deposit")
def batch_complete_presale_deposit(
    req: BatchCompleteRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.order_ids:
        raise HTTPException(status_code=400, detail="请先勾选待完成定金的订单")

    try:
        comp_dt = datetime.strptime(req.complete_date, "%Y-%m-%d").date() if req.complete_date else date.today()
    except Exception:
        comp_dt = date.today()

    service = SalesOrderService(db)
    success, errors = service.batch_complete_deposit_orders(req.order_ids, complete_date=comp_dt)
    if success == 0 and errors:
        raise HTTPException(status_code=400, detail=errors[0])
    sync_all_caches()
    return {
        "message": f"📥 定金收款入账完成：成功 {success} 单已转为【待付尾款】" + (f"，失败 {len(errors)} 单 ({errors[0]})" if errors else ""),
        "success": success,
        "errors": errors,
    }


@router.post("/presale/batch-close-unpaid")
def batch_close_unpaid_presale(
    req: BatchCompleteRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.order_ids:
        raise HTTPException(status_code=400, detail="请先勾选需要超时未补款结单的预售订单")

    try:
        comp_dt = datetime.strptime(req.complete_date, "%Y-%m-%d").date() if req.complete_date else date.today()
    except Exception:
        comp_dt = date.today()

    service = SalesOrderService(db)
    success, errors = service.close_unpaid_presale_orders(req.order_ids, complete_date=comp_dt)
    if success == 0 and errors:
        raise HTTPException(status_code=400, detail=errors[0])
    sync_all_caches()
    return {
        "message": f"超时未补款结单：成功直接完成 {success} 单" + (f"，失败 {len(errors)} 单 ({errors[0]})" if errors else ""),
        "success": success,
        "errors": errors,
    }


@router.get("/presale/search-deposit")
def search_presale_deposit(
    query: str = Query(""),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    kw = query.strip().lower()
    orders = db.query(SalesOrder).filter(
        SalesOrder.order_type == "预售",
        SalesOrder.status == OrderStatus.PRESALE_PENDING_FINAL,
    ).order_by(SalesOrder.id.desc()).all()
    results = []
    for o in orders:
        if kw and kw not in (o.order_no or "").lower():
            continue
        items_str = " + ".join(f"{i.product_name}[{i.variant}]x{i.quantity}" for i in o.items)
        results.append({
            "id": o.id,
            "order_no": _clean_order_no(o.order_no),
            "platform": o.platform,
            "currency": o.currency,
            "deposit_amount": round(float(o.deposit_amount or 0.0), 2),
            "items_summary": items_str,
            "target_account": o.target_account_name or "",
        })
    return {"candidates": results[:30]}


@router.get("/presale/check-existing-final")
def check_existing_final_order(
    final_order_no: str = Query(...),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    fno = final_order_no.strip()
    if not fno:
        return {"exists": False}
    existing = db.query(SalesOrder).filter(
        SalesOrder.order_type == "预售",
        SalesOrder.final_order_no == fno,
    ).all()
    if not existing:
        return {"exists": False}
    return {
        "exists": True,
        "bound_deposit_nos": [_clean_order_no(o.order_no) for o in existing],
        "existing_final_amount": round(sum(float(o.final_amount or 0.0) for o in existing), 2),
    }


@router.post("/presale/bind-final")
def bind_presale_final(
    req: PresaleBindFinalRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.deposit_order_ids:
        raise HTTPException(status_code=400, detail="请先选择要绑定的定金单")
    if not req.final_order_no.strip():
        raise HTTPException(status_code=400, detail="请填写尾款订单号")

    actual_final = req.final_amount
    if req.peel_shipping and req.shipping_fee > 0:
        actual_final = max(0.0, actual_final - req.shipping_fee)
    if req.fee_enabled and req.fee_rate > 0:
        deducted = round(actual_final * (req.fee_rate / 100.0), 2)
        actual_final = round(actual_final - deducted, 2)

    try:
        service = SalesOrderService(db)
        msg = service.bind_presale_final_order(
            deposit_order_ids=req.deposit_order_ids,
            final_order_no=req.final_order_no.strip(),
            final_net_amount=actual_final,
            new_notes=req.notes.strip(),
        )
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"尾款绑定失败: {e}")


@router.post("/presale/{order_id}/unbind-final")
def unbind_presale_final(
    order_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = SalesOrderService(db)
        msg = service.unbind_presale_final(order_id)
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"解绑尾款失败: {e}")


@router.post("/presale/{order_id}/split")
def split_presale_deposit_order(
    order_id: int,
    req: PresaleSplitRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    split_payload = [
        {"item_id": it.item_id, "split_quantity": it.split_quantity}
        for it in req.items
        if it.split_quantity > 0
    ]
    if not split_payload:
        raise HTTPException(status_code=400, detail="请至少选择 1 件需要拆出的商品")
    try:
        service = SalesOrderService(db)
        _, msg = service.split_presale_deposit_order(order_id, split_payload)
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"拆分定金单失败: {e}")


@router.post("/presale/batch-warehouse")
def batch_update_presale_warehouse(
    req: BatchWarehouseRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.order_ids:
        raise HTTPException(status_code=400, detail="未勾选任何订单")
    wh = db.query(Warehouse).filter(Warehouse.name == req.warehouse_name).first()
    if not wh:
        raise HTTPException(status_code=404, detail=f"找不到仓库 '{req.warehouse_name}'")

    try:
        service = SalesOrderService(db)
        count, wh_name = service.batch_update_warehouse(req.order_ids, wh.id)
        sync_all_caches()
        return {"message": f"成功将 {count} 个订单的发货仓库批量修改为【{wh_name}】"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"批量修改仓库失败: {e}")


# ==================== 3. Offline POS Endpoints ====================

@router.get("/pos/init")
def get_offline_pos_init(
    template_code: Optional[str] = Query(None),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    service = OfflineSalesService(db)
    templates = service.get_all_templates()
    wh_dict = {w.id: w.name for w in db.query(Warehouse).all()}

    # Color image map for fast product card display
    prods = db.query(Product).all()
    prod_map = {p.name: p for p in prods}
    color_id_map: Dict[tuple, int] = {}
    for p in prods:
        for c in p.colors:
            color_id_map[(p.name, c.color_name)] = c.id

    # Precompute warehouse inventory details ONCE to avoid N*M redundant DB queries
    from services.inventory_service import InventoryService
    wh_details = InventoryService(db).get_warehouse_inventory_details()

    def calc_available_sets(wh_id: int, product_name: str, variant_name: str) -> int:
        stock_in_wh = wh_details.get(wh_id, {}).get("stock", {})
        pt_dict = stock_in_wh.get(product_name, {}).get(variant_name, {})
        prod = prod_map.get(product_name)
        if not prod:
            return 0
        target_c = next((c for c in prod.colors if c.color_name == variant_name), None)
        if not target_c:
            return 0
        reqs = {p.part_name: p.quantity for p in target_c.parts} if target_c.parts else {"整套": 1}
        if reqs:
            return max(0, min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items()))
        return 0

    tpl_list = []
    for t in templates:
        t_items = []
        for it in t.items:
            cid = color_id_map.get((it.product_name, it.variant), 0)
            wh_stock = calc_available_sets(t.warehouse_id, it.product_name, it.variant)
            t_items.append({
                "id": it.id,
                "product_name": it.product_name,
                "variant": it.variant,
                "preset_price": round(float(it.preset_price or 0.0), 2),
                "quantity": int(it.quantity or 0),
                "remaining_quantity": int(it.remaining_quantity or 0),
                "warehouse_stock": wh_stock,
                "color_id": cid,
                "image_url": f"/color-image/{cid}" if cid else "",
            })
        tpl_list.append({
            "id": t.id,
            "name": t.name,
            "code": t.code,
            "currency": t.currency or "JPY",
            "warehouse_id": t.warehouse_id or 0,
            "warehouse_name": wh_dict.get(t.warehouse_id, "未指定仓库") if t.warehouse_id else "未指定仓库",
            "platform": t.platform or "线下展会",
            "items": t_items,
        })

    if template_code and template_code != "ALL":
        orders = service.get_orders_by_template(template_code)
    else:
        # Load all offline sales orders across events
        orders = db.query(SalesOrder).options(joinedload(SalesOrder.items)).filter(
            SalesOrder.order_type == "线下"
        ).order_by(SalesOrder.id.desc()).limit(200).all()
        if not orders and tpl_list:
            orders = service.get_orders_by_template(tpl_list[0]["code"])
    ord_list = []
    for o in orders:
        parts = [f"{i.product_name}[{i.variant}] x{i.quantity}" for i in o.items]
        ord_list.append({
            "id": o.id,
            "order_no": o.order_no,
            "event_tag": o.platform,
            "total_amount": round(float(o.total_amount or 0.0), 2),
            "currency": o.currency,
            "target_account": o.target_account_name or "",
            "created_date": o.created_date.strftime("%Y-%m-%d") if o.created_date else "",
            "items_summary": " + ".join(parts),
            "notes": o.notes or "",
        })

    return {
        "templates": tpl_list,
        "orders": ord_list,
        "meta": _get_sales_form_metadata(db),
    }


@router.get("/pos/assignable-stocks")
def get_pos_assignable_stocks(
    warehouse_id: int = Query(...),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    service = OfflineSalesService(db)
    prods = db.query(Product).order_by(Product.id.desc()).all()
    items = []
    for p in prods:
        for c in p.colors:
            avail = service._get_available_sets(warehouse_id, p.name, c.color_name)
            items.append({
                "product_name": p.name,
                "variant": c.color_name,
                "available_sets": avail,
            })
    return {"items": items}


@router.post("/pos/checkout")
def checkout_pos_order(
    req: PosCheckoutRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.cart_items:
        raise HTTPException(status_code=400, detail="购物车为空，请先选择商品")

    cart_data = [
        {
            "product_name": it.product_name,
            "variant": it.variant,
            "qty": it.qty,
            "unit_price": it.unit_price,
        }
        for it in req.cart_items
        if it.qty > 0
    ]

    try:
        service = OfflineSalesService(db)
        order_no, net_amount = service.checkout_offline_order(
            template_id=req.template_id,
            cart_items=cart_data,
            payment_method=req.payment_method,
            fee_rate=req.fee_rate,
            account_id=req.account_id,
        )
        sync_all_caches()
        return {
            "message": f"结账成功！单号: {order_no}，净入账: {net_amount:,.2f}",
            "order_no": order_no,
            "net_amount": round(net_amount, 2),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"POS 结账失败: {e}")


@router.delete("/pos/orders/{order_no}")
def revoke_pos_order(
    order_no: str,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = OfflineSalesService(db)
        msg = service.delete_offline_order(order_no)
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"撤销 POS 订单失败: {e}")


@router.post("/pos/templates")
def save_pos_template(
    req: PosTemplateSaveRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.name.strip() or not req.code.strip():
        raise HTTPException(status_code=400, detail="模板名称与展会代号均不能为空")
    items_data = [
        {
            "product_name": it.product_name,
            "variant": it.variant,
            "preset_price": it.preset_price,
            "quantity": it.quantity,
        }
        for it in req.items
        if it.quantity > 0
    ]
    if not items_data:
        raise HTTPException(status_code=400, detail="请至少分配一件参展商品")

    try:
        service = OfflineSalesService(db)
        if req.template_id:
            service.update_template(
                template_id=req.template_id,
                name=req.name.strip(),
                code=req.code.strip().upper(),
                currency=req.currency,
                warehouse_id=req.warehouse_id,
                platform=req.platform.strip() or "线下展会",
                items_data=items_data,
            )
        else:
            service.create_template(
                name=req.name.strip(),
                code=req.code.strip().upper(),
                currency=req.currency,
                warehouse_id=req.warehouse_id,
                platform=req.platform.strip() or "线下展会",
                items_data=items_data,
            )
        return {"message": f"展会模板【{req.name.strip()}】已保存"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"保存模板失败: {e}")


@router.delete("/pos/templates/{template_id}")
def delete_pos_template(
    template_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = OfflineSalesService(db)
        service.delete_template(template_id)
        return {"message": "展会模板已删除"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除模板失败: {e}")


# ==================== 4. Sales Analytics Overview Endpoints ====================

def _compile_engine_analytics(
    df: pd.DataFrame,
    rates_map: Dict[str, float],
    selected_product: str,
    page_number: int,
    page_size: int,
    is_v2: bool,
) -> Dict[str, Any]:
    if df is None or df.empty:
        return {
            "total_sets": 0,
            "total_cny": 0.0,
            "currency_breakdown": [],
            "leaderboard": [],
            "product_options": [],
            "selected_product": "",
            "prod_total_sets": 0,
            "prod_total_cny": 0.0,
            "prod_currency_breakdown": [],
            "pivot_headers": [],
            "pivot_rows": [],
            "chart_data": [],
            "chart_platforms": [],
            "logs": [],
            "total_items": 0,
            "total_pages": 1,
            "page_number": 1,
        }

    # Map df columns: supports standard names ('product', 'variant', 'platform', 'currency', 'qty', 'amount', 'date')
    col_prod = "product" if "product" in df.columns else ("制品名称" if "制品名称" in df.columns else df.columns[0])
    col_qty = "qty" if "qty" in df.columns else ("销量" if "销量" in df.columns else "quantity")
    col_curr = "currency" if "currency" in df.columns else "货币"
    col_amt = "amount" if "amount" in df.columns else ("原币销售额" if "原币销售额" in df.columns else "price")
    col_var = "variant" if "variant" in df.columns else ("规格" if "规格" in df.columns else "color")
    col_plat = "platform" if "platform" in df.columns else ("销售平台" if "销售平台" in df.columns else "channel")
    col_date = "date" if "date" in df.columns else "日期"

    total_sets = int(df[col_qty].sum()) if col_qty in df.columns else 0
    curr_totals: Dict[str, float] = {}
    if col_curr in df.columns and col_amt in df.columns:
        for curr, grp in df.groupby(col_curr):
            val = float(grp[col_amt].sum())
            if abs(val) > 0.001:
                curr_totals[str(curr)] = val

    total_cny = sum(to_cny(amt, c, rates_map) for c, amt in curr_totals.items())
    bd_list = [
        {"currency": c, "amount_str": format_currency(amt, c)}
        for c, amt in curr_totals.items()
        if abs(amt) > 0.001
    ]

    lb_df = SalesService.get_product_leaderboard(df, rates_map)
    lb_rows = []
    prod_opts = []
    if lb_df is not None and not lb_df.empty:
        cny_equiv_col = lb_df.columns[1]  # '折合CNY总额'
        for idx, row in lb_df.iterrows():
            p_name = str(row["product"])
            prod_opts.append(p_name)
            p_df = df[df[col_prod] == p_name]
            c_strs = []
            if col_curr in p_df.columns and col_amt in p_df.columns:
                for c, grp in p_df.groupby(col_curr):
                    s_val = float(grp[col_amt].sum())
                    if abs(s_val) > 0.001:
                        c_strs.append(format_currency(s_val, str(c)))
            p_qty = int(p_df[col_qty].sum()) if col_qty in p_df.columns else 0
            cny_sum = float(row.get("CNY总额", row.get("CNY销额", 0.0)))
            lb_rows.append({
                "rank": len(lb_rows) + 1,
                "product_name": p_name,
                "total_sets": p_qty,
                "cny_sales": round(cny_sum, 2),
                "jpy_sales_str": " / ".join(c_strs) if c_strs else "-",
                "total_cny_equiv": round(float(row[cny_equiv_col]), 2),
            })

    sel_prod = selected_product if (selected_product and selected_product in prod_opts) else (prod_opts[0] if prod_opts else "")
    df_p = df[df[col_prod] == sel_prod] if sel_prod else pd.DataFrame()

    prod_sets = int(df_p[col_qty].sum()) if (not df_p.empty and col_qty in df_p.columns) else 0
    prod_curr: Dict[str, float] = {}
    if not df_p.empty and col_curr in df_p.columns and col_amt in df_p.columns:
        for c, grp in df_p.groupby(col_curr):
            v = float(grp[col_amt].sum())
            if abs(v) > 0.001:
                prod_curr[str(c)] = v

    prod_cny = sum(to_cny(amt, c, rates_map) for c, amt in prod_curr.items())
    prod_bd = [
        {"currency": c, "amount_str": format_currency(amt, c)}
        for c, amt in prod_curr.items()
        if abs(amt) > 0.001
    ]

    pivot_headers = []
    pivot_rows = []
    chart_data = []
    chart_platforms = []

    if not df_p.empty and col_var in df_p.columns and col_plat in df_p.columns and col_qty in df_p.columns:
        pivot = pd.pivot_table(
            df_p,
            values=col_qty,
            index=col_var,
            columns=col_plat,
            aggfunc="sum",
            fill_value=0,
            margins=True,
            margins_name="总计",
        )
        cols = [str(c) for c in pivot.columns if str(c) != "总计"]
        chart_platforms = cols
        pivot_headers = cols + ["总计"]

        for idx_val, row in pivot.iterrows():
            var_name = str(idx_val)
            cells = [int(row[c]) for c in pivot_headers if c in row]
            pivot_rows.append({"variant": var_name, "cells": cells})
            if var_name != "总计":
                c_item: Dict[str, Any] = {"variant": var_name}
                for c in cols:
                    c_item[c] = int(row[c])
                chart_data.append(c_item)

    df_sorted = df_p.sort_values(by=col_date, ascending=False) if (not df_p.empty and col_date in df_p.columns) else df_p
    tot_items = len(df_sorted)
    tot_pages = max(1, (tot_items + page_size - 1) // page_size)
    pg = max(1, min(page_number, tot_pages))
    start = (pg - 1) * page_size
    df_page = df_sorted.iloc[start: start + page_size] if not df_sorted.empty else pd.DataFrame()

    logs = []
    for _, r in df_page.iterrows():
        logs.append({
            "date": str(r.get(col_date, "")),
            "order_no": str(r.get("order_no", r.get("订单号", "-"))) if is_v2 else "-",
            "product_name": str(r.get(col_prod, "")),
            "variant": str(r.get(col_var, "")),
            "quantity": int(r.get(col_qty, 0)),
            "platform": str(r.get(col_plat, "")),
            "currency": str(r.get(col_curr, "")),
            "orig_sales": round(float(r.get(col_amt, 0.0)), 2),
            "note": str(r.get("note", r.get("备注", ""))),
        })

    return {
        "total_sets": total_sets,
        "total_cny": round(total_cny, 2),
        "currency_breakdown": bd_list,
        "leaderboard": lb_rows,
        "product_options": prod_opts,
        "selected_product": sel_prod,
        "prod_total_sets": prod_sets,
        "prod_total_cny": round(prod_cny, 2),
        "prod_currency_breakdown": prod_bd,
        "pivot_headers": pivot_headers,
        "pivot_rows": pivot_rows,
        "chart_data": chart_data,
        "chart_platforms": chart_platforms,
        "logs": logs,
        "total_items": tot_items,
        "total_pages": tot_pages,
        "page_number": pg,
    }


@router.get("/sales/overview")
def get_sales_overview(
    selected_product: str = "",
    v2_selected_product: str = "",
    page_number: int = 1,
    page_size: int = 20,
    v2_page_number: int = 1,
    v2_page_size: int = 20,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)

    df_v2 = SalesService.process_sales_data_v2(db)
    v2_data = _compile_engine_analytics(
        df=df_v2,
        rates_map=rates_map,
        selected_product=v2_selected_product,
        page_number=v2_page_number,
        page_size=v2_page_size,
        is_v2=True,
    )

    raw_v1 = SalesService.get_raw_sales_logs_v1(db)
    df_v1 = SalesService.process_sales_data_v1(db, raw_v1) if raw_v1 else pd.DataFrame()
    v1_data = _compile_engine_analytics(
        df=df_v1,
        rates_map=rates_map,
        selected_product=selected_product,
        page_number=page_number,
        page_size=page_size,
        is_v2=False,
    )

    return {
        "v2": v2_data,
        "v1": v1_data,
    }


# ==================== 5. Platforms Management Endpoints ====================

@router.get("/platforms")
def list_platforms(
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    platforms = db.query(SalesPlatform).order_by(SalesPlatform.id.asc()).all()
    return {
        "platforms": [
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "currency": p.currency,
                "fee_rate": float(p.fee_rate or 0.0),
                "fee_fixed": float(p.fee_fixed or 0.0),
                "fee_rate_pct_str": f"{(p.fee_rate or 0.0) * 100:.2f}%",
            }
            for p in platforms
        ],
        "currencies": ["CNY"] + [k for k in rates_map.keys() if k != "CNY"],
    }


@router.post("/platforms")
def add_platform(
    req: PlatformCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    code = req.code.strip().lower()
    name = req.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="平台代号和平台名称均不能为空")
    if db.query(SalesPlatform).filter(SalesPlatform.code == code).first():
        raise HTTPException(status_code=400, detail=f"平台代号 '{code}' 已存在")
    if db.query(SalesPlatform).filter(SalesPlatform.name == name).first():
        raise HTTPException(status_code=400, detail=f"平台名称 '{name}' 已存在")

    p = SalesPlatform(
        code=code,
        name=name,
        currency=req.currency.strip().upper(),
        fee_rate=req.fee_rate_pct / 100.0 if req.fee_rate_pct > 0 else 0.0,
        fee_fixed=req.fee_fixed,
    )
    db.add(p)
    db.commit()
    return {"message": f"成功追加销售平台: {name} ({p.currency})"}


@router.delete("/platforms/{platform_id}")
def delete_platform(
    platform_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    p = db.query(SalesPlatform).filter(SalesPlatform.id == platform_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="未找到该销售平台")
    name = p.name
    db.delete(p)
    db.commit()
    return {"message": f"已删除销售平台: {name}"}
