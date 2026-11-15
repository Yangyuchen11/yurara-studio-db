"""
Consignment Management REST API Routes (under Sales Management).
Covers: Consignment Shops, Dispatch from Warehouse, Return to Warehouse,
Single/Batch Settlement with Shop Fees & Account Crediting, and Audit Histories.
"""
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import verify_auth_token, get_db_session, load_rates_map
from services.consignment_service import ConsignmentService
from constants import BalanceCategory, to_cny
from models import CompanyBalanceItem, Product, Warehouse
from cache_manager import sync_all_caches

router = APIRouter(tags=["Consignment Sales"])


# ==================== Request Schemas ====================

class ConsignmentShopSaveRequest(BaseModel):
    name: str
    currency: str = "CNY"
    default_fee_rate: float = 0.0
    default_fee_fixed: float = 0.0
    default_account_name: str = ""
    contact_info: str = ""
    remarks: str = ""


class DispatchCellPayload(BaseModel):
    variant: str
    part_name: Optional[str] = None
    quantity: int


class ConsignmentDispatchRequest(BaseModel):
    shop_id: Optional[int] = None
    shop_name: str = ""
    warehouse_id: Optional[int] = None
    product_name: str
    date: str = ""
    remarks: str = ""
    entries: List[DispatchCellPayload] = []


class ConsignmentManualCreateRequest(BaseModel):
    shop_id: Optional[int] = None
    shop_name: str = ""
    product_name: str
    variant: str = "通用"
    part_name: Optional[str] = None
    quantity: int = 1
    remaining_qty: Optional[int] = None
    unit_price: float = 0.0
    currency: str = "CNY"
    date: str = ""
    remarks: str = ""


class ConsignmentItemUpdateRequest(BaseModel):
    shop_name: Optional[str] = None
    remaining_qty: Optional[int] = None
    unit_price: Optional[float] = None
    remarks: Optional[str] = None


class ReturnEntryPayload(BaseModel):
    consignment_item_id: int
    return_qty: int


class ConsignmentReturnRequest(BaseModel):
    warehouse_id: int
    return_date: str = ""
    notes: str = ""
    entries: List[ReturnEntryPayload] = []


class SettlementEntryPayload(BaseModel):
    consignment_item_id: int
    sold_qty: int
    unit_price: float = 0.0


class ConsignmentSettlementRequest(BaseModel):
    shop_id: Optional[int] = None
    shop_name: str = ""
    account_id: int
    settlement_date: str = ""
    currency: str = "CNY"
    fee_rate: Optional[float] = None
    fee_amount: Optional[float] = None
    net_amount: Optional[float] = None
    notes: str = ""
    items: List[SettlementEntryPayload] = []


# ==================== Endpoints ====================

