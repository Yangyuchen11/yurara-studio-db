"""
System, Auth, Exchange Rates, Memos, Test Sandbox, and Data Backup/Restore Routes.
"""
import io
import zipfile
import datetime
import re
import urllib.request
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import pandas as pd

from api.deps import (
    verify_auth_token,
    get_db_session,
    is_test_mode_header,
    load_rates_map,
    get_allowed_users,
    _generate_token,
    get_cached_engine,
)
from models import (
    Base, SystemSetting,
    Warehouse, Product, ProductColor, ProductPart, ProductPrice,
    FinanceRecord, CostItem, InventoryLog, FixedAsset, FixedAssetLog,
    ConsumableItem, ConsumableLog, CompanyBalanceItem,
    SalesOrder, SalesOrderItem, OrderRefund,
    OfflineTemplate, OfflineTemplateItem,
    ConsignmentItem, PresaleOrderBinding, SalesPlatform, MemoNote, ScheduleNode,
)
from database import engine as prod_engine
from services import memo_service
from cache_manager import sync_all_caches

TABLES_MAP = [
    ("warehouses.csv", "warehouses", Warehouse),
    ("products.csv", "products", Product),
    ("product_colors.csv", "product_colors", ProductColor),
    ("product_parts.csv", "product_parts", ProductPart),
    ("product_prices.csv", "product_prices", ProductPrice),
    ("finance_records.csv", "finance_records", FinanceRecord),
    ("cost_items.csv", "cost_items", CostItem),
    ("inventory_logs.csv", "inventory_logs", InventoryLog),
    ("fixed_assets.csv", "fixed_assets_detail", FixedAsset),
    ("fixed_asset_logs.csv", "fixed_asset_logs", FixedAssetLog),
    ("consumables.csv", "consumable_items", ConsumableItem),
    ("consumable_logs.csv", "consumable_logs", ConsumableLog),
    ("company_balance.csv", "company_balance_items", CompanyBalanceItem),
    ("sales_orders.csv", "sales_orders", SalesOrder),
    ("sales_order_items.csv", "sales_order_items", SalesOrderItem),
    ("order_refunds.csv", "order_refunds", OrderRefund),
    ("presale_order_bindings.csv", "presale_order_bindings", PresaleOrderBinding),
    ("offline_templates.csv", "offline_templates", OfflineTemplate),
    ("offline_template_items.csv", "offline_template_items", OfflineTemplateItem),
    ("sales_platforms.csv", "sales_platforms", SalesPlatform),
    ("memo_notes.csv", "memo_notes", MemoNote),
    ("schedule_nodes.csv", "schedule_nodes", ScheduleNode),
    ("consignments.csv", "consignment_items", ConsignmentItem),
    ("system_settings.csv", "system_settings", SystemSetting),
]

COMMON_CURRENCIES = ["CNY", "JPY", "USD", "EUR", "HKD", "GBP", "KRW", "AUD", "CAD", "SGD"]

router = APIRouter(tags=["System & Global"])


# ==================== Schemas ====================

class LoginRequest(BaseModel):
    username: str
    password: str


class RateUpdateRequest(BaseModel):
    currency: str
    rate_per_100: float


class ClearDataRequest(BaseModel):
    confirm_code: str


class MemoCreateRequest(BaseModel):
    date: str = ""
    content: str = ""
    title: str = ""


class MemoUpdateRequest(BaseModel):
    date: str = ""
    content: str = ""
    title: str = ""


# ==================== Auth ====================

@router.post("/auth/login")
def login(req: LoginRequest):
    uname = req.username.strip()
    pwd = req.password.strip()
    if not uname or not pwd:
        raise HTTPException(status_code=400, detail="请输入账号和密码")

    allowed = get_allowed_users()
    if uname in allowed and allowed[uname] == pwd:
        token = _generate_token(uname, pwd)
        return {
            "token": token,
            "username": uname,
            "message": f"欢迎回来，{uname}！"
        }
    raise HTTPException(status_code=401, detail="账号或密码错误，请重试")


