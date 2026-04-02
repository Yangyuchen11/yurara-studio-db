# services/finance_service.py
from sqlalchemy import or_
from datetime import date
import pandas as pd
import re
from models import (
    FinanceRecord, Product, CostItem, ConsumableItem,
    FixedAsset, ConsumableLog, CompanyBalanceItem
)
from constants import AssetPrefix, BalanceCategory, Currency, FinanceCategory

class FinanceService:
    """
    负责财务流水、债务、兑换及相关资产联动的核心业务逻辑
    """

    # ================= 辅助查询方法 =================

    @staticmethod
    def get_transferable_assets(db):
        """获取所有可移动的资产项目 (CNY 和 JPY)"""
        return db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.category == BalanceCategory.ASSET,
            CompanyBalanceItem.asset_type == "现金" 
        ).order_by(CompanyBalanceItem.currency, CompanyBalanceItem.id.asc()).all()

    @staticmethod
    def get_cash_asset(db, currency):
        """获取指定币种的流动资金账户对象"""
        return db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.name.like(f"{AssetPrefix.CASH}%"),
            CompanyBalanceItem.currency == currency,
            CompanyBalanceItem.category == BalanceCategory.ASSET
        ).order_by(CompanyBalanceItem.id.asc()).first()

    @staticmethod
    def get_balance_items(db, category):
        """获取指定类别的账目项 (asset/liability/equity)"""
        return db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == category).all()

    @staticmethod
    def get_all_products(db):
        return db.query(Product).all()

    @staticmethod
    def get_budget_items(db, product_id, category):
        """获取指定产品的预算项"""
        return db.query(CostItem).filter(
            CostItem.product_id == product_id,
            CostItem.category == category,
            CostItem.supplier == "预算设定"
        ).all()

    @staticmethod
    def get_consumable_items(db):
        return db.query(ConsumableItem).all()

    @staticmethod
    def get_finance_records_with_balance(db):
        records = db.query(FinanceRecord).order_by(FinanceRecord.date.asc(), FinanceRecord.id.asc()).all()
        processed_data = []
        running_cny = 0.0
        running_jpy = 0.0
        
        if records:
            for r in records:
                if r.currency == "CNY": running_cny += r.amount
                elif r.currency == "JPY": running_jpy += r.amount
                
                processed_data.append({
                    "ID": r.id, 
                    "日期": r.date, 
                    "币种": r.currency, 
                    "收支": "收入" if r.amount > 0 else "支出",
                    "金额": abs(r.amount),
                    "分类": r.category, 
                    "备注": r.description or "",
                    "网址": r.url or "", 
                    "当前CNY余额": running_cny, 
                    "当前JPY余额": running_jpy
                })
            return pd.DataFrame(processed_data).sort_values(by=["日期", "ID"], ascending=[False, False]).reset_index(drop=True)
        return pd.DataFrame()

    @staticmethod
    def get_current_balances(db):
        """获取当前账户总余额"""
        records = db.query(FinanceRecord).all()
        cny = sum(r.amount for r in records if r.currency == "CNY")
        jpy = sum(r.amount for r in records if r.currency == "JPY")
        return cny, jpy

    @staticmethod
    def execute_fund_transfer(db, date_val, from_asset_id, to_asset_id, amount, desc):
        """执行同币种的资金移动"""
        from_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == from_asset_id).first()
        to_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == to_asset_id).first()
        
        if not from_asset or not to_asset:
            raise ValueError("资产不存在")
        
        if from_asset.currency != to_asset.currency:
            raise ValueError("币种不同，无法直接移动资金")
            
        from_is_cash = from_asset.name.startswith(AssetPrefix.CASH)
        to_is_cash = to_asset.name.startswith(AssetPrefix.CASH)
        
        record_amount = 0
        if from_is_cash and not to_is_cash:
            record_amount = -amount
        elif not from_is_cash and to_is_cash:
            record_amount = amount
            
        desc_str = f"资金移动: [{from_asset.name}] -> [{to_asset.name}] | 金额: {amount} | 备注: {desc}"
        
        # ✨ 绑定强外键
        rec = FinanceRecord(
            date=date_val, 
            amount=record_amount, 
            currency=from_asset.currency,  
            category="资金移动", 
            description=desc_str,
            account_id=from_asset.id,
            related_item_id=to_asset.id
        )
        db.add(rec)
        
        from_asset.amount -= amount
        to_asset.amount += amount
        
        if from_asset.amount <= 0.01 and not from_is_cash:
            db.delete(from_asset)
            
        db.commit()


    # ================= 业务写入方法 =================

    @staticmethod
    def get_cash_asset_by_id(db, account_id):
        return db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == account_id).first()

    @staticmethod
    def execute_exchange(db, date_val, source_curr, target_curr, amount_out, amount_in, desc, source_acc_id=None, target_acc_id=None):
        asset_out = FinanceService.get_cash_asset_by_id(db, source_acc_id) if source_acc_id else FinanceService.get_cash_asset(db, source_curr)
        asset_in = FinanceService.get_cash_asset_by_id(db, target_acc_id) if target_acc_id else FinanceService.get_cash_asset(db, target_curr)
        
        # 确保入账侧账户一定存在，获取它的 ID
        if not asset_in:
            in_name = f"流动资金({target_curr})"
            asset_in = CompanyBalanceItem(category=BalanceCategory.ASSET, name=in_name, amount=0, currency=target_curr, asset_type="现金")
            db.add(asset_in)
            db.flush()
            
        out_name = asset_out.name if asset_out else f"流动资金({source_curr})"
        in_name = asset_in.name

        # ✨ 绑定强外键
        rec_out = FinanceRecord(
            date=date_val, amount=-amount_out, currency=source_curr,
            category=FinanceCategory.EXCHANGE, description=f"兑换支出 (-> {target_curr}) [账户: {out_name}] | {desc}",
            account_id=asset_out.id if asset_out else None
        )
        db.add(rec_out)
        
        rec_in = FinanceRecord(
            date=date_val, amount=amount_in, currency=target_curr,
            category=FinanceCategory.EXCHANGE, description=f"兑换入账 (<- {source_curr}) [账户: {in_name}] | {desc}",
            account_id=asset_in.id
        )
        db.add(rec_in)
        
        if asset_out: asset_out.amount -= amount_out
        asset_in.amount += amount_in
        db.commit()

    @staticmethod
    def create_debt(db, date_val, curr, name, amount, source, remark, is_to_cash, related_content, target_acc_id=None):
        if is_to_cash:
            cash_asset = FinanceService.get_cash_asset_by_id(db, target_acc_id) if target_acc_id else FinanceService.get_cash_asset(db, curr)
            if not cash_asset:
                acc_name = f"流动资金({curr})"
                cash_asset = CompanyBalanceItem(category=BalanceCategory.ASSET, name=acc_name, amount=0, currency=curr, asset_type="现金")
                db.add(cash_asset)
                db.flush()
                
            finance_rec = FinanceRecord(
                date=date_val, amount=amount, currency=curr, category="借入资金",
                description=f"借入资金: {name} (债权人: {source}) [账户: {cash_asset.name}] | {remark}",
                account_id=cash_asset.id # ✨ 绑定强外键
            )
            db.add(finance_rec)
            db.flush()
            
            cash_asset.amount += amount
            
            # 生成负债并绑定
            debt = CompanyBalanceItem(name=name, amount=amount, category=BalanceCategory.LIABILITY, currency=curr, finance_record_id=finance_rec.id)
            db.add(debt)
            db.flush()
            finance_rec.related_item_id = debt.id # ✨ 将生成的负债ID反向绑定给流水

        else:
            finance_rec = FinanceRecord(
                date=date_val, amount=0, currency=curr, category="新增挂账资产",
                description=f"挂账资产: {related_content} (原债务: {name}) | 金额: {amount} | {remark}"
            )
            db.add(finance_rec)
            db.flush()
            
            new_asset = CompanyBalanceItem(name=related_content, amount=amount, category=BalanceCategory.ASSET, currency=curr, finance_record_id=finance_rec.id)
            db.add(new_asset)
            db.flush()
            
            debt = CompanyBalanceItem(name=name, amount=amount, category=BalanceCategory.LIABILITY, currency=curr, finance_record_id=finance_rec.id)
            db.add(debt)
            db.flush()
            
            finance_rec.related_item_id = debt.id # ✨ 记录负债ID

        db.commit()

    @staticmethod
    def repay_debt(db, date_val, debt_id, amount, remark, source_acc_id=None):
        target_liab = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == debt_id).first()
        if not target_liab: raise ValueError("债务不存在")

        cash_asset = FinanceService.get_cash_asset_by_id(db, source_acc_id) if source_acc_id else FinanceService.get_cash_asset(db, target_liab.currency)
        acc_name = cash_asset.name if cash_asset else f"流动资金({target_liab.currency})"

        finance_rec = FinanceRecord(
            date=date_val, amount=-amount, currency=target_liab.currency, category="债务偿还",
            description=f"偿还债务: [{target_liab.name}] [账户: {acc_name}] | {remark}",
            account_id=cash_asset.id if cash_asset else None,
            related_item_id=target_liab.id # ✨ 强绑定要偿还的债务ID
        )
        db.add(finance_rec)

        if cash_asset: cash_asset.amount -= amount
        
        target_liab.amount -= amount
        if target_liab.amount <= 0.01: db.delete(target_liab)
        db.commit()

    @staticmethod
    def offset_debt(db, date_val, debt_id, asset_id, amount, remark):
        target_liab = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == debt_id).first()
        target_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == asset_id).first()
        if not target_liab or not target_asset: raise ValueError("债务或资产不存在")

        finance_rec = FinanceRecord(
            date=date_val, amount=0, currency=target_liab.currency, category="资产抵消",
            description=f"抵消债务[{target_liab.name}] [使用资产/账户: {target_asset.name}] | 核销金额: {amount} | {remark}",
            related_item_id=target_liab.id # ✨ 强绑定被抵消的债务ID
        )
        db.add(finance_rec)

        target_asset.amount -= amount
        if target_asset.amount <= 0.01: db.delete(target_asset)
        
        target_liab.amount -= amount
        if target_liab.amount <= 0.01: db.delete(target_liab)
            
        db.commit()

    @staticmethod
    def create_general_transaction(db, base_data, link_config, exchange_rate):
        is_income = (base_data['type'] == "收入")
        signed_amount = base_data['amount'] if is_income else -base_data['amount']
        
        acc_id = base_data.get('account_id')
        target_cash = FinanceService.get_cash_asset_by_id(db, acc_id) if acc_id else FinanceService.get_cash_asset(db, base_data['currency'])
        
        # 确保收款现金账户提前生成并拿到 ID
        if not target_cash:
            target_cash = CompanyBalanceItem(category=BalanceCategory.ASSET, name=f"流动资金({base_data['currency']})", amount=0.0, currency=base_data['currency'], asset_type="现金")
            db.add(target_cash)
            db.flush()
            
        acc_name = target_cash.name
        
        note_detail = f"{base_data['shop']}" if base_data['shop'] else ""
        if link_config.get('qty', 1) > 1: note_detail += f" (x{link_config['qty']})"
        if base_data['desc']: note_detail += f" | {base_data['desc']}"
        note_detail += f" [账户: {acc_name}]"
        
        # ✨ 生成流水时强绑定 account_id
        new_record = FinanceRecord(
            date=base_data['date'], amount=signed_amount, currency=base_data['currency'],
            category=base_data['category'], description=f"{link_config.get('name', '')} [{note_detail}]",
            url=base_data.get('url', ''),
            account_id=target_cash.id
        )
        db.add(new_record)
        db.flush()

        # 3. 更新流动资金
        target_cash.amount += signed_amount

        # 4. 处理联动逻辑
        l_type = link_config.get('link_type')
        link_msg = "资金变动已记录"
        
        if l_type in ['equity', 'manual_asset']:
            balance_delta = signed_amount
            if link_config.get('is_new'):
                new_bi = CompanyBalanceItem(
                    name=link_config['name'], amount=balance_delta, 
                    category=BalanceCategory.EQUITY if l_type == 'equity' else BalanceCategory.ASSET,
                    currency=base_data['currency'], finance_record_id=new_record.id,
                    asset_type=link_config.get('asset_type', '资产') 
                )
                db.add(new_bi)
                link_msg += f" + 新{l_type} ({balance_delta:+.2f})"
            elif link_config.get('target_id'):
                existing_bi = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == link_config['target_id']).first()
                if existing_bi:
                    existing_bi.amount += balance_delta
                    if existing_bi.amount <= 0.01: 
                        db.delete(existing_bi)
                        link_msg += f" ({l_type}已归零并移除)"
                    else:
                        link_msg += f" + 更新{l_type} ({balance_delta:+.2f})"

        elif l_type == 'cost':
            cost_in_cny = base_data['amount']
            unit_price_cny = link_config['unit_price']
            final_remark = base_data['desc']
            
            if base_data['currency'] == Currency.JPY:
                cost_in_cny = base_data['amount'] * exchange_rate
                unit_price_cny = cost_in_cny / link_config['qty'] if link_config['qty'] > 0 else 0
                final_remark = f"{base_data['desc']} (原币支付: {base_data['amount']:.0f} JPY)".strip()

            detailed_cat = link_config.get('cat') if link_config.get('cat') else base_data['category']

            target_cost_id = link_config.get('target_cost_id')
            if target_cost_id:
                target_cost = db.query(CostItem).filter(CostItem.id == target_cost_id).first()
                if target_cost:
                    target_cost.actual_cost += cost_in_cny
                    if final_remark:
                        target_cost.remarks = f"{target_cost.remarks} | {final_remark}" if target_cost.remarks else final_remark
                    new_record.related_item_id = target_cost.id
                    link_msg += f" + 累加实付至预算[{target_cost.item_name}]"
                    
                    # ✨ 核心修复：通知系统立刻重算该商品大货资产
                    db.flush()
                    from services.inventory_service import InventoryService
                    InventoryService(db).sync_product_metrics(target_cost.product_id)
            else:
                new_cost = CostItem(
                    product_id=link_config['product_id'], item_name=link_config['name'],
                    actual_cost=cost_in_cny, supplier=base_data['shop'], category=detailed_cat,
                    unit_price=unit_price_cny, quantity=link_config['qty'], 
                    remarks=final_remark, finance_record_id=new_record.id,
                    url=base_data.get('url', '')
                )
                db.add(new_cost)
                
                # ✨ 核心修复：通知系统立刻重算该商品大货资产
                db.flush()
                from services.inventory_service import InventoryService
                InventoryService(db).sync_product_metrics(new_cost.product_id)
                
                link_msg += " + 新增商品成本(已折算CNY)"

        elif l_type == 'fixed_asset':
            db.add(FixedAsset(
                name=link_config['name'], unit_price=link_config['unit_price'], 
                quantity=link_config['qty'], remaining_qty=link_config['qty'],
                shop_name=base_data['shop'], remarks=base_data['desc'], 
                currency=base_data['currency'], finance_record_id=new_record.id,
                url=base_data.get('url', '')
            ))
            link_msg += " + 固定资产"

        elif l_type == 'consumable':
            rate = exchange_rate if base_data['currency'] == "JPY" else 1.0
            val_cny = base_data['amount'] * rate
            
            target_item = db.query(ConsumableItem).filter(ConsumableItem.name == link_config['name']).first()
            
            if target_item:
                old_total = target_item.unit_price * target_item.remaining_qty
                new_total = base_data['amount']
                target_item.remaining_qty += link_config['qty']
                if target_item.remaining_qty > 0:
                    target_item.unit_price = (old_total + new_total) / target_item.remaining_qty
                if base_data['shop']: target_item.shop_name = base_data['shop']
                if link_config.get('cat'): target_item.category = link_config['cat']
                if base_data.get('url'): target_item.url = base_data['url']
                log_note = f"资产增加(收入): {base_data['desc']}" if is_income else f"购入入库: {base_data['desc']}"
                link_msg += f" + 其他资产库存 (已合并: {target_item.name})"
            else:
                new_con = ConsumableItem(
                    name=link_config['name'], category=link_config.get('cat', '其他'),
                    unit_price=link_config['unit_price'], initial_quantity=link_config['qty'],
                    remaining_qty=link_config['qty'], shop_name=base_data['shop'],
                    remarks=base_data['desc'], currency=base_data['currency'],
                    finance_record_id=new_record.id,
                    url=base_data.get('url', '')
                )
                db.add(new_con)
                log_note = f"资产增加(初始): {base_data['desc']}" if is_income else f"初始购入: {base_data['desc']}"
                link_msg += " + 新其他资产库存"
            
            db.add(ConsumableLog(
                item_name=link_config['name'], change_qty=link_config['qty'],
                value_cny=val_cny, note=log_note, date=base_data['date']
            ))

        db.commit()
        return link_msg

    # ================= 编辑与删除 =================

    @staticmethod
    def get_record_by_id(db, record_id):
        return db.query(FinanceRecord).filter(FinanceRecord.id == record_id).first()

    @staticmethod
    def update_record(db, record_id, updates):
        rec = FinanceService.get_record_by_id(db, record_id)
        if not rec: return False

        # 1. 精准回滚旧账户的资金
        old_cash_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == rec.account_id).first()
        if not old_cash_asset and rec.description: 
            # 兼容老数据
            match = re.search(r'\[账户:\s*(.+?)\]', rec.description)
            if match:
                old_cash_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == match.group(1)).first()
        
        if old_cash_asset:
            old_cash_asset.amount -= rec.amount
        
        # 2. 计算新数据并入账新账户
        new_signed_amount = updates['amount_abs'] if updates['type'] == "收入" else -updates['amount_abs']
        
        # ✨ 直接使用前端传来的用户指定账户
        new_acc_id = updates.get('account_id')
        new_cash_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == new_acc_id).first()
        
        if new_cash_asset:
            new_currency = new_cash_asset.currency # 以真实账户的币种为准
            new_cash_asset.amount += new_signed_amount
        else:
            raise ValueError("未找到指定的账户！")
            
        # 3. 更新流水自身 (同步外键)
        rec.date = updates['date']
        rec.currency = new_currency
        rec.amount = new_signed_amount
        rec.category = updates['category']
        rec.description = updates['desc']
        rec.url = updates.get('url', '')
        rec.account_id = new_cash_asset.id # ✨ 强绑定用户指定的账户ID
        
        # 4. 级联更新关联表
        # ✨ 对于关联在已有预算项上的实付更新
        product_id_to_sync = None
        if rec.category == "商品成本" and rec.related_item_id:
            target_cost = db.query(CostItem).filter(CostItem.id == rec.related_item_id).first()
            if target_cost:
                target_cost.actual_cost = target_cost.actual_cost - abs(rec.amount) + updates['amount_abs']
                target_cost.remarks = f"{updates['desc']} (已修)"
                product_id_to_sync = target_cost.product_id 
        else:
            for cost in db.query(CostItem).filter(CostItem.finance_record_id == record_id).all():
                cost.actual_cost = updates['amount_abs']
                cost.remarks = f"{updates['desc']} (已修)"
                product_id_to_sync = cost.product_id
            
        for fa in db.query(FixedAsset).filter(FixedAsset.finance_record_id == record_id).all():
            if fa.quantity > 0: fa.unit_price = updates['amount_abs'] / fa.quantity
            fa.currency = updates['currency'] 
            
        for ci in db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == record_id).all():
            if ci.initial_quantity > 0: ci.unit_price = updates['amount_abs'] / ci.initial_quantity
            ci.currency = updates['currency']
            
        for bi in db.query(CompanyBalanceItem).filter(CompanyBalanceItem.finance_record_id == record_id).all():
            bi.amount = updates['amount_abs']
            bi.currency = updates['currency']

        db.flush()
        if product_id_to_sync:
            from services.inventory_service import InventoryService
            InventoryService(db).sync_product_metrics(product_id_to_sync)

        db.commit()
        return True

    @staticmethod
    def delete_record(db, record_id):
        """删除流水并回滚关联数据（全面使用外键替换正则）"""
        rec = FinanceService.get_record_by_id(db, record_id)
        if not rec: return False

        if rec.category == FinanceCategory.SALES_INCOME:
            raise ValueError("拒绝操作：销售收入流水受到系统保护，必须从【销售订单管理】模块发起撤销或删除。")

        msg_list = []

        # === 辅助：强外键获取现金账户 fallback ===
        def get_acc_from_rec(record):
            if record.account_id:
                return db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == record.account_id).first()
            
            # 向后兼容老数据：正则解析
            if record.description:
                match = re.search(r'\[账户:\s*(.+?)\]', record.description)
                if match:
                    acc_name = match.group(1)
                    return db.query(CompanyBalanceItem).filter(
                        CompanyBalanceItem.name == acc_name, 
                        CompanyBalanceItem.category == BalanceCategory.ASSET
                    ).first()
            return FinanceService.get_cash_asset(db, record.currency)


        # ================= 债务系统的特殊回滚逻辑 =================
        
        if rec.category in ["借入资金", "新增挂账资产"]:
            if rec.category == "借入资金":
                cash = get_acc_from_rec(rec)
                if cash: 
                    cash.amount -= rec.amount
                    msg_list.append(f"借入现金已从【{cash.name}】扣回")
                
            deleted_count = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.finance_record_id == rec.id).delete()
            if deleted_count > 0:
                msg_list.append(f"已级联清理 {deleted_count} 项关联账目/负债")

        elif rec.category == "债务偿还":
            cash_asset = get_acc_from_rec(rec)
            if cash_asset: 
                cash_asset.amount -= rec.amount 
                msg_list.append(f"还款资金已退回至【{cash_asset.name}】")
            
            # ✨ 使用外键精准定位负债
            target_liab = None
            if rec.related_item_id:
                target_liab = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == rec.related_item_id).first()
            else:
                # 兼容老数据
                try:
                    debt_name = rec.description.split("偿还债务: [")[1].split("]")[0]
                    target_liab = db.query(CompanyBalanceItem).filter(
                        CompanyBalanceItem.name == debt_name,
                        CompanyBalanceItem.category == BalanceCategory.LIABILITY
                    ).first()
                except:
                    pass
            
            if target_liab: 
                target_liab.amount += abs(rec.amount)
                msg_list.append(f"负债【{target_liab.name}】已复原")
            else:
                msg_list.append("未能自动复原负债，请手动核对")

        elif rec.category == "资产抵消":
            target_liab = None
            if rec.related_item_id:
                target_liab = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == rec.related_item_id).first()
            
            # 兼容老数据与恢复逻辑
            try:
                desc = rec.description
                if "资产[" in desc and "抵消债务[" in desc:
                    asset_name = desc.split("资产[")[1].split("]")[0]
                    debt_name = desc.split("抵消债务[")[1].split("]")[0]
                else:
                    debt_name = desc.split("抵消债务[")[1].split("]")[0]
                    asset_name = desc.split("[使用资产/账户: ")[1].split("]")[0]
                    
                amount_part = float(desc.split("核销金额:")[1].split("|")[0].strip())

                # 复活/增加资产
                target_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()
                if target_asset: target_asset.amount += amount_part
                else: db.add(CompanyBalanceItem(name=asset_name, amount=amount_part, category=BalanceCategory.ASSET, currency=rec.currency))
                
                # 复活/增加负债
                if target_liab: target_liab.amount += amount_part
                else:
                    target_liab = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == debt_name).first()
                    if target_liab: target_liab.amount += amount_part
                    else: db.add(CompanyBalanceItem(name=debt_name, amount=amount_part, category=BalanceCategory.LIABILITY, currency=rec.currency))
                
                msg_list.append("抵消操作已撤销，资产与负债已双向复原")
            except Exception:
                msg_list.append("未能自动复原资产/负债，请手动核对")

        # === 资金移动 ===
        elif rec.category == "资金移动":
            from_asset = None
            to_asset = None
            if rec.account_id and rec.related_item_id:
                from_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == rec.account_id).first()
                to_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == rec.related_item_id).first()
                
            try:
                # 若无法找到记录，兼容旧数据解析
                if not from_asset or not to_asset:
                    part1 = rec.description.split("资金移动: [")[1]
                    from_name = part1.split("] -> [")[0]
                    to_name = part1.split("] -> [")[1].split("] |")[0]
                    from_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == from_name).first()
                    to_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == to_name).first()

                # 从流水解析转移数量
                amount_part = float(rec.description.split("金额: ")[1].split(" |")[0].strip())
                curr = rec.currency  

                if from_asset: 
                    from_asset.amount += amount_part
                else: 
                    db.add(CompanyBalanceItem(name=from_name, amount=amount_part, category=BalanceCategory.ASSET, currency=curr, asset_type="现金"))
                
                if to_asset: 
                    to_asset.amount -= amount_part
                    if to_asset.amount <= 0.01 and getattr(to_asset, "asset_type", "") != "现金":
                        db.delete(to_asset)
                
                msg_list.append("资金移动已撤销")
            except Exception:
                msg_list.append("未能完全自动复原移动资产，请手动核对")

        # ================= 普通流水回滚逻辑 =================
        else:
            cash_asset = get_acc_from_rec(rec)
            if cash_asset: 
                cash_asset.amount -= rec.amount
                msg_list.append(f"资金已从【{cash_asset.name}】回滚")
            
            product_id_to_sync = None # ✨ 初始化

            if rec.category == "商品成本" and rec.related_item_id:
                target_cost = db.query(CostItem).filter(CostItem.id == rec.related_item_id).first()
                if target_cost:
                    target_cost.actual_cost -= abs(rec.amount)
                    if target_cost.actual_cost < 0: target_cost.actual_cost = 0
                    product_id_to_sync = target_cost.product_id # ✨ 捕捉
                    msg_list.append(f"已从预算项【{target_cost.item_name}】扣除实付回滚")
            else:
                # 记录要被删除的成本项对应的 product_id
                cost = db.query(CostItem).filter(CostItem.finance_record_id == record_id).first()
                if cost: product_id_to_sync = cost.product_id
                db.query(CostItem).filter(CostItem.finance_record_id == record_id).delete()
            
            db.query(FixedAsset).filter(FixedAsset.finance_record_id == record_id).delete()
            db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == record_id).delete()
            db.query(CompanyBalanceItem).filter(CompanyBalanceItem.finance_record_id == record_id).delete()
        
        db.delete(rec)
        db.flush()
        
        # ✨ 执行重算
        if 'product_id_to_sync' in locals() and product_id_to_sync:
            from services.inventory_service import InventoryService
            InventoryService(db).sync_product_metrics(product_id_to_sync)

        db.commit()
        return " | ".join(msg_list)