@router.get("/consignments")
def get_consignment_page_data(
    shop_id: Optional[int] = Query(None),
    status: str = Query("全部"),
    search: str = Query(""),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    service = ConsignmentService(db)
    rates_map = load_rates_map(db)

    shops = service.get_shop_summaries()
    status_filter = None if status in ("", "全部", "全部状态") else status
    raw_items = service.get_all_consignments(
        shop_id=shop_id,
        status=status_filter,
        search=search,
    )

    wh_map = {w.id: w.name for w in db.query(Warehouse).all()}
    items_dto = []
    for c in raw_items:
        items_dto.append({
            "id": c.id,
            "shop_id": c.shop_id or 0,
            "shop_name": c.shop_name or "",
            "warehouse_id": c.warehouse_id or 0,
            "warehouse_name": (c.warehouse.name if c.warehouse else wh_map.get(c.warehouse_id, "未指定")) if c.warehouse_id else "未指定",
            "product_name": c.product_name or "",
            "variant": c.variant or "通用",
            "part_name": c.part_name or "整套",
            "quantity": int(c.quantity or 0),
            "sold_qty": int(c.sold_qty or 0),
            "returned_qty": int(c.returned_qty or 0),
            "remaining_qty": int(c.remaining_qty or 0),
            "unit_price": round(float(c.unit_price or 0.0), 2),
            "currency": c.currency or "CNY",
            "status": c.status or "寄售中",
            "date": c.date.strftime("%Y-%m-%d") if c.date else "",
            "remarks": c.remarks or "",
        })

    raw_settlements = service.get_settlements(shop_id=shop_id)
    settlements_dto = []
    total_settled_cny = 0.0
    for st in raw_settlements:
        net_val = float(st.net_amount or 0.0)
        total_settled_cny += to_cny(net_val, st.currency or "CNY", rates_map)
        settlements_dto.append({
            "id": st.id,
            "settlement_no": st.settlement_no or "",
            "shop_id": st.shop_id or 0,
            "shop_name": st.shop_name or "",
            "settlement_date": st.settlement_date.strftime("%Y-%m-%d") if st.settlement_date else "",
            "currency": st.currency or "CNY",
            "gross_amount": round(float(st.gross_amount or 0.0), 2),
            "fee_rate": float(st.fee_rate or 0.0),
            "fee_amount": round(float(st.fee_amount or 0.0), 2),
            "net_amount": round(net_val, 2),
            "account_id": st.account_id or 0,
            "account_name": st.account_name or "",
            "sales_order_id": st.sales_order_id or 0,
            "notes": st.notes or "",
            "total_sold_qty": sum(int(i.sold_qty or 0) for i in st.items),
            "items": [
                {
                    "id": si.id,
                    "consignment_item_id": si.consignment_item_id or 0,
                    "product_name": si.product_name or "",
                    "variant": si.variant or "",
                    "part_name": si.part_name or "整套",
                    "sold_qty": int(si.sold_qty or 0),
                    "unit_price": round(float(si.unit_price or 0.0), 2),
                    "gross_subtotal": round(float(si.gross_subtotal or 0.0), 2),
                    "net_subtotal": round(float(si.net_subtotal or 0.0), 2),
                }
                for si in st.items
            ],
        })

    raw_returns = service.get_return_history()
    returns_dto = [
        {
            "id": r.id,
            "consignment_item_id": r.consignment_item_id or 0,
            "shop_name": r.shop_name or "",
            "product_name": r.product_name or "",
            "variant": r.variant or "",
            "part_name": r.part_name or "整套",
            "warehouse_id": r.warehouse_id or 0,
            "warehouse_name": r.warehouse_name or "",
            "return_qty": int(r.return_qty or 0),
            "return_date": r.return_date.strftime("%Y-%m-%d") if r.return_date else "",
            "notes": r.notes or "",
        }
        for r in raw_returns
    ]

    warehouses = [
        {"id": w.id, "name": w.name}
        for w in db.query(Warehouse).order_by(Warehouse.id.asc()).all()
    ]
    accounts = [
        {
            "id": a.id,
            "name": a.name,
            "currency": a.currency or "CNY",
            "amount": round(float(a.amount or 0.0), 2),
        }
        for a in db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.category == BalanceCategory.ASSET,
            CompanyBalanceItem.asset_type == "现金",
        ).all()
    ]
    products = []
    for p in db.query(Product).order_by(Product.id.desc()).all():
        colors = []
        for c in p.colors:
            prices = [
                {"platform": pr.platform or "", "currency": pr.currency or "CNY", "price": float(pr.price or 0.0)}
                for pr in (c.prices or [])
            ]
            parts = ["整套"] + [pt.part_name for pt in (c.parts or [])]
            colors.append({"color_name": c.color_name, "prices": prices, "parts": parts})
        products.append({"id": p.id, "name": p.name, "colors": colors})

    return {
        "shops": shops,
        "items": items_dto,
        "settlements": settlements_dto,
        "returns": returns_dto,
        "warehouses": warehouses,
        "accounts": accounts,
        "products": products,
        "currencies": list(rates_map.keys()),
        "summary": {
            "shop_count": len(shops),
            "total_remaining_qty": sum(i["remaining_qty"] for i in items_dto),
            "total_sold_qty": sum(i["sold_qty"] for i in items_dto),
            "total_returned_qty": sum(i["returned_qty"] for i in items_dto),
            "total_settled_cny": round(total_settled_cny, 2),
        },
    }


