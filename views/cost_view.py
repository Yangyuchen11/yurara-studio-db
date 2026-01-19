import streamlit as st
import pandas as pd
from datetime import date
from models import Product, CostItem, FinanceRecord, CompanyBalanceItem, InventoryLog

def show_cost_page(db):
    st.header("🧵 商品成本核算")
    
    # === 0. 全局设置 ===
    exchange_rate_input = st.session_state.get("global_rate_input", 4.8)
    exchange_rate = exchange_rate_input / 100.0

    # 1. 选择商品
    products = db.query(Product).all()
    if not products:
        st.warning("请先在“产品管理”中添加产品！")
        return

    product_names = [p.name for p in products]
    selected_prod_name = st.selectbox("请选择要核算的商品", product_names)
    prod = db.query(Product).filter(Product.name == selected_prod_name).first()
    
    # 使用持久化的可销售数量
    make_qty = prod.marketable_quantity if prod.marketable_quantity is not None else prod.total_quantity
    
    st.divider()

    # ================= 1. 添加预算功能 (数据录入区) =================
    with st.expander("➕ 添加预算项目 (Budget)", expanded=False):
        st.caption("在此处录入的条目仅作为预算参考，实付金额默认为0。")
        
        detailed_cats = ["大货材料费", "大货加工费", "物流邮费", "包装费"]
        simple_cats = ["设计开发费", "检品发货等人工费", "宣发费", "其他成本"]
        all_cats = detailed_cats + simple_cats
        
        c_cat, c_name = st.columns([1, 1.5])
        b_cat = c_cat.selectbox("预算分类", all_cats, key="budget_cat_select")
        b_name = c_name.text_input("项目名称", placeholder="如：面料预算", key="budget_name_input")
        
        b_unit_price = 0.0
        b_qty = 1.0
        b_unit_text = ""
        b_remarks = ""
        
        if b_cat in detailed_cats:
            c1_b, c2_b, c3_b = st.columns([1, 1, 1])
            
            b_price_input = c1_b.number_input("预算单价", min_value=0.0, step=0.01, format="%.2f", key="b_p_in")
            b_qty_input = c2_b.number_input("预算数量", min_value=0.01, step=0.01, value=1.0, format="%.2f", key="b_q_in")
            b_unit_text = c3_b.text_input("单位", placeholder="米/个/件", key="b_u_in")
            
            st.markdown(f"**💰 预算总价: ¥ {b_price_input * b_qty_input:,.2f}**")
            b_unit_price = b_price_input
            b_qty = b_qty_input
        else:
            b_total_input = st.number_input("预算总价", min_value=0.0, step=100.0, format="%.2f", key="b_t_in")
            b_unit_price = b_total_input
            b_qty = 1.0

        b_remarks = st.text_input("备注", placeholder="选填", key="b_r_in")

        if st.button("保存预算", type="primary"):
            if not b_name:
                st.error("请输入项目名称")
            else:
                new_cost = CostItem(
                    product_id=prod.id,
                    item_name=b_name,
                    actual_cost=0,      
                    supplier="预算设定", 
                    category=b_cat,
                    unit_price=b_unit_price, 
                    quantity=b_qty,          
                    unit=b_unit_text,
                    remarks=b_remarks
                )
                db.add(new_cost)
                db.commit()
                st.toast("预算已添加", icon="✅")
                st.rerun()

    # 获取当前商品的所有成本项
    all_items = db.query(CostItem).filter(CostItem.product_id == prod.id).all()
    
    # 布局：左侧表格，右侧总览
    c1, c2 = st.columns([3.5, 1.2]) 
    
    # ================= 左侧：支出明细表 (可编辑) =================
    with c1:
        st.subheader("📋 支出明细表")
        
        has_data = False
        
        # 遍历每一个分类显示表格
        for cat in all_cats:
            cat_items = [i for i in all_items if i.category == cat or (cat=="检品发货等人工费" and "检品" in i.category)]
            
            if cat_items:
                has_data = True
                st.markdown(f"#### 🔹 {cat}")
                
                # --- 准备表格数据 ---
                data_list = []
                delete_options = {}
                
                for i in cat_items:
                    is_budget_item = (i.supplier == "预算设定")
                    
                    budget_qty = i.quantity if is_budget_item else None
                    budget_unit_price = i.unit_price if is_budget_item else None
                    budget_total = (i.unit_price * i.quantity) if is_budget_item else None
                    
                    actual_qty = i.quantity if not is_budget_item else None
                    actual_total = i.actual_cost
                    actual_unit_price = 0.0
                    if not is_budget_item and i.quantity > 0:
                        actual_unit_price = i.actual_cost / i.quantity
                    actual_unit_price_disp = actual_unit_price if not is_budget_item else None

                    row = {
                        "_id": i.id,
                        "支出内容": i.item_name,
                        "单位": i.unit or "",
                        # 预算部分
                        "预算数量": budget_qty or 0,
                        "预算单价": budget_unit_price or 0,
                        "预算总价": budget_total or 0,
                        
                        # 实付部分
                        "实际数量": actual_qty or 0,
                        "实付单价": actual_unit_price_disp or 0,
                        "实付总价": actual_total or 0,
                        
                        "供应商": i.supplier or "",
                        "备注": i.remarks or "",
                        
                        "_is_budget": is_budget_item
                    }
                    data_list.append(row)
                    
                    option_label = f"{i.item_name} | ￥{i.actual_cost} ({i.supplier or '未填'})"
                    delete_options[option_label] = i.id
                
                df = pd.DataFrame(data_list)

                # 强制转为数值类型
                numeric_cols = ["预算数量", "预算单价", "预算总价", "实际数量", "实付单价", "实付总价"]
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                # --- 渲染可编辑表格 ---
                # 【修改点】: 调整 enabled 逻辑，允许更多列可编辑
                
                if cat in detailed_cats:
                    col_order = ["支出内容", "单位", "预算数量", "预算单价", "预算总价", "实际数量", "实付单价", "实付总价", "供应商", "备注"]
                    
                    edited_df = st.data_editor(
                        df,
                        key=f"editor_{cat}_{prod.id}",
                        column_order=col_order,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "_id": None,
                            "_is_budget": None,
                            "支出内容": st.column_config.TextColumn(disabled=True),
                            
                            # 详细模式：允许编辑 单位、数量、单价、供应商、备注
                            "单位": st.column_config.TextColumn(), 
                            "预算数量": st.column_config.NumberColumn(min_value=0.0, step=0.01, format="%.2f"),
                            "预算单价": st.column_config.NumberColumn(min_value=0.0, step=0.01, format="¥ %.2f"),
                            "预算总价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True), # 自动计算，禁止编辑
                            
                            "实际数量": st.column_config.NumberColumn(format="%.2f", disabled=True),
                            "实付单价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                            "实付总价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                            
                            "供应商": st.column_config.TextColumn(),
                            "备注": st.column_config.TextColumn(),
                        }
                    )
                else:
                    # 简易模式
                    col_order = ["支出内容", "预算总价", "实付总价", "供应商", "备注"] 
                    
                    edited_df = st.data_editor(
                        df,
                        key=f"editor_{cat}_{prod.id}",
                        column_order=col_order,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "_id": None,
                            "_is_budget": None,
                            "支出内容": st.column_config.TextColumn(disabled=True),
                            
                            # 简易模式：允许编辑 预算总价、供应商、备注
                            "预算总价": st.column_config.NumberColumn(min_value=0.0, step=10.0, format="¥ %.2f"),
                            "实付总价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                            
                            "供应商": st.column_config.TextColumn(),
                            "备注": st.column_config.TextColumn(),
                        }
                    )

                # --- 处理编辑保存 ---
                for index, row in edited_df.iterrows():
                    item_id = row["_id"]
                    is_budget = row["_is_budget"]
                    target_item = db.query(CostItem).filter(CostItem.id == item_id).first()
                    
                    if target_item:
                        has_change = False
                        
                        # 通用字段更新
                        if row.get("单位") is not None and row.get("单位") != (target_item.unit or ""):
                            target_item.unit = row.get("单位"); has_change = True
                            
                        if row.get("供应商") is not None and row.get("供应商") != (target_item.supplier or ""):
                            target_item.supplier = row.get("供应商"); has_change = True
                            
                        if row.get("备注") is not None and row.get("备注") != (target_item.remarks or ""):
                            target_item.remarks = row.get("备注"); has_change = True
                        
                        # 预算数值更新 (仅预算条目)
                        if is_budget:
                            if cat in detailed_cats:
                                # 详细模式：通过 数量 和 单价 更新
                                new_qty = float(row.get("预算数量") or 0) if pd.notna(row.get("预算数量")) else 0.0
                                if abs(new_qty - target_item.quantity) > 0.001:
                                    target_item.quantity = new_qty; has_change = True
                                    
                                new_price = float(row.get("预算单价") or 0) if pd.notna(row.get("预算单价")) else 0.0
                                if abs(new_price - target_item.unit_price) > 0.01:
                                    target_item.unit_price = new_price; has_change = True
                            else:
                                # 简易模式：通过 预算总价 更新 (反算 Unit Price, Qty 保持 1)
                                new_total = float(row.get("预算总价") or 0) if pd.notna(row.get("预算总价")) else 0.0
                                # 比较当前的总价 (unit_price * quantity)
                                current_total = target_item.unit_price * target_item.quantity
                                if abs(new_total - current_total) > 0.01:
                                    # 简易模式下 quantity 通常为 1，直接更新 unit_price
                                    target_item.unit_price = new_total
                                    target_item.quantity = 1.0
                                    has_change = True
                        
                        if has_change:
                            db.commit()
                            st.toast(f"已更新: {target_item.item_name}", icon="💾")

                # --- 删除功能 ---
                c_del_sel, c_del_btn = st.columns([3, 1])
                selected_del_label = c_del_sel.selectbox("选择要删除的项目", options=list(delete_options.keys()), key=f"sel_del_{cat}", label_visibility="collapsed", index=None, placeholder="选择要删除的项目...")
                
                if selected_del_label:
                    with c_del_btn.popover("🗑️ 删除", use_container_width=True):
                        st.markdown(f"确认删除 `{selected_del_label.split('|')[0].strip()}` ？")
                        if st.button("🔴 确认", key=f"btn_confirm_del_{cat}", type="primary"):
                            del_id = delete_options[selected_del_label]
                            item_to_del = db.query(CostItem).filter(CostItem.id == del_id).first()
                            if item_to_del:
                                # === 【修改开始】 ===
                                if item_to_del.finance_record_id:
                                    fin_rec = db.query(FinanceRecord).filter(FinanceRecord.id == item_to_del.finance_record_id).first()
                                    if fin_rec:
                                        # 1. 恢复资金 (回滚流动资金)
                                        # 支出在 FinanceRecord 中是负数，所以我们要减去这个负数（即加上绝对值），或者直接用 -=
                                        # 这里为了逻辑清晰：我们需要把钱“加回去”
                                        restore_amount = abs(fin_rec.amount) 
                                        restore_currency = fin_rec.currency
                                        
                                        # 查找对应的流动资金账户
                                        cash_asset = db.query(CompanyBalanceItem).filter(
                                            CompanyBalanceItem.name.like("流动资金%"),
                                            CompanyBalanceItem.currency == restore_currency,
                                            CompanyBalanceItem.category == "asset"
                                        ).first()
                                        
                                        if cash_asset:
                                            cash_asset.amount += restore_amount
                                            st.toast(f"已回滚资金: {restore_amount} {restore_currency}", icon="💸")
                                        
                                        # 2. 标记流水为已冲销
                                        fin_rec.amount = 0
                                        fin_rec.category = "取消/冲销"
                                        fin_rec.description = f"【已取消成本】{fin_rec.description}"
                                
                                # 3. 删除成本项
                                db.delete(item_to_del)
                                db.commit()
                                st.rerun()

                # 1. 计算小计实付 (所有项目的 actual_cost 之和)
                cat_total_real = sum([i.actual_cost for i in cat_items])

                # 2. 计算小计预算 (混合逻辑：优先预算，无预算则取实付)
                cat_budget_map = {}
                
                # A. 先提取该分类下所有的“显式预算”
                for i in cat_items:
                    if i.supplier == "预算设定":
                        # 如果有重复名字的预算，累加金额
                        current_val = i.unit_price * i.quantity
                        cat_budget_map[i.item_name] = cat_budget_map.get(i.item_name, 0) + current_val
                
                cat_total_budget = sum(cat_budget_map.values())

                # B. 遍历“实付项”，填补没有预算的空缺
                for i in cat_items:
                    if i.supplier != "预算设定":
                        # 如果这个项目名称不在预算表里，说明是计划外支出，预算额 = 实付额
                        if i.item_name not in cat_budget_map:
                            cat_total_budget += i.actual_cost

                # 3. 计算单价 (使用 make_qty)
                cat_unit_real = cat_total_real / make_qty if make_qty > 0 else 0
                cat_unit_budget = cat_total_budget / make_qty if make_qty > 0 else 0

                # 4. 四列展示
                sub_c1, sub_c2, sub_c3, sub_c4 = st.columns(4)
                
                sub_c1.caption(f"**小计实付**: ¥ {cat_total_real:,.2f}")
                sub_c2.caption(f"实付单价: ¥ {cat_unit_real:,.2f}")
                
                sub_c3.caption(f"**小计预算**: ¥ {cat_total_budget:,.2f}")
                sub_c4.caption(f"预算单价: ¥ {cat_unit_budget:,.2f}")
                
                st.divider()

        if not has_data:
            st.info("该商品暂无支出或预算记录。")

    # ================= 右侧：总核算结果 =================
    with c2:
        with st.container(border=True):
            st.subheader("📊 核算面板")
            
            # --- 计算实付总成本 ---
            total_real_cost = sum([i.actual_cost for i in all_items])
            
            # --- 计算预算总成本 ---
            budget_map = {} 
            for i in all_items:
                if i.supplier == "预算设定":
                    budget_map[i.item_name] = i.unit_price * i.quantity
            total_budget_cost = sum(budget_map.values())
            for i in all_items:
                if i.supplier != "预算设定":
                    if i.item_name not in budget_map:
                        total_budget_cost += i.actual_cost

            # --- 显示总支出 ---
            st.metric("📦 项目总支出 (实付)", f"¥ {total_real_cost:,.2f}")
            st.caption(f"📝 预算总成本: ¥ {total_budget_cost:,.2f}")
            
            st.divider()

            # 显示可销售数量
            st.metric("🔢 预计可销售数量", f"{int(make_qty)} 件", help="此数值通过库存变动（消耗、损耗、增产）自动更新。")
            
            st.divider()
            
            # --- 计算单件成本 ---
            if make_qty > 0:
                unit_real_cost = total_real_cost / make_qty
                unit_budget_cost = total_budget_cost / make_qty
                
                st.metric("💰 单套综合成本 (实付)", f"¥ {unit_real_cost:,.2f}")
                st.caption(f"📝 预算单套成本: ¥ {unit_budget_cost:,.2f}")
                
                st.divider()
                st.markdown("**📈 各平台毛利参考 (基于实付)**")
                
                platforms_config = [
                    ("price_weidian", "微店 (CNY)", False),
                    ("price_offline_cn", "中国线下 (CNY)", False),
                    ("price_other", "其他 (CNY)", False),
                    ("price_booth", "Booth (JPY)", True),
                    ("price_instagram", "Instagram (JPY)", True),
                    ("price_offline_jp", "日本线下 (JPY)", True),
                    ("price_other_jpy", "其他 (JPY)", True),
                ]

                has_platform_price = False
                for field, label, is_jpy in platforms_config:
                    price_val = getattr(prod, field, 0)
                    
                    if price_val > 0:
                        has_platform_price = True
                        price_cny = price_val * exchange_rate if is_jpy else price_val
                        margin = price_cny - unit_real_cost
                        margin_rate = (margin / price_cny * 100) if price_cny > 0 else 0
                        
                        with st.expander(f"{label}", expanded=True):
                            if is_jpy:
                                st.caption(f"定价: {price_val:,.0f} JPY")
                            
                            st.metric(
                                label="单件毛利", 
                                value=f"¥ {margin:,.2f}", 
                                delta=f"{margin_rate:.1f}%",
                                delta_color="normal" if margin > 0 else "inverse"
                            )
                            total_profit = margin * make_qty
                            st.caption(f"总预期毛利: ¥ {total_profit:,.2f}")

                if not has_platform_price:
                    st.caption("暂未在商品管理中设置任何平台价格")

            else:
                st.error("⚠️ 预计数量为 0，请调整数量以计算成本。")

    # ================= 5. 强制结单/修正功能 (新增模块) =================

    with st.expander("🛠️ 生产结单 / 账目修正 (高级)", expanded=False):
        st.warning("⚠️ **功能说明**：如果该商品已经生产完成，但在【公司资产一览】中仍显示有“在制资产”余额，请点击下方按钮。系统将重新计算所有成本，并强制将账面上的在制资产归零。")
        
        # 计算当前的在制资产净值 (WIP Net)
        # 1. 计算总实付成本
        current_total_cost = sum([i.actual_cost for i in all_items])
        
        # 2. 获取当前的冲销额
        offset_name = f"在制资产冲销-{prod.name}"
        offset_item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == offset_name).first()
        current_offset = offset_item.amount if offset_item else 0.0
        
        # 3. 计算残留 WIP
        remaining_wip = current_total_cost + current_offset # 冲销额通常是负数
        
        c_fix1, c_fix2 = st.columns([2, 1])
        c_fix1.metric("当前残留 WIP (应为0)", f"¥ {remaining_wip:,.2f}")
        
        # 【修改版】强制修正 + 同步大货资产
        if c_fix2.button("🚀 强制修正 + 同步大货资产", type="primary"):
            try:
                # --- 步骤 A: 计算追加的成本差额 ---
                old_accounted_cost = abs(current_offset)
                added_cost_value = current_total_cost - old_accounted_cost

                # --- 步骤 B: 自动更新“大货资产”并记录流水 ---
                if abs(added_cost_value) > 0.01:
                    inventory_asset_name = f"大货资产-{prod.name}"
                    inv_item = db.query(CompanyBalanceItem).filter(
                        CompanyBalanceItem.name == inventory_asset_name,
                        CompanyBalanceItem.category == "asset"
                    ).first()

                    if inv_item:
                        inv_item.amount += added_cost_value
                        st.toast(f"已自动调整大货资产: {added_cost_value:+.2f}", icon="📦")
                    else:
                        new_inv = CompanyBalanceItem(
                            name=inventory_asset_name,
                            amount=added_cost_value,
                            category="asset",
                            currency="CNY"
                        )
                        db.add(new_inv)
                        st.toast(f"已自动创建大货资产: {added_cost_value:+.2f}", icon="✨")
                    
                    # 【新增】记录一条虚拟流水，保证账目有据可查
                    fix_rec = FinanceRecord(
                        date=date.today(),
                        amount=0, # 不涉及现金变动，所以金额为0，仅做资产调整记录
                        currency="CNY",
                        category="成本结转",
                        description=f"【{prod.name}】追加成本结转: 将 {added_cost_value:.2f} 从在制转入大货资产"
                    )
                    db.add(fix_rec)

                # --- 步骤 C: 更新冲销项 (让 WIP 归零) ---
                target_offset = -current_total_cost
                
                if not offset_item:
                    offset_item = CompanyBalanceItem(
                        name=offset_name, 
                        amount=target_offset, 
                        category="asset", 
                        currency="CNY" 
                    )
                    db.add(offset_item)
                else:
                    offset_item.amount = target_offset
                
                # --- 步骤 D: 清理残留 ---
                pre_stock_name = f"预入库大货资产-{prod.name}"
                db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == pre_stock_name).delete()
                
                db.commit()
                st.success(f"修正完成！追加成本 {added_cost_value:,.2f} 已结转。")
                st.rerun()
                
            except Exception as e:
                db.rollback()
                st.error(f"修正失败: {e}")

        st.markdown("---")
        st.subheader("⚖️ 库存价值重估 (Revaluation)")
        st.caption("当单价因追加成本或调整可售数量发生剧烈变化时，使用此功能将账面资产价值同步为 [剩余数量 × 当前单价]。")

        # 1. 获取当前库存数量 (修正版：只计算实物库存)
        current_stock_qty = 0
        stock_logs = db.query(InventoryLog).filter(InventoryLog.product_name == prod.name).all()
        
        # 【关键修正】定义哪些操作属于“实物”变动，排除“预入库”
        # 对应 Inventory View 中的 real_stock_map 逻辑
        real_stock_reasons = ["入库", "出库", "额外生产入库", "退货入库", "发货撤销"]
        
        for l in stock_logs:
            if l.reason in real_stock_reasons:
                current_stock_qty += l.change_amount
        
        # 2. 获取大货资产当前余额
        inventory_asset_name = f"大货资产-{prod.name}"
        inv_item = db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.name == inventory_asset_name,
            CompanyBalanceItem.category == "asset"
        ).first()
        current_inv_val = inv_item.amount if inv_item else 0.0

        # 3. 计算理论目标值
        # 理论值 = 库存数量 * 当前核算单价
        target_inv_val = current_stock_qty * unit_real_cost
        
        # 4. 计算差额
        reval_diff = target_inv_val - current_inv_val

        # 5. 显示面板
        c_rv1, c_rv2, c_rv3 = st.columns(3)
        c_rv1.metric("当前实际库存", f"{current_stock_qty} 件")
        c_rv2.metric("当前账面价值", f"¥ {current_inv_val:,.2f}")
        c_rv3.metric("目标重估价值", f"¥ {target_inv_val:,.2f}", help=f"计算公式: {current_stock_qty} * {unit_real_cost:.2f}")

        if abs(reval_diff) > 1.0:
            st.info(f"💡 检测到价值偏差: ¥ {reval_diff:+,.2f}")
            
            if st.button("🔄 执行资产重估 / 补差", type="secondary"):
                try:
                    # 1. 更新大货资产
                    if inv_item:
                        inv_item.amount += reval_diff
                    else:
                        inv_item = CompanyBalanceItem(
                            name=inventory_asset_name,
                            amount=reval_diff,
                            category="asset",
                            currency="CNY"
                        )
                        db.add(inv_item)
                    
                    # 2. 记录一条调整流水，保证账目可追溯
                    # 注意：这笔钱通常视为“成本调整”或“未分配损益”，这里为了平衡，我们不额外动现金，
                    # 而是记录一笔虚拟的“资产增值/减值”记录。
                    reval_rec = FinanceRecord(
                        date=date.today(),
                        amount=0, # 不涉及现金变动
                        currency="CNY",
                        category="库存重估",
                        description=f"【{prod.name}】资产重估补差: 从 {current_inv_val:.2f} 调整为 {target_inv_val:.2f} (差额 {reval_diff:.2f})"
                    )
                    db.add(reval_rec)
                    
                    # 如果这笔差额非常大，也可以选择创建一个“成本调整”的负债项或资本项来平衡，
                    # 但为了简化，这里直接修改资产余额（类似于存货升值/贬值处理）。
                    
                    db.commit()
                    st.success("重估完成！账面资产已与最新单价对齐。")
                    st.rerun()
                except Exception as e:
                    db.rollback()
                    st.error(f"重估失败: {e}")
        else:
            st.success("✅ 账面价值与理论价值一致，无需重估。")