@router.get("/auth/me")
def get_me(username: str = Depends(verify_auth_token)):
    return {"username": username, "authenticated": True}


# ==================== System Init & Exchange Rates ====================

def _build_sorted_rates(rates_map: Dict[str, float]) -> List[Dict[str, Any]]:
    res = []
    for k, v in rates_map.items():
        if k != "CNY":
            res.append({"currency": k, "rate_100": round(v * 100, 4), "rate_1": round(v, 6)})
    return sorted(res, key=lambda x: x["currency"])


@router.get("/system/init")
def get_system_init(
    is_test: bool = Depends(is_test_mode_header),
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    sorted_rates = _build_sorted_rates(rates_map)

    extra = [k for k in rates_map.keys() if k not in COMMON_CURRENCIES]
    all_currencies = COMMON_CURRENCIES + sorted(extra)

    # Latest memo preview
    memos = memo_service.get_all_memos(db)
    latest_memo_preview = "点击打开备忘录"
    if memos:
        latest = memos[0]
        content_clean = (latest.content or "").replace("\n", " ").strip()
        preview_text = f"[{latest.date}] {content_clean}" if latest.date else content_clean
        if len(preview_text) > 22:
            preview_text = preview_text[:22] + "..."
        latest_memo_preview = preview_text or "点击查看备忘录"

    return {
        "username": username,
        "is_test_mode": is_test,
        "rates_map": rates_map,
        "sorted_rates": sorted_rates,
        "all_currencies": all_currencies,
        "latest_memo_preview": latest_memo_preview,
        "memo_count": len(memos),
    }


@router.get("/system/rates")
def get_exchange_rates(
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    extra = [k for k in rates_map.keys() if k not in COMMON_CURRENCIES]
    return {
        "rates_map": rates_map,
        "sorted_rates": _build_sorted_rates(rates_map),
        "all_currencies": COMMON_CURRENCIES + sorted(extra),
    }


@router.post("/system/rates")
def upsert_exchange_rate(
    req: RateUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    curr = req.currency.strip().upper()
    if not curr or curr == "CNY":
        raise HTTPException(status_code=400, detail="不能配置 CNY 或空币种代码")
    if req.rate_per_100 <= 0:
        raise HTTPException(status_code=400, detail="汇率必须大于 0")

    key = f"rate_CNY_per_{curr}_100"
    record = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if record:
        record.value = str(round(req.rate_per_100, 4))
    else:
        db.add(SystemSetting(
            key=key,
            value=str(round(req.rate_per_100, 4)),
            description=f"100 {curr} 兑换人民币汇率"
        ))
    if curr == "JPY":
        old_rec = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate").first()
        if old_rec:
            old_rec.value = str(round(req.rate_per_100 / 100.0, 6))

    db.commit()
    sync_all_caches()
    rates_map = load_rates_map(db)
    return {
        "message": f"已保存 {curr} 汇率: {req.rate_per_100:.4f} CNY / 100 {curr}",
        "rates_map": rates_map,
        "sorted_rates": _build_sorted_rates(rates_map),
    }


@router.delete("/system/rates/{currency}")
def delete_exchange_rate(
    currency: str,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    curr = currency.strip().upper()
    if curr in ("CNY", "JPY"):
        raise HTTPException(status_code=400, detail="基础币种不可移除")
    key = f"rate_CNY_per_{curr}_100"
    rec = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if rec:
        db.delete(rec)
        db.commit()
    sync_all_caches()
    rates_map = load_rates_map(db)
    return {
        "message": f"已移除币种 {curr}",
        "rates_map": rates_map,
        "sorted_rates": _build_sorted_rates(rates_map),
    }


@router.post("/system/rates/sync")
def sync_live_exchange_rates(
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    rates_map = load_rates_map(db)
    currencies = [k for k in rates_map.keys() if k != "CNY"]
    if not currencies:
        currencies = ["JPY"]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    updated = []
    failed = []

    for curr in currencies:
        url = f"https://www.google.com/finance/quote/{curr}-CNY"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r'data-last-price="([0-9.]+)"', html)
            if not m:
                m = re.search(r'class="YMlKec fxKbKc">([0-9.,]+)<', html)
            if m:
                price_1 = float(m.group(1).replace(",", ""))
                if price_1 > 0:
                    rate_100 = round(price_1 * 100.0, 4)
                    key = f"rate_CNY_per_{curr}_100"
                    rec = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                    if rec:
                        rec.value = str(rate_100)
                    else:
                        db.add(SystemSetting(key=key, value=str(rate_100), description=f"100 {curr} 兑换人民币汇率"))
                    if curr == "JPY":
                        old_rec = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate").first()
                        if old_rec:
                            old_rec.value = str(round(price_1, 6))
                    updated.append(f"{curr}: {rate_100}")
                else:
                    failed.append(curr)
            else:
                failed.append(curr)
        except Exception:
            failed.append(curr)

    db.commit()
    sync_all_caches()
    new_rates_map = load_rates_map(db)
    msg = f"成功同步汇率: {', '.join(updated)}" if updated else "未能从 Google 财经获取最新汇率"
    if failed:
        msg += f" (失败: {', '.join(failed)})"
    return {
        "message": msg,
        "updated": updated,
        "failed": failed,
        "rates_map": new_rates_map,
        "sorted_rates": _build_sorted_rates(new_rates_map),
    }


# ==================== Test Mode Sandbox Cloning ====================

@router.post("/system/test-mode/init")
def init_test_sandbox(username: str = Depends(verify_auth_token)):
    """Clones all production database tables into sqlite:///yurara_test_env.db."""
    try:
        test_engine = get_cached_engine(True)
        Base.metadata.drop_all(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        with prod_engine.connect() as prod_conn:
            with test_engine.begin() as test_conn:
                for table in Base.metadata.sorted_tables:
                    rows = prod_conn.execute(table.select()).fetchall()
                    if rows:
                        data = [dict(row._mapping) for row in rows]
                        test_conn.execute(table.insert(), data)
        return {"message": "已成功从正式数据库克隆最新镜像至测试沙盒环境！"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化测试环境失败: {e}")


# ==================== Data Backup / Restore / Clear ====================

@router.get("/system/backup")
def download_backup_zip(
    is_test: bool = Depends(is_test_mode_header),
    username: str = Depends(verify_auth_token),
):
    target_engine = get_cached_engine(is_test)
    zip_buffer = io.BytesIO()
    with target_engine.connect() as conn:
        with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_name, table_name, model in TABLES_MAP:
                try:
                    df = pd.read_sql_table(table_name, conn)
                    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
                    zf.writestr(file_name, csv_bytes)
                except Exception as e:
                    zf.writestr(f"{table_name}_error.txt", str(e))

    zip_buffer.seek(0)
    ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    prefix = "yurara_test_backup" if is_test else "yurara_backup"
    filename = f"{prefix}_{ts_str}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/system/restore")
async def restore_from_backup_zip(
    file: UploadFile = File(...),
    is_test: bool = Depends(is_test_mode_header),
    username: str = Depends(verify_auth_token),
):
    content = await file.read()
    target_engine = get_cached_engine(is_test)
    db = Session(bind=target_engine)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            file_list = zf.namelist()
            for table in reversed(Base.metadata.sorted_tables):
                db.execute(table.delete())
            db.commit()

            restored_tables = 0
            for file_name, table_name, model in TABLES_MAP:
                if file_name in file_list:
                    with zf.open(file_name) as f:
                        df = pd.read_csv(f)
                    if not df.empty:
                        df = df.where(pd.notnull(df), None)
                        records = df.to_dict(orient="records")
                        for col in model.__table__.columns:
                            col_name = col.name
                            col_type = str(col.type).upper()
                            if "DATETIME" in col_type or "TIMESTAMP" in col_type:
                                for r in records:
                                    val = r.get(col_name)
                                    if val is not None and isinstance(val, str):
                                        try:
                                            r[col_name] = pd.to_datetime(val).to_pydatetime()
                                        except Exception:
                                            r[col_name] = None
                            elif "DATE" in col_type:
                                for r in records:
                                    val = r.get(col_name)
                                    if val is not None and isinstance(val, str):
                                        try:
                                            r[col_name] = pd.to_datetime(val).date()
                                        except Exception:
                                            r[col_name] = None
                        db.execute(model.__table__.insert(), records)
                        restored_tables += 1
            db.commit()
        sync_all_caches()
        return {"message": f"数据还原成功！已恢复 {restored_tables} 张数据表。"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"备份恢复失败: {e}")
    finally:
        db.close()


@router.post("/system/clear-data")
def clear_all_data(
    req: ClearDataRequest,
    is_test: bool = Depends(is_test_mode_header),
    username: str = Depends(verify_auth_token),
):
    if req.confirm_code.strip() != "DELETE":
        raise HTTPException(status_code=400, detail="安全校验码错误，必须输入大写的 DELETE")

    target_engine = get_cached_engine(is_test)
    db = Session(bind=target_engine)
    try:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "system_settings":
                db.execute(table.delete())
        db.commit()
        sync_all_caches()
        env_label = "测试环境" if is_test else "正式环境"
        return {"message": f"已清空【{env_label}】所有业务表数据（保留系统汇率设置）。"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"清空数据失败: {e}")
    finally:
        db.close()


# ==================== Memos ====================

def _serialize_memo(m) -> Dict[str, Any]:
    d_str = m.date or ""
    c_str = m.content or ""
    first_line = c_str.strip().split("\n")[0] if c_str.strip() else ""
    return {
        "id": m.id,
        "date": d_str,
        "content": c_str,
        "created_at": m.created_at or "",
        "title": d_str or first_line or "备忘录",
        "created_by": "Admin",
        "updated_at": m.created_at or "",
    }


@router.get("/memos")
def list_memos(
    search: str = "",
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    memos = memo_service.get_all_memos(db)
    kw = search.strip().lower()
    items = []
    for m in memos:
        if kw and kw not in (m.date or "").lower() and kw not in (m.content or "").lower():
            continue
        items.append(_serialize_memo(m))
    return {"items": items, "memos": items, "total": len(items)}


@router.post("/memos")
def create_memo(
    req: MemoCreateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    date_str = req.date.strip()
    if not date_str and req.title.strip():
        date_str = req.title.strip()
    if not date_str:
        date_str = datetime.date.today().strftime("%Y-%m-%d")
    m = memo_service.create_memo(db, date_str=date_str, content=req.content)
    serialized = _serialize_memo(m)
    return {"message": "备忘录已添加", "item": serialized, "memo": serialized}


@router.put("/memos/{memo_id}")
def update_memo(
    memo_id: int,
    req: MemoUpdateRequest,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    date_str = req.date.strip()
    if not date_str and req.title.strip():
        date_str = req.title.strip()
    if not date_str:
        date_str = datetime.date.today().strftime("%Y-%m-%d")
    m = memo_service.update_memo(db, memo_id=memo_id, date_str=date_str, content=req.content)
    if not m:
        raise HTTPException(status_code=404, detail="备忘录不存在")
    serialized = _serialize_memo(m)
    return {"message": "备忘录已保存", "item": serialized, "memo": serialized}


@router.delete("/memos/{memo_id}")
def delete_memo(
    memo_id: int,
    username: str = Depends(verify_auth_token),
    db: Session = Depends(get_db_session),
):
    ok = memo_service.delete_memo(db, memo_id)
    if not ok:
        raise HTTPException(status_code=404, detail="备忘录不存在")
    return {"message": "备忘录已删除"}
