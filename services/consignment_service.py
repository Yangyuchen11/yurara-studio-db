# services/consignment_service.py
from datetime import date, datetime
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from models import (
    ConsignmentShop,
    ConsignmentItem,
    ConsignmentSettlement,
    ConsignmentSettlementItem,
    ConsignmentReturn,
    CompanyBalanceItem,
    FinanceRecord,
    InventoryLog,
    Product,
    SalesOrder,
    SalesOrderItem,
    Warehouse,
)
from constants import (
    BalanceCategory,
    Currency,
    FinanceCategory,
    OrderStatus,
    StockLogReason,
)
from services.inventory_service import InventoryService


def _recompute_item_status(item: ConsignmentItem) -> str:
    rem = max(0, int(item.remaining_qty or 0))
    sold = max(0, int(item.sold_qty or 0))
    ret = max(0, int(item.returned_qty or 0))
    if rem <= 0:
        return "已结清"
    if sold > 0 or ret > 0:
        return "部分结算"
    return "寄售中"


class ConsignmentService:
    """寄售管理核心业务服务：寄售店铺档案、仓库出库调拨、退回仓库、单条/批量结算与财务入账。"""

    def __init__(self, db: Session):
        self.db = db

    # ================= 1. 寄售店铺管理 =================

    def get_all_shops(self) -> list[ConsignmentShop]:
        return self.db.query(ConsignmentShop).order_by(ConsignmentShop.id.asc()).all()

    def get_shop_summaries(self) -> list[dict]:
        shops = self.get_all_shops()
        items = self.db.query(ConsignmentItem).all()
        settlements = self.db.query(ConsignmentSettlement).all()

        result = []
        for s in shops:
            s_items = [i for i in items if (i.shop_id == s.id) or (i.shop_id is None and i.shop_name == s.name)]
            s_setts = [st for st in settlements if (st.shop_id == s.id) or (st.shop_id is None and st.shop_name == s.name)]
            result.append({
                "id": s.id,
                "name": s.name,
                "currency": s.currency or Currency.CNY,
                "default_fee_rate": float(s.default_fee_rate or 0.0),
                "default_fee_fixed": float(s.default_fee_fixed or 0.0),
                "default_account_name": s.default_account_name or "",
                "contact_info": s.contact_info or "",
                "remarks": s.remarks or "",
                "batch_count": len(s_items),
                "total_sent_qty": sum(int(i.quantity or 0) for i in s_items),
                "remaining_qty": sum(int(i.remaining_qty or 0) for i in s_items),
                "sold_qty": sum(int(i.sold_qty or 0) for i in s_items),
                "returned_qty": sum(int(i.returned_qty or 0) for i in s_items),
                "settlement_count": len(s_setts),
                "settled_net_total": round(sum(float(st.net_amount or 0.0) for st in s_setts), 2),
            })
        return result

    def create_shop(
        self,
        name: str,
        currency: str = "CNY",
        default_fee_rate: float = 0.0,
        default_fee_fixed: float = 0.0,
        default_account_name: str = "",
        contact_info: str = "",
        remarks: str = "",
    ) -> ConsignmentShop:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("寄售店铺名称不能为空")
        exist = self.db.query(ConsignmentShop).filter(ConsignmentShop.name == clean_name).first()
        if exist:
            raise ValueError(f"寄售店铺【{clean_name}】已存在")
        if default_fee_rate < 0 or default_fee_rate > 1:
            raise ValueError("抽成手续费率应在 0% ~ 100% 之间")

        shop = ConsignmentShop(
            name=clean_name,
            currency=(currency or "CNY").strip().upper(),
            default_fee_rate=float(default_fee_rate or 0.0),
            default_fee_fixed=float(default_fee_fixed or 0.0),
            default_account_name=(default_account_name or "").strip() or None,
            contact_info=(contact_info or "").strip(),
            remarks=(remarks or "").strip(),
        )
        self.db.add(shop)
        self.db.flush()
        return shop

    def update_shop(
        self,
        shop_id: int,
        name: str,
        currency: str = "CNY",
        default_fee_rate: float = 0.0,
        default_fee_fixed: float = 0.0,
        default_account_name: str = "",
        contact_info: str = "",
        remarks: str = "",
    ) -> ConsignmentShop:
        shop = self.db.query(ConsignmentShop).filter(ConsignmentShop.id == shop_id).first()
        if not shop:
            raise ValueError("寄售店铺不存在")
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("寄售店铺名称不能为空")
        dup = self.db.query(ConsignmentShop).filter(
            ConsignmentShop.name == clean_name, ConsignmentShop.id != shop_id
        ).first()
        if dup:
            raise ValueError(f"寄售店铺名称【{clean_name}】已被其他店铺使用")
        if default_fee_rate < 0 or default_fee_rate > 1:
            raise ValueError("抽成手续费率应在 0% ~ 100% 之间")

        old_name = shop.name
        shop.name = clean_name
        shop.currency = (currency or "CNY").strip().upper()
        shop.default_fee_rate = float(default_fee_rate or 0.0)
        shop.default_fee_fixed = float(default_fee_fixed or 0.0)
        shop.default_account_name = (default_account_name or "").strip() or None
        shop.contact_info = (contact_info or "").strip()
        shop.remarks = (remarks or "").strip()

        if old_name != clean_name:
            self.db.query(ConsignmentItem).filter(ConsignmentItem.shop_id == shop.id).update(
                {"shop_name": clean_name}
            )
            self.db.query(ConsignmentSettlement).filter(ConsignmentSettlement.shop_id == shop.id).update(
                {"shop_name": clean_name}
            )
        self.db.flush()
        return shop

    def delete_shop(self, shop_id: int):
        shop = self.db.query(ConsignmentShop).filter(ConsignmentShop.id == shop_id).first()
        if not shop:
            raise ValueError("寄售店铺不存在")
        item_cnt = self.db.query(ConsignmentItem).filter(ConsignmentItem.shop_id == shop_id).count()
        sett_cnt = self.db.query(ConsignmentSettlement).filter(ConsignmentSettlement.shop_id == shop_id).count()
        if item_cnt > 0 or sett_cnt > 0:
            raise ValueError(
                f"无法删除店铺【{shop.name}】：仍有关联寄售库存({item_cnt}条)或结算单({sett_cnt}笔)"
            )
        self.db.delete(shop)
        self.db.flush()

    def get_or_create_shop(self, shop_name: str, currency: str = "CNY") -> ConsignmentShop:
        clean_name = (shop_name or "").strip() or "默认寄售店"
        shop = self.db.query(ConsignmentShop).filter(ConsignmentShop.name == clean_name).first()
        if not shop:
            shop = ConsignmentShop(name=clean_name, currency=(currency or "CNY").strip().upper())
            self.db.add(shop)
            self.db.flush()
        return shop

    # ================= 2. 寄售库存台账查询、调拨与手动补录 =================

    def get_all_consignments(
        self,
        shop_id: Optional[int] = None,
        product_name: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[ConsignmentItem]:
        query = self.db.query(ConsignmentItem).options(
            joinedload(ConsignmentItem.shop),
            joinedload(ConsignmentItem.warehouse),
        )
        if shop_id is not None:
            query = query.filter(ConsignmentItem.shop_id == shop_id)
        if product_name:
            query = query.filter(ConsignmentItem.product_name == product_name)
        if status:
            query = query.filter(ConsignmentItem.status == status)
        items = query.order_by(ConsignmentItem.date.desc(), ConsignmentItem.id.desc()).all()

        if search and search.strip():
            q = search.strip().lower()
            items = [
                c for c in items
                if q in (c.shop_name or "").lower()
                or q in (c.product_name or "").lower()
                or q in (c.variant or "").lower()
                or q in (c.part_name or "").lower()
                or q in (c.remarks or "").lower()
                or (c.date and q in c.date.strftime("%Y-%m-%d").lower())
            ]
        return items

    def dispatch_from_warehouse(
        self,
        shop_id: Optional[int],
        shop_name: str,
        warehouse_id: Optional[int],
        product_name: str,
        entries: list[dict],
        dispatch_date: Optional[date] = None,
        remarks: str = "",
    ) -> str:
        """从物理仓库出库调拨至寄售店"""
        target_shop = None
        if shop_id:
            target_shop = self.db.query(ConsignmentShop).filter(ConsignmentShop.id == shop_id).first()
        if not target_shop:
            if not shop_name or not shop_name.strip():
                raise ValueError("请选择或填写寄售店铺")
            target_shop = self.get_or_create_shop(shop_name.strip())

        prod = self.db.query(Product).filter(Product.name == product_name).first()
        if not prod:
            raise ValueError(f"商品【{product_name}】不存在")

        valid_entries = [e for e in (entries or []) if int(e.get("quantity", 0) or 0) > 0]
        if not valid_entries:
            raise ValueError("请至少填写一条大于 0 的出库数量")

        d_obj = dispatch_date or date.today()
        inv_service = InventoryService(self.db)
        msg = inv_service.add_batch_inventory_movements(
            product_id=prod.id,
            product_name=prod.name,
            entries=valid_entries,
            move_type=StockLogReason.OUT_STOCK,
            date_obj=d_obj,
            batch_remark=remarks.strip(),
            warehouse_id=warehouse_id,
            out_type="寄售",
            consignment_shop=target_shop.name,
        )
        self.db.flush()
        return msg

    def add_manual_consignment(
        self,
        shop_name: str,
        product_name: str,
        variant: str,
        quantity: int,
        remaining_qty: Optional[int] = None,
        unit_price: float = 0.0,
        currency: Optional[str] = None,
        part_name: Optional[str] = None,
        warehouse_id: Optional[int] = None,
        remarks: str = "",
        date_obj: Optional[date] = None,
        shop_id: Optional[int] = None,
    ) -> ConsignmentItem:
        if not product_name or not product_name.strip():
            raise ValueError("商品名称不能为空")
        if quantity <= 0:
            raise ValueError("寄售数量必须大于 0")

        shop_obj = None
        if shop_id:
            shop_obj = self.db.query(ConsignmentShop).filter(ConsignmentShop.id == shop_id).first()
        if not shop_obj:
            if not shop_name or not shop_name.strip():
                raise ValueError("寄售店铺名称不能为空")
            shop_obj = self.get_or_create_shop(shop_name.strip(), currency or Currency.CNY)

        rem_val = max(0, int(quantity if remaining_qty is None else remaining_qty))
        if rem_val > int(quantity):
            raise ValueError("剩余数量不能大于初始寄售数量")
        sold_val = max(0, int(quantity) - rem_val)

        used_currency = (currency or shop_obj.currency or Currency.CNY).strip().upper()
        used_price = float(unit_price or 0.0)
        if used_price <= 0:
            prod = self.db.query(Product).filter(Product.name == product_name.strip()).first()
            if prod:
                c = next((col for col in prod.colors if col.color_name == (variant or "").strip()), None)
                if c and c.prices:
                    pr = next((p.price for p in c.prices if (p.currency or "").upper() == used_currency and (p.price or 0) > 0), None)
                    if pr is not None:
                        used_price = float(pr)

        item = ConsignmentItem(
            shop_id=shop_obj.id,
            shop_name=shop_obj.name,
            warehouse_id=warehouse_id,
            product_name=product_name.strip(),
            variant=variant.strip() if variant else "通用",
            part_name=part_name if (part_name and part_name != "整套") else None,
            quantity=int(quantity),
            sold_qty=sold_val,
            returned_qty=0,
            remaining_qty=rem_val,
            unit_price=used_price,
            currency=used_currency,
            status="已结清" if rem_val <= 0 else ("部分结算" if sold_val > 0 else "寄售中"),
            remarks=(remarks or "").strip(),
            date=date_obj or date.today(),
        )
        self.db.add(item)
        self.db.flush()
        return item

    def update_consignment_item(
        self,
        item_id: int,
        remaining_qty: Optional[int] = None,
        remarks: Optional[str] = None,
        shop_name: Optional[str] = None,
        unit_price: Optional[float] = None,
    ) -> ConsignmentItem:
        item = self.db.query(ConsignmentItem).filter(ConsignmentItem.id == item_id).first()
        if not item:
            raise ValueError(f"未找到 ID 为 {item_id} 的寄售记录")
        if remaining_qty is not None:
            new_rem = max(0, int(remaining_qty))
            max_allowed = max(0, int(item.quantity or 0) - int(item.returned_qty or 0))
            if new_rem > max_allowed:
                raise ValueError(f"剩余数量不能超过可用上限 {max_allowed}")
            item.remaining_qty = new_rem
        if remarks is not None:
            item.remarks = str(remarks).strip()
        if unit_price is not None:
            item.unit_price = max(0.0, float(unit_price))
        if shop_name is not None and shop_name.strip():
            shop_obj = self.get_or_create_shop(shop_name.strip(), item.currency or Currency.CNY)
            item.shop_id = shop_obj.id
            item.shop_name = shop_obj.name
        item.status = _recompute_item_status(item)
        self.db.flush()
        return item

    def delete_consignment_item(self, item_id: int):
        item = self.db.query(ConsignmentItem).filter(ConsignmentItem.id == item_id).first()
        if not item:
            raise ValueError(f"未找到 ID 为 {item_id} 的寄售记录")
        if (item.sold_qty or 0) > 0 or (item.returned_qty or 0) > 0:
            raise ValueError("该寄售记录已发生结算售出或退回仓库，请先撤销关联结算单/退回记录后再删除")

        if item.inventory_log_id:
            inv_log = self.db.query(InventoryLog).filter(InventoryLog.id == item.inventory_log_id).first()
            if inv_log:
                prod = self.db.query(Product).filter(Product.name == inv_log.product_name).first()
                self.db.delete(inv_log)
                self.db.flush()
                if prod:
                    InventoryService(self.db).sync_product_metrics(prod.id)

        self.db.delete(item)
        self.db.flush()

    # ================= 3. 寄售店退回仓库 =================

    def return_to_warehouse(
        self,
        entries: list[dict],
        warehouse_id: int,
        return_date: Optional[date] = None,
        notes: str = "",
    ) -> list[ConsignmentReturn]:
        """
        寄售店退回到指定物理仓库（支持单条或批量）。
        entries: [{"consignment_item_id": int, "return_qty": int}, ...]
        """
        if not entries:
            raise ValueError("请选择至少一条待退回的寄售商品")
        wh = self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not wh:
            raise ValueError("请选择有效的退回目标仓库")

        r_date = return_date or date.today()
        created_returns = []
        product_ids_to_sync = set()

        for entry in entries:
            c_id = int(entry.get("consignment_item_id", 0) or 0)
            r_qty = int(entry.get("return_qty", 0) or 0)
            if r_qty <= 0:
                continue

            item = self.db.query(ConsignmentItem).filter(ConsignmentItem.id == c_id).with_for_update().first()
            if not item:
                raise ValueError(f"寄售记录 ID={c_id} 不存在")
            if r_qty > (item.remaining_qty or 0):
                raise ValueError(
                    f"【{item.shop_name} / {item.product_name}-{item.variant}】当前在店仅剩 {item.remaining_qty} 件，"
                    f"无法退回 {r_qty} 件"
                )

            note_str = f"寄售退回: {item.shop_name}" + (f" | {notes.strip()}" if notes and notes.strip() else "")
            inv_log = InventoryLog(
                product_name=item.product_name,
                variant=item.variant,
                change_amount=r_qty,
                reason=StockLogReason.CONSIGNMENT_RETURN,
                date=r_date,
                note=note_str,
                warehouse_id=wh.id,
                part_name=item.part_name,
            )
            self.db.add(inv_log)
            self.db.flush()

            ret_rec = ConsignmentReturn(
                consignment_item_id=item.id,
                shop_name=item.shop_name,
                product_name=item.product_name,
                variant=item.variant,
                part_name=item.part_name,
                warehouse_id=wh.id,
                warehouse_name=wh.name,
                return_qty=r_qty,
                return_date=r_date,
                inventory_log_id=inv_log.id,
                notes=(notes or "").strip(),
            )
            self.db.add(ret_rec)

            item.returned_qty = int(item.returned_qty or 0) + r_qty
            item.remaining_qty = max(0, int(item.remaining_qty or 0) - r_qty)
            item.status = _recompute_item_status(item)

            prod = self.db.query(Product).filter(Product.name == item.product_name).first()
            if prod:
                product_ids_to_sync.add(prod.id)
            created_returns.append(ret_rec)

        if not created_returns:
            raise ValueError("未检测到大于 0 的有效退回数量")

        self.db.flush()
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)
        return created_returns

    def get_return_history(self, shop_name: Optional[str] = None) -> list[ConsignmentReturn]:
        query = self.db.query(ConsignmentReturn)
        if shop_name:
            query = query.filter(ConsignmentReturn.shop_name == shop_name)
        return query.order_by(ConsignmentReturn.return_date.desc(), ConsignmentReturn.id.desc()).all()

    def revoke_return(self, return_id: int) -> str:
        """撤销退回记录：校验目标仓库剩余实物是否足够扣回，恢复寄售在店余量。"""
        ret = self.db.query(ConsignmentReturn).filter(ConsignmentReturn.id == return_id).first()
        if not ret:
            raise ValueError("退回记录不存在")

        item = self.db.query(ConsignmentItem).filter(ConsignmentItem.id == ret.consignment_item_id).first()
        inv_service = InventoryService(self.db)

        if ret.inventory_log_id:
            inv_log = self.db.query(InventoryLog).filter(InventoryLog.id == ret.inventory_log_id).first()
            if inv_log:
                wh_details = inv_service.get_warehouse_inventory_details()
                stock_in_wh = wh_details.get(inv_log.warehouse_id, {}).get("stock", {}).get(inv_log.product_name, {}).get(inv_log.variant, {})
                prod = self.db.query(Product).filter(Product.name == inv_log.product_name).first()
                if inv_log.part_name:
                    avail = stock_in_wh.get(inv_log.part_name, 0)
                    if avail < ret.return_qty:
                        raise ValueError(
                            f"无法撤销退回：仓库【{ret.warehouse_name}】中【{inv_log.product_name}-{inv_log.variant}】"
                            f"部件【{inv_log.part_name}】当前仅剩 {avail} 件，不足以扣回 {ret.return_qty} 件"
                        )
                else:
                    target_c = next((c for c in prod.colors if c.color_name == inv_log.variant), None) if prod else None
                    parts_req = {p.part_name: p.quantity for p in target_c.parts} if (target_c and target_c.parts) else {"整套": 1}
                    for pt, req in parts_req.items():
                        avail = stock_in_wh.get(pt, 0)
                        need = ret.return_qty * req
                        if avail < need:
                            raise ValueError(
                                f"无法撤销退回：仓库【{ret.warehouse_name}】中【{inv_log.product_name}-{inv_log.variant}】"
                                f"部件【{pt}】仅剩 {avail} 件，不足以扣回 {need} 件"
                            )
                self.db.delete(inv_log)
                self.db.flush()
                if prod:
                    inv_service.sync_product_metrics(prod.id)

        if item:
            item.returned_qty = max(0, int(item.returned_qty or 0) - int(ret.return_qty or 0))
            item.remaining_qty = int(item.remaining_qty or 0) + int(ret.return_qty or 0)
            item.status = _recompute_item_status(item)

        self.db.delete(ret)
        self.db.flush()
        return f"已撤销寄售退回（{ret.product_name}-{ret.variant} ×{ret.return_qty}），已恢复寄售店在售余量"

    # ================= 4. 寄售结算处理与财务入账 =================

    def _generate_settlement_no(self, s_date: date) -> str:
        prefix = f"CS-{s_date.strftime('%Y%m%d')}-"
        existing = (
            self.db.query(ConsignmentSettlement.settlement_no)
            .filter(ConsignmentSettlement.settlement_no.like(f"{prefix}%"))
            .all()
        )
        max_seq = 0
        for (no,) in existing:
            try:
                seq = int(str(no).replace(prefix, ""))
                if seq > max_seq:
                    max_seq = seq
            except Exception:
                pass
        return f"{prefix}{max_seq + 1:03d}"

    def create_settlement(
        self,
        shop_id: Optional[int],
        shop_name: str,
        items: list[dict],
        account_id: int,
        settlement_date: Optional[date] = None,
        currency: str = "CNY",
        fee_rate: Optional[float] = None,
        fee_amount: Optional[float] = None,
        net_amount: Optional[float] = None,
        notes: str = "",
    ) -> ConsignmentSettlement:
        """
        创建寄售结算单（支持单条或按店批量合并结算）。
        items: [{"consignment_item_id": int, "sold_qty": int, "unit_price": float}, ...]
        """
        if not items:
            raise ValueError("请选择至少一条寄售商品进行结算")

        acc = self.db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.id == account_id,
            CompanyBalanceItem.category == BalanceCategory.ASSET,
        ).with_for_update().first()
        if not acc:
            raise ValueError("请选择有效的入账资金账户")

        shop_obj = None
        if shop_id:
            shop_obj = self.db.query(ConsignmentShop).filter(ConsignmentShop.id == shop_id).first()
        if not shop_obj and shop_name:
            shop_obj = self.get_or_create_shop(shop_name, currency)

        s_date = settlement_date or date.today()
        used_currency = (currency or (shop_obj.currency if shop_obj else None) or acc.currency or Currency.CNY).strip().upper()
        used_fee_rate = float(fee_rate if fee_rate is not None else (shop_obj.default_fee_rate if shop_obj else 0.0))

        parsed_rows = []
        gross_total = 0.0
        total_sold_qty = 0

        for entry in items:
            c_id = int(entry.get("consignment_item_id", 0) or 0)
            s_qty = int(entry.get("sold_qty", 0) or 0)
            u_price = float(entry.get("unit_price", 0.0) or 0.0)
            if s_qty <= 0:
                continue
            if u_price < 0:
                raise ValueError("销售单价不能为负数")

            cons_item = self.db.query(ConsignmentItem).filter(ConsignmentItem.id == c_id).with_for_update().first()
            if not cons_item:
                raise ValueError(f"寄售记录 ID={c_id} 不存在")
            if s_qty > (cons_item.remaining_qty or 0):
                raise ValueError(
                    f"【{cons_item.shop_name} / {cons_item.product_name}-{cons_item.variant}】"
                    f"当前仅剩 {cons_item.remaining_qty} 件，无法结算 {s_qty} 件"
                )
            if not shop_obj:
                shop_obj = self.get_or_create_shop(cons_item.shop_name, used_currency)

            gross_sub = round(s_qty * u_price, 2)
            gross_total += gross_sub
            total_sold_qty += s_qty
            parsed_rows.append({
                "cons_item": cons_item,
                "sold_qty": s_qty,
                "unit_price": u_price,
                "gross_subtotal": gross_sub,
            })

        if not parsed_rows:
            raise ValueError("未检测到大于 0 的有效售出数量")

        gross_total = round(gross_total, 2)
        if fee_amount is None:
            fixed_fee = float(shop_obj.default_fee_fixed or 0.0) if shop_obj else 0.0
            calc_fee = gross_total * used_fee_rate + fixed_fee
            used_fee_amount = float(round(calc_fee)) if used_currency == Currency.JPY else round(calc_fee, 2)
        else:
            used_fee_amount = round(float(fee_amount), 2)

        if net_amount is None:
            used_net_amount = round(max(0.0, gross_total - used_fee_amount), 2)
        else:
            used_net_amount = round(float(net_amount), 2)

        if used_net_amount < 0:
            raise ValueError("实际入账金额不能为负数")

        # 按毛额比例分摊实收净额到每个商品明细（用于销售额一览 & 销售订单明细）
        accumulated_net = 0.0
        for idx, row in enumerate(parsed_rows):
            if idx == len(parsed_rows) - 1:
                net_sub = round(used_net_amount - accumulated_net, 2)
            else:
                if gross_total > 0:
                    net_sub = round(used_net_amount * (row["gross_subtotal"] / gross_total), 2)
                else:
                    net_sub = round(used_net_amount * (row["sold_qty"] / total_sold_qty), 2)
                accumulated_net += net_sub
            row["net_subtotal"] = net_sub
            row["net_unit_price"] = round(net_sub / row["sold_qty"], 4) if row["sold_qty"] > 0 else 0.0

        settlement_no = self._generate_settlement_no(s_date)
        shop_display = shop_obj.name if shop_obj else (shop_name or "默认寄售店")
        platform_label = f"寄售-{shop_display}"
        clean_notes = (notes or "").strip()
        order_notes = (
            f"寄售结算单:{settlement_no} | 毛额:{gross_total:.2f} | 店铺手续费:{used_fee_amount:.2f} | 实收:{used_net_amount:.2f}"
            + (f" | {clean_notes}" if clean_notes else "")
        )

        # 1. 创建已完成销售单（不重复写 InventoryLog，因仓库出库至寄售店时已扣减库存）
        sales_order = SalesOrder(
            order_no=settlement_no,
            order_type="寄售",
            status=OrderStatus.COMPLETED,
            total_amount=used_net_amount,
            currency=used_currency,
            platform=platform_label,
            target_account_name=acc.name,
            created_date=s_date,
            shipped_date=s_date,
            completed_date=s_date,
            notes=order_notes,
        )
        self.db.add(sales_order)
        self.db.flush()

        for row in parsed_rows:
            ci = row["cons_item"]
            self.db.add(SalesOrderItem(
                order_id=sales_order.id,
                product_name=ci.product_name,
                variant=ci.variant,
                quantity=row["sold_qty"],
                unit_price=row["net_unit_price"],
                subtotal=row["net_subtotal"],
                warehouse_id=ci.warehouse_id,
            ))

        # 2. 创建财务收入流水 & 更新目标现金账户余额
        fin_rec = None
        if used_net_amount > 0:
            fin_desc = (
                f"寄售结算: {settlement_no} ({shop_display}) "
                f"[毛额:{gross_total:.2f}, 手续费:{used_fee_amount:.2f}] [账户: {acc.name}]"
            )
            fin_rec = FinanceRecord(
                date=s_date,
                amount=used_net_amount,
                currency=used_currency,
                category=FinanceCategory.SALES_INCOME,
                description=fin_desc,
                order_id=sales_order.id,
                account_id=acc.id,
            )
            self.db.add(fin_rec)
            self.db.flush()
            acc.amount = float(acc.amount or 0.0) + used_net_amount

        # 3. 保存寄售结算单及明细，扣减寄售在店余量
        settlement = ConsignmentSettlement(
            settlement_no=settlement_no,
            shop_id=shop_obj.id if shop_obj else None,
            shop_name=shop_display,
            settlement_date=s_date,
            currency=used_currency,
            gross_amount=gross_total,
            fee_rate=used_fee_rate,
            fee_amount=used_fee_amount,
            net_amount=used_net_amount,
            account_id=acc.id,
            account_name=acc.name,
            sales_order_id=sales_order.id,
            finance_record_id=fin_rec.id if fin_rec else None,
            notes=clean_notes,
        )
        self.db.add(settlement)
        self.db.flush()

        for row in parsed_rows:
            ci = row["cons_item"]
            self.db.add(ConsignmentSettlementItem(
                settlement_id=settlement.id,
                consignment_item_id=ci.id,
                product_name=ci.product_name,
                variant=ci.variant,
                part_name=ci.part_name,
                sold_qty=row["sold_qty"],
                unit_price=row["unit_price"],
                gross_subtotal=row["gross_subtotal"],
                net_subtotal=row["net_subtotal"],
            ))
            ci.sold_qty = int(ci.sold_qty or 0) + row["sold_qty"]
            ci.remaining_qty = max(0, int(ci.remaining_qty or 0) - row["sold_qty"])
            if row["unit_price"] > 0:
                ci.unit_price = row["unit_price"]
            ci.status = _recompute_item_status(ci)

        self.db.flush()
        return settlement

    def get_settlements(self, shop_id: Optional[int] = None) -> list[ConsignmentSettlement]:
        query = self.db.query(ConsignmentSettlement).options(
            joinedload(ConsignmentSettlement.items)
        )
        if shop_id is not None:
            query = query.filter(ConsignmentSettlement.shop_id == shop_id)
        return query.order_by(ConsignmentSettlement.settlement_date.desc(), ConsignmentSettlement.id.desc()).all()

    def delete_settlement(self, settlement_id: int) -> str:
        """撤销寄售结算单：全量回滚现金账户、财务流水、销售订单及寄售在店余量"""
        settlement = (
            self.db.query(ConsignmentSettlement)
            .options(joinedload(ConsignmentSettlement.items))
            .filter(ConsignmentSettlement.id == settlement_id)
            .first()
        )
        if not settlement:
            raise ValueError("寄售结算单不存在")

        # 1. 回滚资金账户余额
        if (settlement.net_amount or 0.0) != 0:
            acc = None
            if settlement.account_id:
                acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == settlement.account_id).first()
            if not acc and settlement.account_name:
                acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == settlement.account_name).first()
            if acc:
                acc.amount = float(acc.amount or 0.0) - float(settlement.net_amount or 0.0)

        # 2. 清理财务流水
        if settlement.finance_record_id:
            fin = self.db.query(FinanceRecord).filter(FinanceRecord.id == settlement.finance_record_id).first()
            if fin:
                self.db.delete(fin)

        # 3. 清理关联销售单（级联删除 SalesOrderItem 及关联残余 FinanceRecord）
        if settlement.sales_order_id:
            so = self.db.query(SalesOrder).filter(SalesOrder.id == settlement.sales_order_id).first()
            if so:
                self.db.delete(so)

        # 4. 恢复寄售条目剩余数与已售数
        for s_item in settlement.items:
            if s_item.consignment_item_id:
                ci = self.db.query(ConsignmentItem).filter(ConsignmentItem.id == s_item.consignment_item_id).first()
                if ci:
                    ci.sold_qty = max(0, int(ci.sold_qty or 0) - int(s_item.sold_qty or 0))
                    ci.remaining_qty = int(ci.remaining_qty or 0) + int(s_item.sold_qty or 0)
                    ci.status = _recompute_item_status(ci)

        no_str = settlement.settlement_no
        self.db.delete(settlement)
        self.db.flush()
        return f"已撤销寄售结算单 {no_str}，相关资金入账、销售订单与在店余量已全量回滚！"
