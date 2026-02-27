# services/finance_service.py
from sqlalchemy import or_
from datetime import date
import pandas as pd
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
        """
        获取所有流水记录，并计算动态余额（用于前端展示）
        返回: DataFrame
        """
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
                    "当前CNY余额": running_cny, 
                    "当前JPY余额": running_jpy
                })
            # 倒序排列，最新的在前面
            return pd.DataFrame(processed_data).sort_values(by=["日期", "ID"], ascending=[False, False]).reset_index(drop=True)
        return pd.DataFrame()

    @staticmethod
    def get_current_balances(db):
        """获取当前账户总余额"""
        records = db.query(FinanceRecord).all()
        cny = sum(r.amount for r in records if r.currency == "CNY")
        jpy = sum(r.amount for r in records if r.currency == "JPY")
        return cny, jpy

    # ================= 业务写入方法 =================

    @staticmethod
    def execute_exchange(db, date_val, source_curr, target_curr, amount_out, amount_in, desc):
        """执行货币兑换"""
        # 1. 记录流水
        rec_out = FinanceRecord(
            date=date_val, amount=-amount_out, currency=source_curr,
            category=FinanceCategory.EXCHANGE, description=f"兑换支出 (-> {target_curr}) | {desc}"
        )
        db.add(rec_out)
        rec_in = FinanceRecord(
            date=date_val, amount=amount_in, currency=target_curr,
            category=FinanceCategory.EXCHANGE, description=f"兑换入账 (<- {source_curr}) | {desc}"
        )
        db.add(rec_in)
        
        # 2. 更新资产余额
        asset_out = FinanceService.get_cash_asset(db, source_curr)
        if asset_out: asset_out.amount -= amount_out
        
        asset_in = FinanceService.get_cash_asset(db, target_curr)
        if asset_in: 
            asset_in.amount += amount_in
        else:
            new_asset = CompanyBalanceItem(category=BalanceCategory.ASSET, name=f"{AssetPrefix.CASH}({target_curr})", amount=amount_in, currency=target_curr)
            db.add(new_asset)
        
        db.commit()

    @staticmethod
    def create_debt(db, date_val, curr, name, amount, source, remark, is_to_cash, related_content):
        """新增债务"""
        finance_rec = None
        if is_to_cash:
            # A. 存入流动资金
            finance_rec = FinanceRecord(
                date=date_val, amount=amount, currency=curr, category=FinanceCategory.BORROW,
                description=f"{related_content} (来源: {source}) | {remark}"
            )
            cash_asset = FinanceService.get_cash_asset(db, curr)
            if cash_asset: 
                cash_asset.amount += amount
            else:
                db.add(CompanyBalanceItem(category=BalanceCategory.ASSET, name=f"{AssetPrefix.CASH}({curr})", amount=amount, currency=curr))
        else:
            # B. 形成固定资产或其他资产（不进现金流）
            finance_rec = FinanceRecord(
                date=date_val, amount=0, currency=curr, category=FinanceCategory.DEBT_ASSET_FORM,
                description=f"【资产债务】新增资产: {related_content} | 债务: {name} | 金额: {amount}"
            )
        
        db.add(finance_rec)
        db.flush()

        # 创建负债项
        new_liability = CompanyBalanceItem(
            name=name, amount=amount, category=BalanceCategory.LIABILITY, currency=curr, finance_record_id=finance_rec.id
        )
        db.add(new_liability)

        # 如果是非现金资产，创建对应的资产项
        if not is_to_cash:
            new_asset = CompanyBalanceItem(
                name=related_content, amount=amount, category=BalanceCategory.ASSET, currency=curr, finance_record_id=finance_rec.id
            )
            db.add(new_asset)
        
        db.commit()

    @staticmethod
    def repay_debt(db, date_val, debt_id, amount, remark):
        """资金偿还债务"""
        target_liab = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == debt_id).first()
        if not target_liab: raise ValueError("债务不存在")

        # 记录流水
        new_finance = FinanceRecord(
            date=date_val, amount=-amount, currency=target_liab.currency, category=FinanceCategory.DEBT_REPAY,
            description=f"资金偿还: {target_liab.name} | {remark}"
        )
        db.add(new_finance)
        
        # 减少流动资金
        cash_asset = FinanceService.get_cash_asset(db, target_liab.currency)
        if cash_asset: cash_asset.amount -= amount
        
        # 减少负债
        target_liab.amount -= amount
        if target_liab.amount <= 0.01:
            db.delete(target_liab)
            
        db.commit()

    @staticmethod
    def offset_debt(db, date_val, debt_id, asset_id, amount, remark):
        """资产抵债/核销"""
        target_liab = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == debt_id).first()
        target_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == asset_id).first()
        
        if not target_liab or not target_asset: raise ValueError("债务或资产不存在")

        new_finance = FinanceRecord(
            date=date_val, amount=0, currency=target_liab.currency, category=FinanceCategory.DEBT_ASSET_OFFSET,
            description=f"资产抵消: 用 [{target_asset.name}] 抵消 [{target_liab.name}] | 金额: {amount} | {remark}"
        )
        db.add(new_finance)
        
        target_asset.amount -= amount
        if target_asset.amount <= 0.01: db.delete(target_asset)
        
        target_liab.amount -= amount
        if target_liab.amount <= 0.01: db.delete(target_liab)
            
        db.commit()

    @staticmethod
    def create_general_transaction(db, base_data, link_config, exchange_rate):
        """
        通用收支记录创建 (核心方法)
        base_data: {date, type(收入/支出), amount(abs), currency, category, shop, desc}
        link_config: {
            link_type: 'equity' | 'manual_asset' | 'cost' | 'fixed_asset' | 'consumable',
            is_new: bool,
            target_id: int, 
            name: str,
            qty: float,
            unit_price: float,
            ...
        }
        """
        # 1. 准备基础数据
        is_income = (base_data['type'] == "收入")
        signed_amount = base_data['amount'] if is_income else -base_data['amount']
        
        note_detail = f"{base_data['shop']}" if base_data['shop'] else ""
        if link_config.get('qty', 1) > 1: note_detail += f" (x{link_config['qty']})"
        if base_data['desc']: note_detail += f" | {base_data['desc']}"
        
        # 2. 创建流水
        new_record = FinanceRecord(
            date=base_data['date'], amount=signed_amount, currency=base_data['currency'],
            category=base_data['category'], description=f"{link_config.get('name', '')} [{note_detail}]"
        )
        db.add(new_record)
        db.flush()

        # 3. 更新流动资金
        target_cash = FinanceService.get_cash_asset(db, base_data['currency'])
        if not target_cash:
            target_cash = CompanyBalanceItem(
                category=BalanceCategory.ASSET, name=f"{AssetPrefix.CASH}({base_data['currency']})",
                amount=0.0, currency=base_data['currency']
            )
            db.add(target_cash)
        target_cash.amount += signed_amount

        # 4. 处理联动逻辑
        l_type = link_config.get('link_type')
        link_msg = "资金变动已记录"
        
        # 4.1 资本/手动资产 (CompanyBalanceItem)
        if l_type in ['equity', 'manual_asset']:
            balance_delta = signed_amount
            if link_config.get('is_new'):
                new_bi = CompanyBalanceItem(
                    name=link_config['name'], amount=balance_delta, 
                    category=BalanceCategory.EQUITY if l_type == 'equity' else BalanceCategory.ASSET,
                    currency=base_data['currency'], finance_record_id=new_record.id
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

        # 4.2 商品成本 (CostItem)
        elif l_type == 'cost':
            # JPY折算逻辑
            cost_in_cny = base_data['amount']
            unit_price_cny = link_config['unit_price']
            final_remark = base_data['desc']
            
            if base_data['currency'] == Currency.JPY:
                cost_in_cny = base_data['amount'] * exchange_rate
                unit_price_cny = cost_in_cny / link_config['qty'] if link_config['qty'] > 0 else 0
                final_remark = f"{base_data['desc']} (原币支付: {base_data['amount']:.0f} JPY)".strip()

            detailed_cat = link_config.get('cat') if link_config.get('cat') else base_data['category']

            db.add(CostItem(
                product_id=link_config['product_id'], item_name=link_config['name'],
                actual_cost=cost_in_cny, supplier=base_data['shop'], category=detailed_cat, # 👈 使用具体分类
                unit_price=unit_price_cny, quantity=link_config['qty'], 
                remarks=final_remark, finance_record_id=new_record.id
            ))
            link_msg += " + 商品成本(已折算CNY)"

        # 4.3 固定资产 (FixedAsset)
        elif l_type == 'fixed_asset':
            db.add(FixedAsset(
                name=link_config['name'], unit_price=link_config['unit_price'], 
                quantity=link_config['qty'], remaining_qty=link_config['qty'],
                shop_name=base_data['shop'], remarks=base_data['desc'], 
                currency=base_data['currency'], finance_record_id=new_record.id
            ))
            link_msg += " + 固定资产"

        # 4.4 其他资产/耗材 (ConsumableItem)
        elif l_type == 'consumable':
            # 计算CNY价值用于日志
            rate = exchange_rate if base_data['currency'] == "JPY" else 1.0
            val_cny = base_data['amount'] * rate
            
            target_item = db.query(ConsumableItem).filter(ConsumableItem.name == link_config['name']).first()
            
            if target_item:
                # 合并
                old_total = target_item.unit_price * target_item.remaining_qty
                new_total = base_data['amount']
                target_item.remaining_qty += link_config['qty']
                if target_item.remaining_qty > 0:
                    target_item.unit_price = (old_total + new_total) / target_item.remaining_qty
                if base_data['shop']: target_item.shop_name = base_data['shop']
                if link_config.get('cat'): target_item.category = link_config['cat']
                
                log_note = f"资产增加(收入): {base_data['desc']}" if is_income else f"购入入库: {base_data['desc']}"
                link_msg += f" + 其他资产库存 (已合并: {target_item.name})"
            else:
                # 新建
                new_con = ConsumableItem(
                    name=link_config['name'], category=link_config.get('cat', '其他'),
                    unit_price=link_config['unit_price'], initial_quantity=link_config['qty'],
                    remaining_qty=link_config['qty'], shop_name=base_data['shop'],
                    remarks=base_data['desc'], currency=base_data['currency'],
                    finance_record_id=new_record.id
                )
                db.add(new_con)
                log_note = f"资产增加(初始): {base_data['desc']}" if is_income else f"初始购入: {base_data['desc']}"
                link_msg += " + 新其他资产库存"
            
            # 记录库存日志
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
        """
        更新流水记录并级联更新
        updates: {date, type, currency, amount_abs, category, desc}
        """
        rec = FinanceService.get_record_by_id(db, record_id)
        if not rec: return False

        # === 修复开始：处理资金回滚与重记 ===
        
        # 1. 回滚旧记录的影响 (Revert old impact)
        # 获取旧币种的资产账户
        old_cash_asset = FinanceService.get_cash_asset(db, rec.currency)
        if old_cash_asset:
            # rec.amount 本身为有符号数（收入为正，支出为负）
            # 回滚操作就是减去这个数值
            old_cash_asset.amount -= rec.amount
        
        # 2. 计算新记录的数据 (Prepare new data)
        new_signed_amount = updates['amount_abs'] if updates['type'] == "收入" else -updates['amount_abs']
        new_currency = updates['currency']

        # 3. 应用新记录的影响 (Apply new impact)
        new_cash_asset = FinanceService.get_cash_asset(db, new_currency)
        if new_cash_asset:
            new_cash_asset.amount += new_signed_amount
        else:
            # 如果该币种账户不存在，则新建
            new_cash_asset = CompanyBalanceItem(
                category="asset", 
                name=f"流动资金({new_currency})", 
                amount=new_signed_amount, 
                currency=new_currency
            )
            db.add(new_cash_asset)
            
        # === 修复结束 ===

        # 4. 更新流水记录本身
        rec.date = updates['date']
        rec.currency = new_currency
        rec.amount = new_signed_amount
        rec.category = updates['category']
        rec.description = updates['desc']
        
        # 5. 级联更新关联表 (保持原有逻辑，增加币种同步)
        # CostItem
        for cost in db.query(CostItem).filter(CostItem.finance_record_id == record_id).all():
            cost.actual_cost = updates['amount_abs']
            cost.remarks = f"{updates['desc']} (已修)"
            # 注意：如果原本是 CostItem，通常不存币种字段(隐含在amount里)或需额外处理，此处保持原逻辑即可
            
        # FixedAsset
        for fa in db.query(FixedAsset).filter(FixedAsset.finance_record_id == record_id).all():
            if fa.quantity > 0: fa.unit_price = updates['amount_abs'] / fa.quantity
            fa.currency = updates['currency'] # 确保关联资产币种也同步修改
            
        # ConsumableItem
        for ci in db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == record_id).all():
            if ci.initial_quantity > 0: ci.unit_price = updates['amount_abs'] / ci.initial_quantity
            ci.currency = updates['currency']
            
        # CompanyBalanceItem (关联的非现金资产)
        for bi in db.query(CompanyBalanceItem).filter(CompanyBalanceItem.finance_record_id == record_id).all():
            bi.amount = updates['amount_abs']
            bi.currency = updates['currency']

        db.commit()
        return True

    @staticmethod
    def delete_record(db, record_id):
        """删除流水并回滚关联数据"""
        rec = FinanceService.get_record_by_id(db, record_id)
        if not rec: return False

        msg_list = []
        # 1. 回滚资金
        cash_asset = FinanceService.get_cash_asset(db, rec.currency)
        if cash_asset: 
            cash_asset.amount -= rec.amount
            msg_list.append("资金已回滚")
        
        # 2. 特殊处理：回滚耗材库存
        if rec.category == "其他资产购入":
            target_log = db.query(ConsumableLog).filter(
                ConsumableLog.date == rec.date,
                ConsumableLog.value_cny >= abs(rec.amount) - 0.1,
                ConsumableLog.value_cny <= abs(rec.amount) + 0.1,
                ConsumableLog.change_qty > 0
            ).first()
            if target_log:
                item = db.query(ConsumableItem).filter(ConsumableItem.name == target_log.item_name).first()
                if item: 
                    item.remaining_qty -= target_log.change_qty
                    msg_list.append(f"库存已扣减 {target_log.change_qty}")
                db.delete(target_log)

        # 3. 级联删除
        db.query(CostItem).filter(CostItem.finance_record_id == record_id).delete()
        db.query(FixedAsset).filter(FixedAsset.finance_record_id == record_id).delete()
        db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == record_id).delete()
        db.query(CompanyBalanceItem).filter(CompanyBalanceItem.finance_record_id == record_id).delete()
        
        # 4. 删除本身
        db.delete(rec)
        db.commit()
        return " | ".join(msg_list)
