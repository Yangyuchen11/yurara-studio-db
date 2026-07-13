import os
import sys
from database import SessionLocal
from models import FinanceRecord, FixedAsset, ConsumableItem, Product, InventoryLog, CostItem
import pandas as pd

def get_discrepancies():
    db = SessionLocal()
    rates = {'CNY': 1.0, 'JPY': 0.05} # rough approximation
    
    # 1. Simulate items_map (curr_val)
    items_map = {"fixed": {}, "consumable": {}, "wip": {}, "stock": {}, "other": {}}
    
    fixed_assets = db.query(FixedAsset).all()
    consumables = db.query(ConsumableItem).all()
    for fa in fixed_assets:
        items_map["fixed"][fa.name] = items_map["fixed"].get(fa.name, 0.0) + fa.unit_price * fa.remaining_qty
    for c in consumables:
        items_map["consumable"][c.name] = items_map["consumable"].get(c.name, 0.0) + c.unit_price * c.remaining_qty
        
    # WIP
    prods = db.query(Product).all()
    for prod in prods:
        total_cost = sum([c.actual_cost for c in db.query(CostItem).filter_by(product_id=prod.id)])
        # simplified curr_val for WIP
        if prod.is_production_completed:
            wip_val = 0.0
        else:
            wip_val = total_cost # approximation
        items_map["wip"][prod.name] = wip_val
        
        # stock curr_val
        # we will skip precise stock curr_val for this debug script, just want to see the sums
        
    # 2. Simulate ALL_TIME_SUM (past_chg)
    all_time = {"fixed": {}, "consumable": {}, "wip": {}, "stock": {}, "other": {}}
    
    records = db.query(FinanceRecord).all()
    for r in records:
        cat = r.category
        desc = (r.description or "").lower()
        equiv = r.amount * (rates.get(r.currency, 1.0))
        nc_cat = None
        nc_change = 0.0
        if cat in ["固定资产购入", "其他资产购入", "商品成本"]:
            nc_change = -equiv
            if cat == "固定资产购入": nc_cat = "fixed"
            elif cat == "其他资产购入": nc_cat = "consumable"
            else: nc_cat = "wip"
        elif cat in ["现有资产增加", "新资产增加", "其他资产增加", "现有资产减少", "资产抵消"]:
            nc_change = equiv
            if "固定" in desc: nc_cat = "fixed"
            elif "耗材" in desc or "物料" in desc: nc_cat = "consumable"
            elif "在制" in desc or "在研" in desc or "wip" in desc: nc_cat = "wip"
            elif "大货" in desc or "商品" in desc or "库存" in desc or "存货" in desc: nc_cat = "stock"
            else: nc_cat = "other"
            
        if nc_cat:
            matched_item = None
            for name in items_map[nc_cat].keys():
                clean = name.replace("大货资产-", "").replace("流动资金-", "").strip().lower()
                if clean and (clean in desc or clean in cat.lower()):
                    matched_item = name; break
            if not matched_item: matched_item = "其他未分类资产"
            all_time[nc_cat][matched_item] = all_time[nc_cat].get(matched_item, 0.0) + nc_change

    print("=== DISCREPANCIES ===")
    for cat in all_time:
        for name in all_time[cat]:
            sum_val = all_time[cat][name]
            curr_val = items_map[cat].get(name, 0.0)
            diff = curr_val - sum_val
            if abs(diff) > 100:
                print(f"[{cat}] {name}: curr={curr_val:.2f}, sum={sum_val:.2f}, diff={diff:.2f}")

get_discrepancies()

    print('---')
    for cat in all_time:
        for name in all_time[cat]:
            sum_val = all_time[cat][name]
            curr_val = items_map[cat].get(name, 0.0)
            diff = curr_val - sum_val
            if abs(diff) > 100:
                print(f'[{cat}] {repr(name)}: curr={curr_val:.2f}, sum={sum_val:.2f}, diff={diff:.2f}')
