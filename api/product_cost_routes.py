"""
Product Management & Cost Accounting REST API Routes.
Reuses services.product_service.ProductService and services.cost_service.CostService directly.
"""
import io
import base64
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
import pandas as pd
from PIL import Image

from api.deps import verify_auth_token, get_db_session, load_rates_map
from services.product_service import ProductService
from services.cost_service import CostService
from constants import PRODUCT_COST_CATEGORIES, to_cny
from models import Product, SalesPlatform
from cache_manager import sync_all_caches

router = APIRouter(tags=["Product & Cost"])


def _format_curr_val(val: float, currency: str) -> str:
    if currency == "JPY":
        return f"{val:,.0f} JPY"
    return f"{val:,.2f} {currency}"


# ==================== Schemas ====================

class ColorPricePayload(BaseModel):
    platform_code: str
    platform_name: str = ""
    currency: str = "CNY"
    price: float = 0.0


class ColorPartPayload(BaseModel):
    part_name: str
    quantity: int = 1


class ColorFormPayload(BaseModel):
    id: int = 0
    color_name: str
    qty: int = 0
    image_url: str = ""
    image_base64: Optional[str] = None
    image_data: str = ""
    prices: List[ColorPricePayload] = []
    parts: List[ColorPartPayload] = []


class PartFormPayload(BaseModel):
    part_name: str
    req_qty: int = 1
    colors: List[str] = []


class ProductUpsertRequest(BaseModel):
    name: str
    platform: str = "微店"
    production_quantity: int = 100
    marketable_quantity: int = 95
    colors: List[ColorFormPayload] = []
    parts: List[PartFormPayload] = []
    part_names: List[str] = []


class BudgetCreateRequest(BaseModel):
    product_id: int
    category: str
    item_name: str
    unit_price: float
    qty: float = 1.0
    quantity: Optional[float] = None
    unit: str = ""
    shop: str = ""
    remark: str = ""
    remarks: str = ""
    url: str = ""
    currency: str = "CNY"


class CostItemUpdateRequest(BaseModel):
    item_name: str = ""
    category: str = ""
    unit: str = ""
    supplier: str = ""
    remark: str = ""
    remarks: str = ""
    url: str = ""
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total_budget: Optional[float] = None


class WipFixRequest(BaseModel):
    product_id: int


# ==================== Product Management Endpoints ====================

@router.get("/products")
def list_products(
    include_images: bool = Query(False),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    from sqlalchemy import func
    from models import CostItem

    plats = db.query(SalesPlatform).order_by(SalesPlatform.id.asc()).all()
    all_platforms = [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "currency": p.currency,
            "fee_rate": float(p.fee_rate or 0.0),
            "fee_fixed": float(p.fee_fixed or 0.0),
        }
        for p in plats
    ]

    service = ProductService(db)
    prods = service.get_all_products(include_images=include_images)
    result = []

    for p in prods:
        tot_actual = float(
            db.query(func.sum(CostItem.actual_cost)).filter(CostItem.product_id == p.id).scalar() or 0.0
        )
        mkt_qty = int(p.marketable_quantity if p.marketable_quantity is not None else (p.total_quantity or 0))
        prod_qty = int(p.total_quantity or mkt_qty)
        u_cost = round(tot_actual / mkt_qty, 2) if mkt_qty > 0 else 0.0

        all_part_names_set = []
        colors_dto = []
        for c in p.colors:
            c_prices_lookup = {pr.platform: float(pr.price or 0.0) for pr in c.prices}
            plat_prices = []
            for pl in all_platforms:
                p_code = pl["code"]
                p_price = c_prices_lookup.get(p_code, 0.0)
                plat_prices.append({
                    "platform_code": p_code,
                    "platform_name": pl["name"],
                    "price": p_price,
                    "currency": pl["currency"],
                })

            c_parts = []
            for pt in (c.parts or []):
                if pt.part_name not in all_part_names_set:
                    all_part_names_set.append(pt.part_name)
                c_parts.append({
                    "part_name": pt.part_name,
                    "quantity": int(pt.quantity or 1),
                })

            colors_dto.append({
                "id": c.id,
                "color_name": c.color_name,
                "image_url": f"/color-image/{c.id}",
                "prices": plat_prices,
                "parts": c_parts,
            })

        result.append({
            "id": p.id,
            "name": p.name,
            "production_quantity": prod_qty,
            "marketable_quantity": mkt_qty,
            "unit_cost": u_cost,
            "total_actual": round(tot_actual, 2),
            "colors": colors_dto,
            "all_part_names": all_part_names_set,
        })

    return {
        "products": result,
        "platforms": all_platforms,
    }


