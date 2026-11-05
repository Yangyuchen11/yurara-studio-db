"""
Finance Records, Balance Overview, and Financial Reports REST API Routes.
Reuses services.finance_service, services.balance_service, and state sync helpers directly.
"""
import re
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import verify_auth_token, get_db_session, is_test_mode_header, load_rates_map, format_currency
from services.finance_service import FinanceService
from services.balance_service import BalanceService
from constants import PRODUCT_COST_CATEGORIES, to_cny
from models import ConsumableItem, CostItem, FinanceRecord, Product
from cache_manager import sync_all_caches

EXPENSE_CATEGORIES = [
    "商品成本",
    "商品成本待付款",
    "固定资产购入",
    "其他资产购入",
    "其他待付款",
    "杂费/其他支出",
    "现有资产减少",
    "利润分配/分红",
]
INCOME_CATEGORIES = [
    "销售收入",
    "股东注资/资本增加",
    "其他收入",
    "现有资产增加",
    "新资产增加",
]
DEBT_TYPES = ["金钱借入(需还现金)", "业务欠款(预收/代垫)"]
BATCH_CATEGORIES = ["商品成本", "固定资产购入", "其他资产购入"]
ASSET_SUB_CATEGORIES = ["生产耗材", "包装材料", "展会物资", "办公用品", "赠品/特典", "其他耗材"]

router = APIRouter(tags=["Finance & Reports"])


# ==================== Request Schemas ====================

class SingleTransactionRequest(BaseModel):
    date: str
    rec_type: str  # "支出" or "收入"
    currency: str = "CNY"
    amount: float
    category: str
    shop: str = ""
    desc: str = ""
    url: str = ""
    account_id: Optional[int] = None
    asset_purchase_mode: str = "new"  # "new" or "replenish"
    replenish_asset_id: Optional[int] = None
    replenish_qty: float = 1.0


class BatchItemPayload(BaseModel):
    name: str
    amount: float
    qty: float = 1.0
    desc: str = ""
    url: str = ""


class BatchExpenseRequest(BaseModel):
    date: str
    currency: str = "CNY"
    account_id: int
    shop: str = ""
    category: str  # "商品成本", "固定资产购入", "其他资产购入"
    product_id: Optional[int] = None
    cost_cat: str = "材料费"
    asset_cat: str = "生产耗材"
    shipping_fee: float = 0.0
    selected_budget_id: Optional[int] = None
    items: List[BatchItemPayload]


class PendingCostItemPayload(BaseModel):
    name: str
    amount: float
    qty: float = 1.0
    remark: str = ""
    url: str = ""


class PendingPaymentRequest(BaseModel):
    date: str
    currency: str = "CNY"
    category: str  # "商品成本待付款" or "其他待付款"
    shop: str = ""
    product_id: Optional[int] = None
    cost_cat: str = "材料费"
    shipping_fee: float = 0.0
    selected_budget_id: Optional[int] = None
    items: List[PendingCostItemPayload] = []
    amount: float = 0.0
    desc: str = ""
    url: str = ""


class ExchangeTransactionRequest(BaseModel):
    date: str
    out_account_id: int
    out_amount: float
    in_account_id: int
    in_amount: float
    shop: str = ""
    desc: str = ""
    url: str = ""


class DebtCreateRequest(BaseModel):
    date: str
    debt_type: str  # "金钱借入(需还现金)" or "业务欠款(预收/代垫)"
    currency: str = "CNY"
    amount: float
    creditor: str
    account_id: Optional[int] = None
    desc: str = ""
    url: str = ""


class DebtRepayRequest(BaseModel):
    date: str
    debt_id: int
    account_id: int
    amount: float
    desc: str = ""
    url: str = ""
    overpay_product_id: Optional[int] = None
    overpay_cost_cat: str = "加工费"
    overpay_item_name: str = ""


class DebtOffsetRequest(BaseModel):
    date: str
    debt_id: int
    asset_id: int
    offset_cny_val: float
    desc: str = ""


class FundTransferRequest(BaseModel):
    date: str
    from_asset_id: int
    to_asset_id: int
    amount: float
    desc: str = ""


class RecordUpdateRequest(BaseModel):
    date: str
    type: str
    amount_abs: float
    category: str
    desc: str = ""
    url: str = ""
    account_id: Optional[int] = None


class CashAccountCreateRequest(BaseModel):
    name: str
    currency: str = "CNY"
    initial_amount: float = 0.0


# ==================== Finance Records Endpoints ====================