@router.post("/consignments/shops")
def create_consignment_shop(
    req: ConsignmentShopSaveRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsignmentService(db)
        shop = service.create_shop(
            name=req.name,
            currency=req.currency,
            default_fee_rate=req.default_fee_rate,
            default_fee_fixed=req.default_fee_fixed,
            default_account_name=req.default_account_name,
            contact_info=req.contact_info,
            remarks=req.remarks,
        )
        db.commit()
        return {"message": f"寄售店铺【{shop.name}】创建成功！", "shop_id": shop.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")


@router.put("/consignments/shops/{shop_id}")
def update_consignment_shop(
    shop_id: int,
    req: ConsignmentShopSaveRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsignmentService(db)
        shop = service.update_shop(
            shop_id=shop_id,
            name=req.name,
            currency=req.currency,
            default_fee_rate=req.default_fee_rate,
            default_fee_fixed=req.default_fee_fixed,
            default_account_name=req.default_account_name,
            contact_info=req.contact_info,
            remarks=req.remarks,
        )
        db.commit()
        return {"message": f"寄售店铺【{shop.name}】信息已更新！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"更新失败: {e}")


@router.delete("/consignments/shops/{shop_id}")
def delete_consignment_shop(
    shop_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsignmentService(db)
        service.delete_shop(shop_id)
        db.commit()
        return {"message": "寄售店铺已删除！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除失败: {e}")


@router.post("/consignments/dispatch")
def dispatch_to_consignment_shop(
    req: ConsignmentDispatchRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        d_val = date.fromisoformat(req.date) if req.date else date.today()
    except Exception:
        d_val = date.today()

    try:
        service = ConsignmentService(db)
        entries = [
            {
                "variant": e.variant,
                "part_name": None if (not e.part_name or e.part_name == "整套") else e.part_name,
                "quantity": e.quantity,
            }
            for e in req.entries
            if e.quantity > 0
        ]
        msg = service.dispatch_from_warehouse(
            shop_id=req.shop_id,
            shop_name=req.shop_name,
            warehouse_id=req.warehouse_id,
            product_name=req.product_name,
            entries=entries,
            dispatch_date=d_val,
            remarks=req.remarks,
        )
        db.commit()
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"寄售出库失败: {e}")


@router.post("/consignments/manual")
def add_manual_consignment_item(
    req: ConsignmentManualCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        d_val = date.fromisoformat(req.date) if req.date else date.today()
    except Exception:
        d_val = date.today()

    try:
        service = ConsignmentService(db)
        service.add_manual_consignment(
            shop_id=req.shop_id,
            shop_name=req.shop_name,
            product_name=req.product_name,
            variant=req.variant,
            part_name=req.part_name,
            quantity=req.quantity,
            remaining_qty=req.remaining_qty,
            unit_price=req.unit_price,
            currency=req.currency,
            remarks=req.remarks,
            date_obj=d_val,
        )
        db.commit()
        return {"message": "已手动补录寄售库存！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"补录失败: {e}")


@router.put("/consignments/items/{item_id}")
def update_consignment_item(
    item_id: int,
    req: ConsignmentItemUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsignmentService(db)
        service.update_consignment_item(
            item_id=item_id,
            remaining_qty=req.remaining_qty,
            remarks=req.remarks,
            shop_name=req.shop_name,
            unit_price=req.unit_price,
        )
        db.commit()
        return {"message": "寄售记录已更新！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"更新失败: {e}")


@router.delete("/consignments/items/{item_id}")
def delete_consignment_item_route(
    item_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsignmentService(db)
        service.delete_consignment_item(item_id)
        db.commit()
        sync_all_caches()
        return {"message": "寄售记录已删除！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"删除失败: {e}")


@router.post("/consignments/return")
def return_consignment_to_warehouse(
    req: ConsignmentReturnRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        r_date = date.fromisoformat(req.return_date) if req.return_date else date.today()
    except Exception:
        r_date = date.today()

    try:
        service = ConsignmentService(db)
        entries = [
            {"consignment_item_id": e.consignment_item_id, "return_qty": e.return_qty}
            for e in req.entries
            if e.return_qty > 0
        ]
        created = service.return_to_warehouse(
            entries=entries,
            warehouse_id=req.warehouse_id,
            return_date=r_date,
            notes=req.notes,
        )
        db.commit()
        sync_all_caches()
        total_qty = sum(r.return_qty for r in created)
        return {"message": f"成功退回 {total_qty} 件商品至仓库！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"退回仓库失败: {e}")


@router.delete("/consignments/returns/{return_id}")
def revoke_consignment_return(
    return_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsignmentService(db)
        msg = service.revoke_return(return_id)
        db.commit()
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"撤销退回失败: {e}")


@router.post("/consignments/settlements")
def create_consignment_settlement(
    req: ConsignmentSettlementRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        s_date = date.fromisoformat(req.settlement_date) if req.settlement_date else date.today()
    except Exception:
        s_date = date.today()

    try:
        service = ConsignmentService(db)
        items_payload = [
            {
                "consignment_item_id": i.consignment_item_id,
                "sold_qty": i.sold_qty,
                "unit_price": i.unit_price,
            }
            for i in req.items
            if i.sold_qty > 0
        ]
        settlement = service.create_settlement(
            shop_id=req.shop_id,
            shop_name=req.shop_name,
            items=items_payload,
            account_id=req.account_id,
            settlement_date=s_date,
            currency=req.currency,
            fee_rate=req.fee_rate,
            fee_amount=req.fee_amount,
            net_amount=req.net_amount,
            notes=req.notes,
        )
        db.commit()
        sync_all_caches()
        return {
            "message": f"寄售结算成功！单号 {settlement.settlement_no}，入账 {settlement.net_amount:.2f} {settlement.currency} 至【{settlement.account_name}】",
            "settlement_id": settlement.id,
            "settlement_no": settlement.settlement_no,
            "gross_amount": float(settlement.gross_amount or 0.0),
            "fee_amount": float(settlement.fee_amount or 0.0),
            "net_amount": float(settlement.net_amount or 0.0),
            "sales_order_id": int(settlement.sales_order_id or 0),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"结算失败: {e}")


@router.delete("/consignments/settlements/{settlement_id}")
def delete_consignment_settlement(
    settlement_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ConsignmentService(db)
        msg = service.delete_settlement(settlement_id)
        db.commit()
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"撤销结算失败: {e}")