@router.get("/products/{product_id}")
def get_product_detail(
    product_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    service = ProductService(db)
    p = service.get_product_by_id(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="未找到该商品")

    plats = db.query(SalesPlatform).order_by(SalesPlatform.id.asc()).all()
    all_platforms = [
        {"code": pl.code, "name": pl.name, "currency": pl.currency}
        for pl in plats
    ]

    colors_payload = []
    parts_dict: Dict[tuple, List[str]] = {}

    for c in p.colors:
        price_map = {pr.platform: float(pr.price or 0.0) for pr in c.prices}
        c_prices = []
        for pl in all_platforms:
            c_prices.append({
                "platform_code": pl["code"],
                "platform_name": pl["name"],
                "currency": pl["currency"],
                "price": price_map.get(pl["code"], 0.0),
            })

        colors_payload.append({
            "color_id": c.id,
            "color_name": c.color_name,
            "qty": int(c.quantity or 0),
            "image_data": c.image_data or "",
            "prices": c_prices,
        })

        for pt in (c.parts or []):
            key = (pt.part_name, int(pt.quantity or 1))
            parts_dict.setdefault(key, []).append(c.color_name)

    parts_payload = [
        {"part_name": pt_name, "req_qty": r_qty, "colors": c_list}
        for (pt_name, r_qty), c_list in parts_dict.items()
    ]

    return {
        "id": p.id,
        "name": p.name,
        "platform": p.target_platform or "微店",
        "total_qty": int(p.total_quantity or 0),
        "is_completed": bool(p.is_production_completed),
        "colors": colors_payload,
        "parts": parts_payload,
        "all_platforms": all_platforms,
    }


@router.post("/products")
def create_product(
    req: ProductUpsertRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="商品名称不能为空")
    if not req.colors:
        raise HTTPException(status_code=400, detail="请至少添加一个颜色/款式")

    per_color_qty = max(1, (req.production_quantity or 100) // max(1, len(req.colors)))
    colors_with_prices = []
    part_records = []

    for c in req.colors:
        c_name = c.color_name.strip()
        if not c_name:
            continue
        prices_dict = {
            pr.platform_code: pr.price
            for pr in c.prices
            if pr.price and pr.price > 0
        }
        img_str = c.image_data or (f"data:image/png;base64,{c.image_base64}" if c.image_base64 else None)
        colors_with_prices.append({
            "name": c_name,
            "qty": int(c.qty or per_color_qty),
            "image_data": img_str,
            "prices": prices_dict,
        })
        for pt in (c.parts or []):
            if pt.part_name.strip():
                part_records.append({
                    "颜色名称": c_name,
                    "部件名称": pt.part_name.strip(),
                    "数量": max(1, int(pt.quantity or 1)),
                })

    if not colors_with_prices:
        raise HTTPException(status_code=400, detail="请至少填写一个有效颜色规格名称")

    for pt in req.parts:
        p_name = pt.part_name.strip()
        if not p_name:
            continue
        for target_c in pt.colors:
            part_records.append({
                "颜色名称": target_c.strip(),
                "部件名称": p_name,
                "数量": max(1, int(pt.req_qty or 1)),
            })
    parts_df = pd.DataFrame(part_records) if part_records else None

    try:
        service = ProductService(db)
        service.create_product(
            name=name,
            platform=req.platform.strip() or "微店",
            colors_with_prices=colors_with_prices,
            parts_df=parts_df,
        )
        prod_obj = db.query(Product).filter(Product.name == name).first()
        if prod_obj:
            if req.production_quantity > 0:
                prod_obj.total_quantity = req.production_quantity
            if req.marketable_quantity > 0:
                prod_obj.marketable_quantity = req.marketable_quantity
            db.commit()
        sync_all_caches()
        return {"message": f"成功创建新商品: {name}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"创建商品失败: {e}")


@router.put("/products/{product_id}")
def update_product(
    product_id: int,
    req: ProductUpsertRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="商品名称不能为空")
    if not req.colors:
        raise HTTPException(status_code=400, detail="请至少保留一个颜色/款式")

    per_color_qty = max(1, (req.production_quantity or 100) // max(1, len(req.colors)))
    matrix_rows = []
    image_map = {}
    part_records = []

    for c in req.colors:
        c_name = c.color_name.strip()
        if not c_name:
            continue
        row_dict: Dict[str, Any] = {
            "颜色名称": c_name,
            "库存/预计数量": int(c.qty or per_color_qty),
        }
        for pr in c.prices:
            row_dict[pr.platform_code] = float(pr.price or 0.0)
        matrix_rows.append(row_dict)
        img_str = c.image_data or (f"data:image/png;base64,{c.image_base64}" if c.image_base64 else "")
        if img_str:
            image_map[c_name] = img_str
        for pt in (c.parts or []):
            if pt.part_name.strip():
                part_records.append({
                    "颜色名称": c_name,
                    "部件名称": pt.part_name.strip(),
                    "数量": max(1, int(pt.quantity or 1)),
                })

    color_matrix_df = pd.DataFrame(matrix_rows)

    for pt in req.parts:
        p_name = pt.part_name.strip()
        if not p_name:
            continue
        for target_c in pt.colors:
            part_records.append({
                "颜色名称": target_c.strip(),
                "部件名称": p_name,
                "数量": max(1, int(pt.req_qty or 1)),
            })
    parts_df = pd.DataFrame(part_records) if part_records else None

    try:
        service = ProductService(db)
        service.update_product(
            product_id=product_id,
            name=name,
            platform=req.platform.strip() or "微店",
            color_matrix_data=color_matrix_df,
            parts_df=parts_df,
            image_map=image_map,
        )
        prod_obj = db.query(Product).filter(Product.id == product_id).first()
        if prod_obj:
            if req.production_quantity > 0:
                prod_obj.total_quantity = req.production_quantity
            if req.marketable_quantity > 0:
                prod_obj.marketable_quantity = req.marketable_quantity
            db.commit()
        sync_all_caches()
        return {"message": f"商品【{name}】修改已保存"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"更新商品失败: {e}")


@router.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = ProductService(db)
        service.delete_product(product_id)
        sync_all_caches()
        return {"message": "商品已成功删除"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/products/upload-image")
async def upload_product_image(
    file: UploadFile = File(...),
    username: str = Depends(verify_auth_token),
):
    try:
        raw = await file.read()
        img = Image.open(io.BytesIO(raw))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((300, 300))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"
        return {
            "image_base64": b64,
            "data_uri": data_url,
            "image_data": data_url,
            "message": "图片压缩上传成功",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"图片解析失败: {e}")


# ==================== Cost Accounting Endpoints ====================

@router.get("/costs")
def get_cost_accounting(
    product_name: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    service = CostService(db)
    products = service.get_all_products()

    prod_opts = [
        {
            "id": p.id,
            "name": p.name,
            "qty": int(p.marketable_quantity if p.marketable_quantity is not None else (p.total_quantity or 0)),
            "is_completed": bool(p.is_production_completed),
        }
        for p in products
    ]

    if not prod_opts:
        return {
            "has_product": False,
            "products": [],
            "categories": PRODUCT_COST_CATEGORIES,
            "currencies": list(rates_map.keys()),
        }

    target_prod = None
    if product_id:
        target_prod = next((p for p in products if p.id == product_id), None)
    if not target_prod and product_name:
        target_prod = next((p for p in products if p.name == product_name), None)
    if not target_prod:
        target_prod = products[0]

    prod = service.get_product_by_name(target_prod.name)
    make_qty = float(prod.marketable_quantity if prod.marketable_quantity is not None else (prod.total_quantity or 0))
    is_completed = bool(prod.is_production_completed)
    wip_offset = float(service.get_wip_offset(prod.id) or 0.0)
    raw_items = service.get_cost_items(prod.id)

    total_real_cost = sum(float(i.actual_cost or 0.0) for i in raw_items)
    budget_names = {i.item_name for i in raw_items if i.is_budget}
    total_budget_cost = sum(
        to_cny(float(i.unit_price or 0.0) * float(i.quantity or 0.0), i.currency or "CNY", rates_map)
        for i in raw_items if i.is_budget
    )
    for i in raw_items:
        if not i.is_budget and i.item_name not in budget_names:
            total_budget_cost += float(i.actual_cost or 0.0)

    unit_real_cost = total_real_cost / make_qty if make_qty > 0 else 0.0
    unit_budget_cost = total_budget_cost / make_qty if make_qty > 0 else 0.0
    remaining_wip = total_real_cost + wip_offset

    # Grouped items & subtotals by 9 categories
    grouped: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in PRODUCT_COST_CATEGORIES}
    for item in raw_items:
        cat = item.category or ""
        if "检品" in cat and "人工费" in cat:
            cat = "检品发货等人工费"
        if cat not in grouped:
            grouped[cat] = []

        is_b = bool(item.is_budget)
        curr = item.currency or "CNY"
        b_qty = float(item.quantity or 0.0) if is_b else 0.0
        b_price = float(item.unit_price or 0.0) if is_b else 0.0
        b_total = b_price * b_qty if is_b else 0.0

        orig_amt = float(item.original_amount if item.original_amount is not None else (item.actual_cost or 0.0))
        a_qty = float(item.actual_qty or 0.0) if is_b else float(item.quantity or 0.0)
        a_price = (
            float(item.actual_unit_price or 0.0)
            if is_b
            else (orig_amt / a_qty if a_qty > 0 else 0.0)
        )

        grouped[cat].append({
            "id": item.id,
            "item_name": item.item_name or "",
            "category": item.category or "",
            "unit": item.unit or "",
            "currency": curr,
            "is_budget": is_b,
            "budget_qty": b_qty,
            "budget_unit_price": b_price,
            "budget_total": b_total,
            "actual_qty": a_qty,
            "actual_unit_price": a_price,
            "actual_total": orig_amt,
            "actual_cost_cny": round(float(item.actual_cost or 0.0), 2),
            "supplier": item.supplier or "",
            "url": item.url or "",
            "remarks": item.remarks or "",
            "budget_qty_str": f"{b_qty:.2f}" if b_qty else "-",
            "budget_price_str": _format_curr_val(b_price, curr) if b_price else "-",
            "budget_total_str": _format_curr_val(b_total, curr) if b_total else "-",
            "actual_qty_str": f"{a_qty:.2f}" if a_qty else "-",
            "actual_price_str": _format_curr_val(a_price, curr) if a_price else "-",
            "actual_total_str": _format_curr_val(orig_amt, curr) if orig_amt else "-",
        })

    subtotals: Dict[str, Dict[str, Any]] = {}
    for cat in PRODUCT_COST_CATEGORIES:
        cat_items = [
            i for i in raw_items
            if i.category == cat or (cat == "检品发货等人工费" and "检品" in (i.category or ""))
        ]
        real_tot = sum(float(i.actual_cost or 0.0) for i in cat_items)
        cat_b_names = {i.item_name for i in cat_items if i.is_budget}
        bud_tot = sum(
            to_cny(float(i.unit_price or 0.0) * float(i.quantity or 0.0), i.currency or "CNY", rates_map)
            for i in cat_items if i.is_budget
        )
        for i in cat_items:
            if not i.is_budget and i.item_name not in cat_b_names:
                bud_tot += float(i.actual_cost or 0.0)

        real_u = real_tot / make_qty if make_qty > 0 else 0.0
        bud_u = bud_tot / make_qty if make_qty > 0 else 0.0
        subtotals[cat] = {
            "real_total": round(real_tot, 2),
            "budget_total": round(bud_tot, 2),
            "real_str": f"{real_tot:,.2f} CNY",
            "budget_str": f"{bud_tot:,.2f} CNY",
            "real_unit_str": f"{real_u:,.2f} CNY",
            "budget_unit_str": f"{bud_u:,.2f} CNY",
        }

    # Profit references grouped by platform for mobile CostAccountingScreen
    plats = db.query(SalesPlatform).order_by(SalesPlatform.id.asc()).all()
    profit_refs = []
    if make_qty > 0:
        for p in plats:
            color_profits = []
            for color in prod.colors:
                price_val = 0.0
                for pr in (color.prices or []):
                    if pr.platform in (p.code, p.name):
                        price_val = float(pr.price or 0.0)
                        break
                if price_val > 0:
                    fee_val = price_val * float(p.fee_rate or 0.0) + float(p.fee_fixed or 0.0)
                    price_cny = to_cny(price_val, p.currency, rates_map)
                    fee_cny = to_cny(fee_val, p.currency, rates_map)
                    margin = price_cny - fee_cny - unit_real_cost
                    margin_rate = (margin / price_cny * 100.0) if price_cny > 0 else 0.0
                    color_profits.append({
                        "color_name": color.color_name,
                        "orig_price_str": f"{price_val:,.2f} {p.currency}",
                        "cny_revenue": round(price_cny, 2),
                        "cny_fee": round(fee_cny, 2),
                        "net_profit": round(margin, 2),
                        "margin_pct": round(margin_rate, 1),
                    })
            if color_profits:
                profit_refs.append({
                    "platform_code": p.code,
                    "platform_name": p.name,
                    "currency": p.currency,
                    "fee_desc": f"费率 {(p.fee_rate or 0.0) * 100:.2f}% + 固定 {p.fee_fixed or 0.0}",
                    "colors": color_profits,
                })

    cat_groups = []
    for cat in PRODUCT_COST_CATEGORIES:
        st = subtotals.get(cat, {})
        b_tot = float(st.get("budget_total", 0.0))
        r_tot = float(st.get("real_total", 0.0))
        c_items = []
        for gi in grouped.get(cat, []):
            c_items.append({
                "id": gi["id"],
                "category": cat,
                "item_name": gi["item_name"],
                "is_budget": gi["is_budget"],
                "actual_cost": gi["actual_cost_cny"] if not gi["is_budget"] else round(to_cny(gi["budget_total"], gi["currency"], rates_map), 2),
                "unit_price": gi["budget_unit_price"] if gi["is_budget"] else gi["actual_unit_price"],
                "quantity": gi["budget_qty"] if gi["is_budget"] else gi["actual_qty"],
                "currency": gi["currency"],
                "original_amount": gi["actual_total"],
                "shop": gi["supplier"],
                "remark": gi["remarks"],
                "url": gi["url"],
            })
        cat_groups.append({
            "category": cat,
            "budget_total": b_tot,
            "actual_total": r_tot,
            "diff": round(b_tot - r_tot, 2),
            "is_over_budget": (r_tot > b_tot and b_tot > 0),
            "items": c_items,
        })

    prod_qty = int(prod.total_quantity or make_qty)
    return {
        "has_product": True,
        "products": prod_opts,
        "selected_product_id": prod.id,
        "selected_product_name": prod.name,
        "production_quantity": prod_qty,
        "marketable_quantity": int(make_qty),
        "make_qty": int(make_qty),
        "is_production_completed": is_completed,
        "total_budget": round(total_budget_cost, 2),
        "total_actual": round(total_real_cost, 2),
        "total_diff": round(total_budget_cost - total_real_cost, 2),
        "unit_budget_prod": round(total_budget_cost / prod_qty, 2) if prod_qty > 0 else 0.0,
        "unit_actual_prod": round(total_real_cost / prod_qty, 2) if prod_qty > 0 else 0.0,
        "unit_budget_mkt": round(unit_budget_cost, 2),
        "unit_actual_mkt": round(unit_real_cost, 2),
        "wip_balance": round(remaining_wip, 2),
        "categories": cat_groups,
        "cost_categories": PRODUCT_COST_CATEGORIES,
        "profit_references": profit_refs,
        "currencies": list(rates_map.keys()),
    }


@router.post("/costs/budget")
def add_cost_budget(
    req: BudgetCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.item_name.strip():
        raise HTTPException(status_code=400, detail="预算名目不能为空")
    final_qty = req.quantity if (req.quantity is not None and req.quantity > 0) else req.qty
    if req.unit_price <= 0 or final_qty <= 0:
        raise HTTPException(status_code=400, detail="单价和数量必须大于 0")
    try:
        service = CostService(db)
        service.add_budget_item(
            product_id=req.product_id,
            category=req.category,
            name=req.item_name.strip(),
            unit_price=req.unit_price,
            quantity=final_qty,
            unit=req.unit.strip(),
            remarks=(req.remark or req.remarks).strip(),
            currency=req.currency,
        )
        sync_all_caches()
        return {"message": f"成功添加预算项: {req.item_name.strip()}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"添加预算失败: {e}")


@router.put("/costs/item/{item_id}")
def update_cost_item(
    item_id: int,
    req: CostItemUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    updates: Dict[str, Any] = {
        "remarks": (req.remark or req.remarks).strip(),
        "url": req.url.strip(),
    }
    if req.item_name.strip():
        updates["item_name"] = req.item_name.strip()
    if req.category.strip():
        updates["category"] = req.category.strip()
    if req.unit.strip():
        updates["unit"] = req.unit.strip()
    if req.supplier.strip():
        updates["supplier"] = req.supplier.strip()
    if req.quantity is not None:
        updates["quantity"] = req.quantity
    if req.unit_price is not None:
        updates["unit_price"] = req.unit_price
    if req.total_budget is not None:
        updates["total_budget"] = req.total_budget

    try:
        service = CostService(db)
        service.update_cost_item(item_id, updates)
        sync_all_caches()
        return {"message": "成本项更新成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"修改成本项失败: {e}")


@router.delete("/costs/item/{item_id}")
def delete_cost_item(
    item_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = CostService(db)
        service.delete_cost_item(item_id)
        sync_all_caches()
        return {"message": "成本/预算项已删除"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/costs/wip-fix")
def fix_product_wip(
    req: WipFixRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        service = CostService(db)
        service.perform_wip_fix(req.product_id)
        sync_all_caches()
        return {"message": "商品生产状态已标记为【生产完工】，在制品(WIP)已自动结转！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"在制品结转失败: {e}")