@router.get("/finance/page")
def get_finance_page(
    search_query: str = "",
    filter_type: str = "全部",
    filter_category: str = "全部",
    batch_product_id: str = "",
    batch_cost_cat: str = "材料费",
    page_number: int = 1,
    is_test: bool = Depends(is_test_mode_header),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    from yurara_app.state.finance_state import _sync_load_finance_data
    
    # In database query, '全部' means no filtering
    clean_type = "" if filter_type in ("", "全部") else filter_type
    clean_cat = "" if filter_category in ("", "全部") else filter_category

    data = _sync_load_finance_data(
        is_test=is_test,
        rates_map=rates_map,
        page=page_number,
        search_query=search_query,
        filter_type=clean_type,
        filter_category=clean_cat,
        batch_product_id=batch_product_id,
        batch_cost_cat=batch_cost_cat,
    )
    
    indicators = data.get("indicators", [])
    cash_bd = []
    for ind in indicators:
        curr = getattr(ind, "currency", None) or (ind.get("currency") if isinstance(ind, dict) else "CNY")
        amt_s = getattr(ind, "amount_str", None) or (ind.get("amount_str") if isinstance(ind, dict) else "")
        cash_bd.append({"currency": str(curr), "amount_str": str(amt_s)})
    
    # Parse cash_accounts to {id, name, currency, amount}
    parsed_accounts = []
    acc_map = {}
    for ca in data.get("cash_accounts", []):
        ca_id = getattr(ca, "id", None) or (ca.get("id") if isinstance(ca, dict) else 0)
        lbl = getattr(ca, "label", None) or (ca.get("label") if isinstance(ca, dict) else "")
        curr = getattr(ca, "currency", None) or (ca.get("currency") if isinstance(ca, dict) else "CNY")
        amt_match = re.search(r'余额:\s*([0-9,\.\-]+)', lbl)
        amt_val = float(amt_match.group(1).replace(",", "")) if amt_match else 0.0
        name_clean = re.sub(r'\[.*?\]\s*', '', lbl)
        name_clean = re.sub(r'\s*\(余额:.*?\)', '', name_clean).strip()
        acc_dict = {
            "id": int(ca_id),
            "name": name_clean or lbl,
            "currency": curr,
            "amount": amt_val,
        }
        parsed_accounts.append(acc_dict)
        acc_map[str(ca_id)] = acc_dict
        acc_map[name_clean] = acc_dict
        acc_map[lbl] = acc_dict
        if "流动资金-" in name_clean:
            acc_map[name_clean.replace("流动资金-", "")] = acc_dict
        else:
            acc_map[f"流动资金-{name_clean}"] = acc_dict

    # Transform raw data to match Android FinancePageResponse contract
    records_list = []
    raw_recs = data.get("processed_records", [])
    for r in raw_recs:
        r_dict = r.model_dump() if hasattr(r, "model_dump") else (r.dict() if hasattr(r, "dict") else r)
        r_curr = str(r_dict.get("currency", "CNY"))
        r_amt = float(r_dict.get("amount", 0.0))
        r_type = str(r_dict.get("type", "支出"))
        amt_prefix = "+" if r_type == "收入" else "-"
        amt_formatted = f"{amt_prefix}{format_currency(r_amt, r_curr)}"
        cny_equiv = to_cny(r_amt, r_curr, rates_map)
        cny_eq_str = f"¥ {cny_equiv:,.2f}" if r_curr != "CNY" and cny_equiv > 0 else ""
        
        # Extract account name from desc if present
        raw_desc = str(r_dict.get("desc", ""))
        acc_match = re.search(r'\[账户:\s*(.*?)\]', raw_desc)
        extracted_acc = acc_match.group(1).strip() if acc_match else ""

        # Match account object
        matched_acc = None
        if extracted_acc:
            matched_acc = acc_map.get(extracted_acc)
            if not matched_acc:
                for k, v in acc_map.items():
                    if k and (k in extracted_acc or extracted_acc in k):
                        matched_acc = v
                        break

        matched_acc_id = matched_acc["id"] if matched_acc else int(r_dict.get("account_id") or 0)
        acc_bal_str = format_currency(matched_acc["amount"], matched_acc["currency"]) if matched_acc else ""

        # Running balance calculation for this currency after transaction
        bal_after = float(r_dict.get("cny_bal", 0.0)) if r_curr == "CNY" else float(r_dict.get("jpy_bal", 0.0))
        bal_after_str = format_currency(bal_after, r_curr) if bal_after != 0.0 else ""

        # Clean description without redundant [账户: xxx] and [cost_item:xxx]
        clean_desc = re.sub(r'\s*\[账户:\s*.*?\]', '', raw_desc)
        clean_desc = re.sub(r'\s*\[cost_item:\d+\]', '', clean_desc).strip()

        records_list.append({
            "id": int(r_dict.get("id", 0)),
            "date_str": str(r_dict.get("date", "")),
            "type": r_type,
            "category": str(r_dict.get("category", "")),
            "description": clean_desc or raw_desc,
            "amount_str": amt_formatted,
            "cny_equiv_str": cny_eq_str,
            "account_name": extracted_acc or (matched_acc["name"] if matched_acc else ""),
            "url": str(r_dict.get("url", "") or ""),
            "amount_raw": r_amt,
            "currency": r_curr,
            "account_id": matched_acc_id,
            "account_balance_str": acc_bal_str,
            "running_balance_str": bal_after_str,
        })

    # Parse unsettled_debts
    parsed_debts = []
    for ud in data.get("unsettled_debts", []):
        ud_id = getattr(ud, "id", None) or (ud.get("id") if isinstance(ud, dict) else 0)
        lbl = getattr(ud, "label", None) or (ud.get("label") if isinstance(ud, dict) else "")
        curr = getattr(ud, "currency", None) or (ud.get("currency") if isinstance(ud, dict) else "CNY")
        amt = getattr(ud, "amount", None) or (ud.get("amount") if isinstance(ud, dict) else 0.0)
        src = getattr(ud, "source_type", None) or (ud.get("source_type") if isinstance(ud, dict) else "")
        parsed_debts.append({
            "id": int(ud_id),
            "name": lbl,
            "currency": curr,
            "amount": float(amt or 0.0),
            "description": src,
        })

    # Parse offset_assets
    parsed_offset = []
    for oa in data.get("offset_assets", []):
        oa_id = getattr(oa, "id", None) or (oa.get("id") if isinstance(oa, dict) else 0)
        lbl = getattr(oa, "label", None) or (oa.get("label") if isinstance(oa, dict) else "")
        amt_match = re.search(r'余额:\s*([0-9,\.\-]+)', lbl)
        amt_val = float(amt_match.group(1).replace(",", "")) if amt_match else 0.0
        parsed_offset.append({
            "id": int(oa_id),
            "name": lbl,
            "currency": "CNY",
            "amount": amt_val,
        })

    # Parse products_list
    parsed_products = []
    for p in data.get("products_list", []):
        p_id = getattr(p, "id", None) or (p.get("id") if isinstance(p, dict) else 0)
        lbl = getattr(p, "label", None) or (p.get("label") if isinstance(p, dict) else "")
        parsed_products.append({
            "id": int(p_id),
            "name": lbl,
        })

    all_cats = list(dict.fromkeys(
        ["全部"] + EXPENSE_CATEGORIES + INCOME_CATEGORIES + DEBT_TYPES + BATCH_CATEGORIES + ASSET_SUB_CATEGORIES
    ))

    return {
        "cash_total_cny": round(float(data.get("total_equiv_cny", 0.0)), 2),
        "cash_breakdown": cash_bd,
        "cash_accounts": parsed_accounts,
        "products": parsed_products,
        "debts": parsed_debts,
        "offset_assets": parsed_offset,
        "replenish_consumables": [],
        "budgets": [],
        "records_data": records_list,
        "total_records": data.get("total_records", 0),
        "total_pages": data.get("total_pages", 1),
        "current_page": data.get("cur_page", 1),
        "all_categories": all_cats,
        "meta": {
            "expense_categories": EXPENSE_CATEGORIES,
            "income_categories": INCOME_CATEGORIES,
            "debt_types": DEBT_TYPES,
            "batch_categories": BATCH_CATEGORIES,
            "asset_sub_categories": ASSET_SUB_CATEGORIES,
            "cost_categories": PRODUCT_COST_CATEGORIES,
        }
    }


@router.get("/finance/budgets")
def get_product_budgets(
    product_id: int = Query(...),
    cost_cat: str = Query("材料费"),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    items = db.query(CostItem).filter(
        CostItem.product_id == product_id,
        CostItem.category == cost_cat,
        CostItem.is_budget == True,
    ).all()
    return {
        "budgets": [
            {
                "id": str(b.id),
                "name": b.item_name,
                "amount": round(float((b.unit_price or 0.0) * (b.quantity or 1.0)), 2),
                "quantity": float(b.quantity or 1.0),
                "label": f"{b.item_name} (预算: {(b.unit_price or 0.0) * (b.quantity or 1.0):,.2f} {b.currency or 'CNY'})",
            }
            for b in items
        ]
    }


@router.post("/finance/transaction")
def create_single_transaction(
    req: SingleTransactionRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    try:
        if req.rec_type == "支出" and req.category == "其他资产购入" and req.asset_purchase_mode == "replenish":
            if not req.replenish_asset_id:
                raise HTTPException(status_code=400, detail="请选择要补充的耗材/资产项目")
            if req.amount <= 0 or req.replenish_qty <= 0:
                raise HTTPException(status_code=400, detail="金额与补充数量必须大于 0")
            if not req.account_id:
                raise HTTPException(status_code=400, detail="未指定扣款现金账户")

            target_con = db.query(ConsumableItem).filter(ConsumableItem.id == req.replenish_asset_id).first()
            if not target_con:
                raise HTTPException(status_code=404, detail="所选耗材资产不存在")

            base_data = {
                "date": dt,
                "type": "支出",
                "currency": req.currency,
                "amount": req.amount,
                "category": req.category,
                "shop": req.shop.strip(),
                "desc": req.desc.strip(),
                "url": req.url.strip(),
                "account_id": req.account_id,
                "is_non_cash": False,
            }
            link_config = {
                "link_type": "consumable",
                "is_new": False,
                "target_id": target_con.id,
                "name": target_con.name,
                "qty": req.replenish_qty,
                "unit_price": req.amount / req.replenish_qty if req.replenish_qty > 0 else 0.0,
                "product_id": None,
                "cat": target_con.category,
            }
            msg = FinanceService.create_general_transaction(db, base_data, link_config, rates_map)
        else:
            if req.amount <= 0:
                raise HTTPException(status_code=400, detail="录入金额必须大于 0")
            is_non_cash = req.category in FinanceService.NON_CASH_CATEGORIES
            if not is_non_cash and not req.account_id:
                raise HTTPException(status_code=400, detail="请选择关联现金账户")

            base_data = {
                "date": dt,
                "type": req.rec_type,
                "currency": req.currency,
                "amount": req.amount,
                "category": req.category,
                "shop": req.shop.strip(),
                "desc": req.desc.strip(),
                "url": req.url.strip(),
                "account_id": req.account_id if not is_non_cash else None,
                "is_non_cash": is_non_cash,
            }
            link_config = {
                "link_type": None,
                "is_new": False,
                "target_id": None,
                "name": "",
                "qty": 1.0,
                "unit_price": req.amount,
                "product_id": None,
                "cat": "",
            }
            msg = FinanceService.create_general_transaction(db, base_data, link_config, rates_map)

        sync_all_caches()
        return {"message": f"记账成功: {msg}"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"记账失败: {e}")


@router.post("/finance/batch-expense")
def create_batch_expense(
    req: BatchExpenseRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.items:
        raise HTTPException(status_code=400, detail="请至少添加一条物品明细")
    for idx, item in enumerate(req.items, start=1):
        if not item.name.strip():
            raise HTTPException(status_code=400, detail=f"第 {idx} 项物品名称不能为空")
        if item.amount < 0 or item.qty <= 0:
            raise HTTPException(status_code=400, detail=f"第 {idx} 项金额或数量无效")

    if req.category == "商品成本" and not req.product_id:
        raise HTTPException(status_code=400, detail="商品成本必须指定关联商品")

    rates_map = load_rates_map(db)
    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    try:
        if req.selected_budget_id:
            if len(req.items) != 1:
                raise HTTPException(status_code=400, detail="匹配特定预算项时，物品明细表内只能有一条物品记录")
            first_item = req.items[0]
            base_data = {
                "date": dt,
                "type": "支出",
                "currency": req.currency,
                "amount": first_item.amount,
                "category": req.category,
                "shop": req.shop.strip(),
                "desc": first_item.desc.strip(),
                "url": first_item.url.strip(),
                "account_id": req.account_id,
            }
            link_config = {
                "link_type": "cost",
                "target_cost_id": req.selected_budget_id,
                "name": first_item.name.strip(),
                "qty": first_item.qty,
                "unit_price": first_item.amount / first_item.qty if first_item.qty else 0.0,
                "product_id": req.product_id,
                "cat": req.cost_cat,
            }
            msg = FinanceService.create_general_transaction(db, base_data, link_config, rates_map)
        else:
            base_data = {
                "date": dt,
                "currency": req.currency,
                "account_id": req.account_id,
                "shop": req.shop.strip(),
                "category": req.category,
            }
            batch_config = {
                "product_id": req.product_id,
                "cost_cat": req.cost_cat,
                "asset_cat": req.asset_cat,
                "shipping_fee": req.shipping_fee,
            }
            items_data = [
                {
                    "name": it.name.strip(),
                    "amount": it.amount,
                    "qty": it.qty,
                    "desc": it.desc.strip(),
                    "url": it.url.strip(),
                }
                for it in req.items
            ]
            msg = FinanceService.create_batch_expense_transaction(
                db, base_data, batch_config, items_data, rates_map
            )
        sync_all_caches()
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"批量记账失败: {e}")


@router.post("/finance/pending-payment")
def create_pending_payment(
    req: PendingPaymentRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.shop.strip():
        raise HTTPException(status_code=400, detail="待付款必须填写店铺/债主名称")

    rates_map = load_rates_map(db)
    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    try:
        if req.category == "商品成本待付款":
            if not req.product_id:
                raise HTTPException(status_code=400, detail="请选择归属商品")
            if not req.items:
                raise HTTPException(status_code=400, detail="请至少添加一条待付款物品明细")
            items_data = [
                {
                    "name": it.name.strip(),
                    "amount": it.amount,
                    "qty": it.qty,
                    "remark": it.remark.strip(),
                    "url": it.url.strip(),
                }
                for it in req.items
            ]
            msg = FinanceService.create_pending_cost_payment(
                db,
                date_val=dt,
                currency=req.currency,
                shop=req.shop.strip(),
                product_id=req.product_id,
                cost_cat=req.cost_cat,
                items_data=items_data,
                shipping_fee=req.shipping_fee,
                rates_map=rates_map,
                selected_budget_id=req.selected_budget_id,
            )
        else:
            if req.amount <= 0:
                raise HTTPException(status_code=400, detail="待付款金额必须大于 0")
            msg = FinanceService.create_other_pending_payment(
                db,
                date_val=dt,
                currency=req.currency,
                shop=req.shop.strip(),
                amount=req.amount,
                desc=req.desc.strip(),
                url=req.url.strip(),
                rates_map=rates_map,
            )
        sync_all_caches()
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"挂账提交失败: {e}")


@router.post("/finance/exchange")
def create_exchange_transaction(
    req: ExchangeTransactionRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if req.out_account_id == req.in_account_id:
        raise HTTPException(status_code=400, detail="兑出账户和兑入账户不能相同")
    if req.out_amount <= 0 or req.in_amount <= 0:
        raise HTTPException(status_code=400, detail="兑出金额与兑入金额均须大于 0")

    rates_map = load_rates_map(db)
    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    try:
        FinanceService.create_exchange_transaction(
            db,
            date_val=dt,
            out_acc_id=req.out_account_id,
            out_amt=req.out_amount,
            in_acc_id=req.in_account_id,
            in_amt=req.in_amount,
            shop=req.shop.strip(),
            desc=req.desc.strip(),
            url=req.url.strip(),
            rates_map=rates_map,
        )
        sync_all_caches()
        return {"message": "货币兑换流水记录成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"货币兑换记录失败: {e}")


@router.post("/finance/debt/create")
def create_debt(
    req: DebtCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if not req.creditor.strip():
        raise HTTPException(status_code=400, detail="请填写债权人/客户名称")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="发生金额必须大于 0")

    is_cash_loan = "金钱借入" in req.debt_type
    if is_cash_loan and not req.account_id:
        raise HTTPException(status_code=400, detail="金钱借入必须选择实际收款账户")

    rates_map = load_rates_map(db)
    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    try:
        msg = FinanceService.create_debt_transaction(
            db,
            date_val=dt,
            currency=req.currency,
            amount=req.amount,
            creditor=req.creditor.strip(),
            desc=req.desc.strip(),
            url=req.url.strip(),
            is_cash_loan=is_cash_loan,
            in_acc_id=req.account_id if is_cash_loan else None,
            rates_map=rates_map,
        )
        sync_all_caches()
        return {"message": f"负债挂账成功: {msg}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"新增负债失败: {e}")


@router.post("/finance/debt/repay")
def repay_debt(
    req: DebtRepayRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="偿还金额必须大于 0")

    rates_map = load_rates_map(db)
    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    try:
        msg = FinanceService.repay_debt_transaction(
            db,
            date_val=dt,
            debt_id=req.debt_id,
            amount=req.amount,
            desc=req.desc.strip(),
            url=req.url.strip(),
            out_acc_id=req.account_id,
            rates_map=rates_map,
            overpay_product_id=req.overpay_product_id,
            overpay_cost_cat=req.overpay_cost_cat,
            overpay_item_name=req.overpay_item_name.strip(),
        )
        sync_all_caches()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"偿还债务失败: {e}")


@router.post("/finance/debt/offset")
def offset_debt(
    req: DebtOffsetRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if req.offset_cny_val <= 0:
        raise HTTPException(status_code=400, detail="核销折算人民币金额必须大于 0")

    rates_map = load_rates_map(db)
    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    try:
        msg = FinanceService.offset_debt_with_asset(
            db,
            date_val=dt,
            debt_id=req.debt_id,
            asset_id=req.asset_id,
            offset_cny_val=req.offset_cny_val,
            desc=req.desc.strip(),
            rates_map=rates_map,
        )
        sync_all_caches()
        return {"message": f"实物抵扣核销完成: {msg}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"抵扣债务失败: {e}")


@router.post("/finance/transfer")
def transfer_funds(
    req: FundTransferRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    if req.from_asset_id == req.to_asset_id:
        raise HTTPException(status_code=400, detail="转出和转入不能是同一个现金账户")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="资金划转金额必须大于 0")

    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    try:
        FinanceService.execute_fund_transfer(
            db,
            date_val=dt,
            from_asset_id=req.from_asset_id,
            to_asset_id=req.to_asset_id,
            amount=req.amount,
            desc=req.desc.strip(),
        )
        sync_all_caches()
        return {"message": f"内部资金划转成功：{req.amount:,.2f}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"资金划转失败: {e}")


@router.put("/finance/records/{rec_id}")
def edit_finance_record(
    rec_id: int,
    req: RecordUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        dt = date.fromisoformat(req.date)
    except Exception:
        dt = date.today()

    updates = {
        "date": dt,
        "type": req.type,
        "amount_abs": req.amount_abs,
        "category": req.category.strip(),
        "desc": req.desc.strip(),
        "url": req.url.strip(),
        "account_id": req.account_id,
    }
    try:
        ok = FinanceService.update_record(db, rec_id, updates)
        if not ok:
            raise HTTPException(status_code=404, detail="流水修改失败，记录不存在")
        sync_all_caches()
        return {"message": "流水修改保存成功"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"修改失败: {e}")


@router.delete("/finance/records/{rec_id}")
def delete_finance_record(
    rec_id: int,
    include_budget: bool = Query(False),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    try:
        msg = FinanceService.delete_record(db, rec_id, include_budget=include_budget)
        if msg is False:
            raise HTTPException(status_code=404, detail="删除失败，记录不存在")
        sync_all_caches()
        return {"message": f"删除流水成功，级联撤销: {msg}"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Balance Overview Endpoints ====================

@router.get("/balance/summary")
def get_balance_summary(
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    summary = BalanceService.get_financial_summary(db)

    def _sum_cny(curr_dict: dict) -> float:
        return sum(to_cny(amt, c, rates_map) for c, amt in curr_dict.items())

    def _compile_bd(curr_dict: dict) -> list[dict]:
        rows = []
        for c, amt in curr_dict.items():
            if abs(amt) > 0.001 or c in ["CNY", "JPY"]:
                rows.append({"currency": c, "amount_str": format_currency(amt, c)})
        return rows

    cash_dict = summary["cash"]
    fixed_dict = summary["fixed"]
    cons_dict = summary["consumable"]
    wip_cny = float(summary["wip"]["total_cny"] or 0.0)
    wip_list = summary["wip"]["list"]

    stock_dict: dict[str, float] = {}
    other_manual_dict: dict[str, float] = {}
    stock_details = []
    prod_map = {p.id: p.name for p in db.query(Product).all()}

    for ma in summary["manual_assets"]:
        c = ma.currency
        if getattr(ma, "product_id", None) is not None:
            stock_dict[c] = stock_dict.get(c, 0.0) + ma.amount
            p_name = prod_map.get(ma.product_id, ma.name)
            stock_details.append({
                "name": p_name,
                "currency": c,
                "amount": round(float(ma.amount or 0.0), 2),
                "cny_equiv": round(to_cny(ma.amount, c, rates_map), 2),
            })
        else:
            other_manual_dict[c] = other_manual_dict.get(c, 0.0) + ma.amount

    cash_total_cny = round(_sum_cny(cash_dict), 2)
    fixed_total_cny = round(_sum_cny(fixed_dict), 2)
    consumable_total_cny = round(_sum_cny(cons_dict), 2)
    stock_total_cny = round(_sum_cny(stock_dict), 2)
    other_manual_cny = round(_sum_cny(other_manual_dict), 2)
    total_assets_cny = round(
        cash_total_cny + fixed_total_cny + consumable_total_cny + wip_cny + stock_total_cny + other_manual_cny,
        2,
    )

    liab_dict: dict[str, float] = {}
    liab_rows = []
    for item in summary["liabilities"]:
        c = item.currency
        liab_dict[c] = liab_dict.get(c, 0.0) + item.amount
        cny_eq = to_cny(item.amount, c, rates_map)
        liab_rows.append({
            "id": item.id,
            "name": item.name,
            "category": "liability",
            "asset_type": item.asset_type or "",
            "currency": c,
            "amount": round(float(item.amount or 0.0), 2),
            "cny_equiv": round(cny_eq, 2),
            "description": getattr(item, "description", "") or "",
        })
    liab_total_cny = round(_sum_cny(liab_dict), 2)

    eq_dict: dict[str, float] = {}
    eq_rows = []
    for item in summary["equities"]:
        c = item.currency
        eq_dict[c] = eq_dict.get(c, 0.0) + item.amount
        cny_eq = to_cny(item.amount, c, rates_map)
        eq_rows.append({
            "id": item.id,
            "name": item.name,
            "category": "equity",
            "asset_type": item.asset_type or "",
            "currency": c,
            "amount": round(float(item.amount or 0.0), 2),
            "cny_equiv": round(cny_eq, 2),
            "description": getattr(item, "description", "") or "",
        })
    eq_total_cny = round(_sum_cny(eq_dict), 2)

    asset_rows = []
    for acc in summary.get("cash_items", []):
        if abs(acc.amount or 0.0) < 0.01:
            continue
        c = acc.currency
        cny_eq = to_cny(acc.amount, c, rates_map)
        asset_rows.append({
            "id": acc.id,
            "name": acc.name,
            "category": "asset",
            "asset_type": "现金账户",
            "currency": c,
            "amount": round(float(acc.amount or 0.0), 2),
            "cny_equiv": round(cny_eq, 2),
            "description": getattr(acc, "description", "") or "资金账户",
        })
    for c, f_amt in fixed_dict.items():
        if f_amt > 0:
            asset_rows.append({
                "id": -1,
                "name": f"固定设备及模具汇总 ({c})",
                "category": "asset",
                "asset_type": "固定资产",
                "currency": c,
                "amount": round(float(f_amt), 2),
                "cny_equiv": round(to_cny(f_amt, c, rates_map), 2),
                "description": "根据固定资产库实时汇总",
            })
    for c, c_amt in cons_dict.items():
        if c_amt > 0:
            asset_rows.append({
                "id": -2,
                "name": f"消耗品及包装材料库存 ({c})",
                "category": "asset",
                "asset_type": "消耗品/物料",
                "currency": c,
                "amount": round(float(c_amt), 2),
                "cny_equiv": round(to_cny(c_amt, c, rates_map), 2),
                "description": "根据耗材管理库实时汇总",
            })
    for p_name, w_val in wip_list:
        if w_val > 0:
            asset_rows.append({
                "id": -3,
                "name": f"在研在制品投入 - {p_name}",
                "category": "asset",
                "asset_type": "在制品资产(WIP)",
                "currency": "CNY",
                "amount": round(float(w_val), 2),
                "cny_equiv": round(float(w_val), 2),
                "description": "商品成本已支出但尚未转化为完成品大货",
            })
    for ma in summary["manual_assets"]:
        c = ma.currency
        a_type = "大货商品库存" if getattr(ma, "product_id", None) is not None else (ma.asset_type or "其他资产")
        asset_rows.append({
            "id": ma.id,
            "name": ma.name,
            "category": "asset",
            "asset_type": a_type,
            "currency": c,
            "amount": round(float(ma.amount or 0.0), 2),
            "cny_equiv": round(to_cny(ma.amount, c, rates_map), 2),
            "description": getattr(ma, "description", "") or "",
        })

    return {
        "total_assets_cny": total_assets_cny,
        "net_assets_cny": round(total_assets_cny - liab_total_cny, 2),
        "cash_total_cny": cash_total_cny,
        "cash_breakdown": _compile_bd(cash_dict),
        "fixed_total_cny": fixed_total_cny,
        "fixed_breakdown": _compile_bd(fixed_dict),
        "consumable_total_cny": consumable_total_cny,
        "consumable_breakdown": _compile_bd(cons_dict),
        "wip_total_cny": round(wip_cny, 2),
        "wip_details": [{"name": n, "cny_equiv": round(float(v), 2)} for n, v in wip_list if v > 0],
        "stock_total_cny": stock_total_cny,
        "stock_breakdown": _compile_bd(stock_dict),
        "stock_details": stock_details,
        "other_manual_cny": other_manual_cny,
        "other_manual_breakdown": _compile_bd(other_manual_dict),
        "liabilities_total_cny": liab_total_cny,
        "liabilities_breakdown": _compile_bd(liab_dict),
        "equities_total_cny": eq_total_cny,
        "equities_breakdown": _compile_bd(eq_dict),
        "asset_rows": asset_rows,
        "liability_rows": liab_rows,
        "equity_rows": eq_rows,
        "currencies": ["CNY"] + [k for k in rates_map.keys() if k != "CNY"],
    }


@router.post("/balance/cash-account")
def create_cash_account(
    req: CashAccountCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="账户名称不能为空")
    try:
        acc, err = BalanceService.add_cash_account(db, name, req.currency.strip().upper())
        if err:
            raise HTTPException(status_code=400, detail=err)
        if req.initial_amount and req.initial_amount != 0:
            acc.amount = req.initial_amount
            db.commit()
        sync_all_caches()
        return {"message": f"成功添加账户: {name} ({req.currency})"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Financial Reports Endpoints ====================

@router.get("/report/calculate")
def calculate_financial_report(
    report_type: str = Query("month"),  # "month" or "year"
    selected_month: str = Query(""),    # e.g. "2026-05"
    selected_year: str = Query(""),     # e.g. "2026"
    is_test: bool = Depends(is_test_mode_header),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    ex_rate = rates_map.get("JPY", 0.048)
    today = date.today()

    active_type = "year" if ("year" in report_type.lower() or "年" in report_type) else "month"
    records = db.query(FinanceRecord.date).all()
    if records:
        months = sorted(list({r[0].strftime("%Y-%m") for r in records if r[0]}), reverse=True)
        years = sorted(list({str(r[0].year) for r in records if r[0]}), reverse=True)
    else:
        months = [today.strftime("%Y-%m")]
        years = [str(today.year)]

    sel_m = selected_month if (selected_month and selected_month in months) else months[0]
    sel_y = selected_year if (selected_year and selected_year in years) else years[0]

    from yurara_app.state.report_state import _sync_recalculate_report
    raw = _sync_recalculate_report(
        is_test=is_test,
        exchange_rate=ex_rate,
        rates_map=rates_map,
        active_report_type=active_type,
        selected_month=sel_m,
        selected_year=sel_y,
    )

    def _dump_list(lst):
        return [
            x.model_dump() if hasattr(x, "model_dump") else (x.dict() if hasattr(x, "dict") else x)
            for x in (lst or [])
        ]

    return {
        "active_report_type": active_type,
        "selected_month": sel_m,
        "selected_year": sel_y,
        "available_months": raw.get("available_months", months),
        "available_years": raw.get("available_years", years),
        "past_cash_total": round(float(raw.get("past_cash_total", 0.0)), 2),
        "net_cash_total": round(float(raw.get("net_cash_total", 0.0)), 2),
        "closing_cash_total": round(float(raw.get("closing_cash_total", 0.0)), 2),
        "month_asset_add": round(float(raw.get("month_asset_add", 0.0)), 2),
        "month_asset_sub": round(float(raw.get("month_asset_sub", 0.0)), 2),
        "net_asset_change": round(float(raw.get("net_asset_change", 0.0)), 2),
        "profit_in": round(float(raw.get("profit_in", 0.0)), 2),
        "profit_out": round(float(raw.get("profit_out", 0.0)), 2),
        "net_profit": round(float(raw.get("net_profit", 0.0)), 2),
        "wip_cny": round(float(raw.get("wip_cny", 0.0)), 2),
        "stock_cny": round(float(raw.get("stock_cny", 0.0)), 2),
        "acc_summary": _dump_list(raw.get("acc_summary")),
        "asset_purchase_rows": _dump_list(raw.get("asset_purchase_rows")),
        "liab_equity_rows": _dump_list(raw.get("liab_equity_rows")),
        "flow_summary": _dump_list(raw.get("flow_summary")),
        "trend_rows": _dump_list(raw.get("trend_rows")),
        "balance_change_summary": _dump_list(raw.get("balance_change_summary")),
        "non_cash_asset_summary": _dump_list(raw.get("non_cash_asset_summary")),
    }
