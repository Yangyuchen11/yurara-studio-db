import streamlit as st
import pandas as pd
from datetime import date
from models import FinanceRecord, Product, CostItem, ConsumableItem, FixedAsset, ConsumableLog, CompanyBalanceItem

def show_finance_page(db, exchange_rate):
    st.header("💰 财务资金流水")
    
    # ================= 1. 新增记录区域 =================
    with st.expander("➕ 新增收支/兑换/债务记录", expanded=True):
        r1_c1, r1_c2, r1_c3 = st.columns([1, 1, 1])
        f_date = r1_c1.date_input("日期", date.today())
        
        # 收支类型
        rec_type = r1_c2.selectbox("业务类型", ["支出", "收入", "货币兑换", "债务"])

        # 初始化通用变量
        f_curr = "CNY"
        f_name = ""
        f_shop = ""
        final_category = ""
        calc_total_amount = 0.0 
        f_qty = 1
        f_price = 0.0 
        f_desc = ""
        
        # 联动标记
        selected_product_id = None
        target_consumable_id = None
        is_consumable_append = False
        target_balance_item_id = None
        is_new_balance_item = False
        balance_item_type = None 

        # =======================================================
        # >>>>> 场景 C: 货币兑换 (保持不变) <<<<<
        # =======================================================
        if rec_type == "货币兑换":
            with r1_c3:
                source_curr = st.selectbox("源币种 (支出)", ["CNY", "JPY"])
            target_curr = "JPY" if source_curr == "CNY" else "CNY"
            st.info(f"💱 兑换方向: {source_curr} ➡️ {target_curr}")
            
            c_ex1, c_ex2 = st.columns(2)
            amount_out = c_ex1.number_input(f"支出金额 ({source_curr})", min_value=0.0, step=100.0, format="%.2f")
            
            est_val = 0.0
            if amount_out > 0:
                if source_curr == "CNY": est_val = amount_out / exchange_rate 
                else: est_val = amount_out * exchange_rate 
            
            amount_in = c_ex2.number_input(f"入账金额 ({target_curr})", value=est_val, min_value=0.0, step=100.0, format="%.2f", help="默认为估算值，请填入实际到账金额")
            f_desc = st.text_input("备注说明", placeholder="如：支付宝购汇 / 银行提现")
            
            if st.button("💾 确认兑换", type="primary"):
                if amount_out <= 0 or amount_in <= 0:
                    st.warning("金额必须大于0")
                else:
                    try:
                        rec_out = FinanceRecord(
                            date=f_date, amount=-amount_out, currency=source_curr,
                            category="货币兑换", description=f"兑换支出 (-> {target_curr}) | {f_desc}"
                        )
                        db.add(rec_out)
                        rec_in = FinanceRecord(
                            date=f_date, amount=amount_in, currency=target_curr,
                            category="货币兑换", description=f"兑换入账 (<- {source_curr}) | {f_desc}"
                        )
                        db.add(rec_in)
                        db.commit()
                        st.toast(f"兑换成功：-{amount_out}{source_curr}, +{amount_in}{target_curr}", icon="💱")
                        st.rerun()
                    except Exception as e:
                        st.error(f"兑换失败: {e}")

        # =======================================================
        # >>>>> 场景 D: 债务管理 (核心修改) <<<<<
        # =======================================================
        elif rec_type == "债务":
            with r1_c3:
                f_curr = st.selectbox("币种", ["CNY", "JPY"])

            # 债务操作类型
            debt_op = st.radio("债务操作", ["➕ 新增债务 (借入)", "💸 偿还/核销债务"], horizontal=True)
            st.divider()

            # --- 1. 新增债务 ---
            if "新增" in debt_op:
                c_type1, c_type2 = st.columns([1, 2])
                # 【修改点】选择借款去向
                fund_dest = c_type1.selectbox("资金去向", ["存入流动资金", "新增资产项"])
                
                c_d1, c_d2 = st.columns(2)
                new_debt_name = c_d1.text_input("债务名称", placeholder="如：银行贷款 / 欠款采购")
                
                # 根据去向显示不同输入框
                if fund_dest == "存入流动资金":
                    related_content = c_d2.text_input("入账说明", placeholder="如：贷款现金入账")
                    help_msg = "此操作会：1.增加负债 2.增加账面流动资金 (产生收入流水)"
                else:
                    related_content = c_d2.text_input("新增资产名称", placeholder="如：未付款的设备 / 赊账原料")
                    help_msg = "此操作会：1.增加负债 2.创建一个新的资产项目 (资产金额与债务一致)。不会增加流动资金。"

                st.caption(f"ℹ️ {help_msg}")

                c_d3, c_d4 = st.columns(2)
                debt_source = c_d3.text_input("债务来源/债权人", placeholder="债权人/机构")
                debt_amount = c_d4.number_input("金额", min_value=0.0, step=100.0, format="%.2f")
                debt_remark = st.text_input("备注说明")

                if st.button("💾 确认新增债务", type="primary"):
                    if not new_debt_name or not related_content:
                        st.error("请填写完整名称和说明")
                    elif debt_amount <= 0:
                        st.error("金额必须大于0")
                    else:
                        try:
                            # 1. 创建 财务流水 (FinanceRecord)
                            # 如果是流动资金 -> 记为收入 (Amount > 0)
                            # 如果是新增资产 -> 记为 0 (仅作为日志，不影响 Cash), 或者用特殊标记
                            
                            finance_rec = None
                            
                            if fund_dest == "存入流动资金":
                                finance_rec = FinanceRecord(
                                    date=f_date,
                                    amount=debt_amount, # 正数，增加现金
                                    currency=f_curr,
                                    category="借入资金",
                                    description=f"{related_content} (来源: {debt_source}) | {debt_remark}"
                                )
                            else:
                                # 新增资产项：不增加流动资金，所以金额记为0，但在描述中备注
                                finance_rec = FinanceRecord(
                                    date=f_date,
                                    amount=0, # 不影响现金流
                                    currency=f_curr,
                                    category="债务-资产形成",
                                    description=f"【资产债务】新增资产: {related_content} | 债务: {new_debt_name} | 金额: {debt_amount}"
                                )
                            
                            db.add(finance_rec)
                            db.flush() # 获取 ID

                            # 2. 创建 负债项目 (Liability)
                            new_liability = CompanyBalanceItem(
                                name=new_debt_name,
                                amount=debt_amount, 
                                category="liability",
                                currency=f_curr,
                                finance_record_id=finance_rec.id
                            )
                            db.add(new_liability)

                            # 3. 如果是新增资产 -> 创建 资产项目 (Asset)
                            if fund_dest == "新增资产项":
                                new_asset = CompanyBalanceItem(
                                    name=related_content,
                                    amount=debt_amount, # 资产价值 = 债务金额
                                    category="asset",
                                    currency=f_curr,
                                    finance_record_id=finance_rec.id
                                )
                                db.add(new_asset)
                            
                            db.commit()
                            st.toast(f"债务记录成功: {new_debt_name}", icon="📝")
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存失败: {e}")

            # --- 2. 偿还/核销债务 ---
            else:
                liabilities = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == 'liability').all()
                if not liabilities:
                    st.warning("暂无债务")
                else:
                    liab_map = {f"{l.name} (余额: {l.amount:,.2f} {l.currency})": l for l in liabilities}
                    selected_label = st.selectbox("选择要处理的债务", list(liab_map.keys()))
                    target_liab = liab_map[selected_label]
                    
                    st.divider()
                    
                    # 【修改点】偿还方式选择
                    repay_type = st.radio("偿还/处理方式", ["💸 资金还款 (减少流动资金)", "🔄 资产抵消/退还 (删除对应资产)"])
                    
                    if "资金还款" in repay_type:
                        st.caption("ℹ️ 使用公司现金偿还债务。操作将：1.减少流动资金 2.减少/删除债务。")
                        c_r1, c_r2 = st.columns(2)
                        repay_amount = c_r1.number_input("偿还金额", min_value=0.0, max_value=target_liab.amount, step=100.0, format="%.2f")
                        repay_remark = c_r2.text_input("备注")
                        
                        if st.button("💾 确认资金还款", type="primary"):
                            if repay_amount <= 0:
                                st.error("金额必须大于0")
                            else:
                                try:
                                    # 1. 记一笔支出 (减少现金)
                                    new_finance = FinanceRecord(
                                        date=f_date,
                                        amount=-repay_amount, 
                                        currency=target_liab.currency,
                                        category="债务偿还",
                                        description=f"资金偿还: {target_liab.name} | {repay_remark}"
                                    )
                                    db.add(new_finance)
                                    
                                    # 2. 减少债务
                                    target_liab.amount -= repay_amount
                                    
                                    # 如果还清，是否删除？这里逻辑是金额归零即可，也可以选择物理删除
                                    if target_liab.amount <= 0.01: # 浮点数容错
                                        db.delete(target_liab)
                                        st.toast("债务已还清并销账", icon="✅")
                                    else:
                                        st.toast(f"已还款: {repay_amount}", icon="💸")
                                        
                                    db.commit()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"操作失败: {e}")
                                    
                    else:
                        st.caption("ℹ️ 通过退还资产或资产抵债来消除债务。操作将：1.删除指定的资产项 2.删除/减少债务。**不会减少流动资金**。")
                        
                        # 获取现有资产供选择
                        assets = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == 'asset').all()
                        asset_map = {f"{a.name} (价值: {a.amount:,.2f})": a for a in assets}
                        
                        c_ra1, c_ra2 = st.columns(2)
                        if not asset_map:
                            st.warning("暂无资产可抵消")
                            st.stop()
                            
                        sel_asset_label = c_ra1.selectbox("选择对应的资产", list(asset_map.keys()))
                        target_asset = asset_map[sel_asset_label]
                        
                        offset_amount = c_ra2.number_input("抵消/核销金额", value=min(target_liab.amount, target_asset.amount), min_value=0.0, step=100.0)
                        offset_remark = st.text_input("备注", placeholder="如：退货销账 / 资产抵债")
                        
                        if st.button("💾 确认资产抵消", type="primary"):
                             try:
                                # 1. 记录日志 (金额为0，不影响现金，但记录事件)
                                new_finance = FinanceRecord(
                                    date=f_date,
                                    amount=0, 
                                    currency=target_liab.currency,
                                    category="债务-资产核销",
                                    description=f"资产抵消: 用 [{target_asset.name}] 抵消 [{target_liab.name}] | 金额: {offset_amount} | {offset_remark}"
                                )
                                db.add(new_finance)
                                
                                # 2. 扣减/删除 资产
                                target_asset.amount -= offset_amount
                                if target_asset.amount <= 0.01:
                                    db.delete(target_asset)
                                
                                # 3. 扣减/删除 债务
                                target_liab.amount -= offset_amount
                                if target_liab.amount <= 0.01:
                                    db.delete(target_liab)
                                    
                                db.commit()
                                st.toast(f"资产抵消完成，金额: {offset_amount}", icon="🔄")
                                st.rerun()
                             except Exception as e:
                                st.error(f"操作失败: {e}")

        # =======================================================
        # >>>>> 场景 A & B: 普通收入/支出 (已移除借款和债务选项) <<<<<
        # =======================================================
        else:
            with r1_c3:
                f_curr = st.selectbox("币种", ["CNY", "JPY"])

            # -------------------------------------------------------
            # >>>>> 场景 A: 收入录入 <<<<<
            # -------------------------------------------------------
            if rec_type == "收入":
                income_cats = ["销售收入", "退款", "投资", "现有资产增加", "新资产增加", "其他现金收入"]
                final_category = st.selectbox("收入分类", income_cats)
                
                # ... (投资/现有资产增加/新资产增加/其他 的逻辑保持不变) ...
                # === 特殊场景：投资 (资本增加) ===
                if final_category == "投资":
                    equities = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == 'equity').all()
                    eq_map = {e.name: e for e in equities}
                    eq_options = ["➕ 新增资本项目"] + list(eq_map.keys())
                    c_eq1, c_eq2 = st.columns([2, 1])
                    selected_eq = c_eq1.selectbox("选择资本项目", eq_options)
                    if selected_eq == "➕ 新增资本项目":
                        is_new_balance_item = True
                        f_name = c_eq2.text_input("新项目名称", placeholder="如：种子轮融资")
                    else:
                        is_new_balance_item = False
                        target_obj = eq_map[selected_eq]
                        target_balance_item_id = target_obj.id
                        f_name = target_obj.name
                        c_eq2.info(f"当前余额: {target_obj.amount:,.2f}")
                    f_amount_input = st.number_input("入账金额", min_value=0.0, step=100.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    balance_item_type = "equity"

                # === 特殊场景：现有资产增加 ===
                elif final_category == "现有资产增加":
                    assets = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == 'asset').all()
                    manual_assets = [a for a in assets if not a.name.startswith("在制资产") and not a.name.startswith("预入库")]
                    if not manual_assets:
                        st.warning("暂无手动录入的资产项目")
                        st.stop()
                    asset_map = {a.name: a for a in manual_assets}
                    selected_asset = st.selectbox("选择资产项目", list(asset_map.keys()))
                    target_obj = asset_map[selected_asset]
                    target_balance_item_id = target_obj.id
                    f_name = target_obj.name
                    st.caption(f"当前余额: {target_obj.amount:,.2f}")
                    f_amount_input = st.number_input("增加金额", min_value=0.0, step=100.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    balance_item_type = "asset"

                # === 新资产增加 ===
                elif final_category == "新资产增加":
                    st.caption("此操作将记录一笔收入流水，并同时在资产表中创建一个新的资产项目。")
                    c_in1, c_in2, c_in3 = st.columns([2, 1.5, 1])
                    f_name = c_in1.text_input("收入内容 (即新资产名称)", placeholder="如：押金、预付款项")
                    f_shop = c_in2.text_input("收入来源", placeholder="来源方")
                    f_amount_input = c_in3.number_input("入账金额", min_value=0.0, step=100.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    is_new_balance_item = True
                    balance_item_type = "asset"

                # === 其他现金收入 ===
                else:
                    c_in1, c_in2, c_in3 = st.columns([2, 1.5, 1])
                    f_name = c_in1.text_input("收入内容", placeholder="如：微店结算 / 零星收入")
                    f_shop = c_in2.text_input("收入来源", placeholder="微店/支付宝")
                    f_amount_input = c_in3.number_input("入账金额", min_value=0.0, step=100.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    balance_item_type = None

            # -------------------------------------------------------
            # >>>>> 场景 B: 支出录入 <<<<<
            # -------------------------------------------------------
            else: 
                exp_cats = ["商品成本", "固定资产购入", "耗材购入", "撤资", "现有资产减少", "其他"]
                exp_type = st.selectbox("支出分类", exp_cats)
                
                # ... (撤资/现有资产减少/商品成本/耗材/固资/其他 的逻辑保持不变) ...
                if exp_type == "撤资":
                    final_category = "资本撤回"
                    equities = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == 'equity').all()
                    eq_map = {e.name: e for e in equities}
                    if not eq_map:
                        st.warning("暂无资本项目，无法撤资")
                        st.stop()
                    selected_eq = st.selectbox("选择撤资项目", list(eq_map.keys()))
                    target_obj = eq_map[selected_eq]
                    target_balance_item_id = target_obj.id
                    f_name = target_obj.name
                    st.caption(f"当前投入: {target_obj.amount:,.2f}")
                    f_amount_input = st.number_input("撤资金额", min_value=0.0, step=100.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    balance_item_type = "equity"

                elif exp_type == "现有资产减少":
                    final_category = "现有资产减少"
                    assets = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == 'asset').all()
                    manual_assets = [a for a in assets if not a.name.startswith("在制资产") and not a.name.startswith("预入库")]
                    if not manual_assets:
                        st.warning("暂无手动录入的资产项目")
                        st.stop()
                    asset_map = {a.name: a for a in manual_assets}
                    selected_asset = st.selectbox("选择要减少的资产", list(asset_map.keys()))
                    target_obj = asset_map[selected_asset]
                    target_balance_item_id = target_obj.id
                    f_name = target_obj.name
                    st.info(f"当前余额: {target_obj.amount:,.2f}")
                    f_amount_input = st.number_input("减少金额", min_value=0.0, step=100.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    balance_item_type = "asset"

                elif exp_type == "商品成本":
                    c_p1, c_p2 = st.columns(2)
                    products = db.query(Product).all()
                    prod_opts = {p.id: p.name for p in products} if products else {}
                    selected_product_id = c_p1.selectbox("选择归属商品", options=list(prod_opts.keys()), format_func=lambda x: prod_opts[x])
                    cost_cats = ["大货材料费", "大货加工费", "物流邮费", "包装费", "设计开发费", "检品发货等人工费", "宣发费", "其他成本"]
                    final_category = c_p2.selectbox("成本分类", cost_cats)
                    budget_items = []
                    if selected_product_id:
                        budget_items = db.query(CostItem).filter(
                            CostItem.product_id == selected_product_id,
                            CostItem.category == final_category,
                            CostItem.supplier == "预算设定"
                        ).all()
                    budget_map = {b.item_name: b for b in budget_items}
                    select_options = ["➕ 手动输入新内容"] + list(budget_map.keys())
                    c_out1, c_out2 = st.columns([2, 1])
                    selected_item_name = c_out1.selectbox("支出内容", select_options)
                    f_shop = c_out2.text_input("店铺/供应商")
                    if selected_item_name == "➕ 手动输入新内容":
                        f_name = c_out1.text_input("请输入具体内容")
                    else:
                        f_name = selected_item_name
                    c_total, c_qty = st.columns(2)
                    calc_total_amount = c_total.number_input("👉 实付总价", min_value=0.0, step=10.0, format="%.2f")
                    f_qty = c_qty.number_input("数量", min_value=1, step=1, value=1)
                    f_price = calc_total_amount / f_qty if f_qty > 0 else 0

                elif exp_type == "耗材购入":
                     all_cons = db.query(ConsumableItem).all()
                     con_map = {c.name: c for c in all_cons}
                     con_options = ["➕ 新增耗材项目"] + list(con_map.keys())
                     c_sel, c_shop = st.columns([2, 1])
                     selected_con = c_sel.selectbox("选择耗材", con_options)
                     f_shop = c_shop.text_input("店铺/供应商", placeholder="淘宝/Amazon")
                     if selected_con == "➕ 新增耗材项目":
                         is_consumable_append = False
                         f_name = st.text_input("新耗材名称")
                         final_category = st.selectbox("耗材子分类", ["包装材", "无实体", "备用素材", "其他"])
                     else:
                         is_consumable_append = True
                         target_obj = con_map[selected_con]
                         target_consumable_id = target_obj.id
                         f_name = target_obj.name
                         final_category = target_obj.category
                     c_total, c_qty = st.columns(2)
                     calc_total_amount = c_total.number_input("👉 实付总价", min_value=0.0, step=10.0, format="%.2f")
                     f_qty = c_qty.number_input("数量", min_value=1, step=1, value=1)
                     f_price = calc_total_amount / f_qty if f_qty > 0 else 0

                elif exp_type == "固定资产购入":
                    final_category = "固定资产购入"
                    c_out1, c_out2 = st.columns([2, 1])
                    f_name = c_out1.text_input("支出内容")
                    f_shop = c_out2.text_input("店铺/供应商")
                    c_total, c_qty = st.columns(2)
                    calc_total_amount = c_total.number_input("👉 实付总价", min_value=0.0, step=10.0, format="%.2f")
                    f_qty = c_qty.number_input("数量", min_value=1, step=1, value=1)
                    f_price = calc_total_amount / f_qty if f_qty > 0 else 0

                else:
                    final_category = st.selectbox("费用分类", ["差旅费", "利润分红", "手续费", "房租水电", "其他支出"])
                    c_out1, c_out2 = st.columns([2, 1])
                    f_name = c_out1.text_input("支出内容")
                    f_shop = c_out2.text_input("店铺/供应商")
                    f_amount_input = st.number_input("支出金额", min_value=0.0, step=10.0, format="%.2f")
                    calc_total_amount = f_amount_input

            f_desc = st.text_input("备注说明", placeholder="选填")

            # ================= 普通收支提交逻辑 =================
            if st.button("💾 确认记账", type="primary"):
                if calc_total_amount == 0:
                    st.warning("金额不能为0")
                elif not f_name:
                    st.warning("请输入内容")
                else:
                    try:
                        final_amount = calc_total_amount if rec_type == "收入" else -calc_total_amount
                        note_detail = f"{f_shop}" if f_shop else ""
                        if f_qty > 1: note_detail += f" (x{f_qty})"
                        if f_desc: note_detail += f" | {f_desc}"
                        
                        # 1. 创建财务对象
                        new_finance = FinanceRecord(
                            date=f_date, amount=final_amount, currency=f_curr,
                            category=final_category, description=f"{f_name} [{note_detail}]"
                        )
                        db.add(new_finance)
                        db.flush() 
                        finance_id = new_finance.id
                        
                        link_msg = ""
                        # 2. 联动 CompanyBalanceItem (资本/资产增减)
                        if balance_item_type:
                            balance_delta = calc_total_amount if rec_type == "收入" else -calc_total_amount
                            
                            if is_new_balance_item:
                                new_bi = CompanyBalanceItem(
                                    name=f_name, 
                                    amount=balance_delta, 
                                    category=balance_item_type,
                                    currency=f_curr,
                                    finance_record_id=finance_id 
                                )
                                db.add(new_bi)
                                link_msg += f" + 新{balance_item_type}"
                            
                            elif target_balance_item_id:
                                existing_bi = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_balance_item_id).first()
                                if existing_bi:
                                    existing_bi.amount += balance_delta
                                    
                                    # 【修改点】自动检测归零逻辑
                                    # 如果余额 <= 0 (考虑到浮点数误差，用 0.01 判断)，则自动删除
                                    if existing_bi.amount <= 0.01:
                                        db.delete(existing_bi)
                                        link_msg += f" ({balance_item_type}已归零并移除)"
                                    else:
                                        link_msg += f" + 更新{balance_item_type}"

                        # 3. 联动其他表
                        if rec_type == "支出":
                            if exp_type == "商品成本" and selected_product_id:
                                db.add(CostItem(product_id=selected_product_id, item_name=f_name, actual_cost=calc_total_amount, supplier=f_shop, category=final_category, unit_price=f_price, quantity=f_qty, remarks=f_desc, finance_record_id=finance_id))
                                link_msg += " + 商品成本"
                            elif exp_type == "固定资产购入":
                                db.add(FixedAsset(name=f_name, unit_price=f_price, quantity=f_qty, remaining_qty=f_qty, shop_name=f_shop, remarks=f_desc, currency=f_curr, finance_record_id=finance_id))
                                link_msg += " + 固定资产"
                            elif exp_type == "耗材购入":
                                rate = exchange_rate if f_curr == "JPY" else 1.0
                                val_cny = calc_total_amount * rate
                                if is_consumable_append and target_consumable_id:
                                    existing_item = db.query(ConsumableItem).filter(ConsumableItem.id == target_consumable_id).first()
                                    if existing_item:
                                        existing_item.remaining_qty += f_qty
                                        old_val = existing_item.unit_price * (existing_item.remaining_qty - f_qty)
                                        if existing_item.remaining_qty > 0: existing_item.unit_price = (old_val + calc_total_amount) / existing_item.remaining_qty
                                        db.add(ConsumableLog(item_name=existing_item.name, change_qty=f_qty, value_cny=val_cny, note=f"追加: {f_desc}", date=f_date))
                                else:
                                    db.add(ConsumableItem(name=f_name, category=final_category, unit_price=f_price, initial_quantity=f_qty, remaining_qty=f_qty, shop_name=f_shop, remarks=f_desc, currency=f_curr, finance_record_id=finance_id))
                                    db.add(ConsumableLog(item_name=f_name, change_qty=f_qty, value_cny=val_cny, note=f"初始: {f_desc}", date=f_date))
                                link_msg += " + 耗材库存"

                        db.commit()
                        st.toast(f"记账成功！{link_msg}", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"写入失败: {e}")

    # ================= 2. 数据处理与余额计算 =================
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
        df_display = pd.DataFrame(processed_data).sort_values(by=["日期", "ID"], ascending=[False, False]).reset_index(drop=True)
    else:
        df_display = pd.DataFrame()

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("CNY 当前余额", f"¥ {running_cny:,.2f}")
    m2.metric("JPY 当前余额", f"¥ {running_jpy:,.0f}")
    jpy_to_cny = running_jpy * exchange_rate
    m3.metric("JPY折合CNY", f"¥ {jpy_to_cny:,.2f}", help=f"汇率: {exchange_rate*100:.1f}")
    m4.metric("账户总余额 (CNY)", f"¥ {(running_cny + jpy_to_cny):,.2f}")

    if not df_display.empty:
        st.subheader("📝 流水明细")
        edited_df = st.data_editor(
            df_display, use_container_width=True, hide_index=True, key="finance_editor",
            disabled=["当前CNY余额", "当前JPY余额", "ID"],
            column_config={
                "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD", required=True),
                "收支": st.column_config.SelectboxColumn("收支", options=["收入", "支出"], required=True),
                "币种": st.column_config.SelectboxColumn("币种", options=["CNY", "JPY"], required=True),
                "金额": st.column_config.NumberColumn("金额 (绝对值)", min_value=0.01, format="¥ %.2f", required=True),
                "当前CNY余额": st.column_config.NumberColumn("CNY 结余", format="¥ %.2f"),
                "当前JPY余额": st.column_config.NumberColumn("JPY 结余", format="¥ %.0f"),
            },
            column_order=["日期", "收支", "币种", "金额", "分类", "备注", "当前CNY余额", "当前JPY余额"]
        )
        if st.session_state.get("finance_editor") and st.session_state["finance_editor"].get("edited_rows"):
            changes = st.session_state["finance_editor"]["edited_rows"]
            has_db_change = False
            for index, diff in changes.items():
                original_row = df_display.iloc[int(index)]
                record = db.query(FinanceRecord).filter(FinanceRecord.id == int(original_row["ID"])).first()
                if record:
                    new_type = diff.get("收支", "收入" if record.amount > 0 else "支出")
                    new_abs_amount = float(diff.get("金额", abs(record.amount)))
                    record.date = diff.get("日期", str(record.date))
                    record.currency = diff.get("币种", record.currency)
                    record.amount = new_abs_amount if new_type == "收入" else -new_abs_amount
                    record.category = diff.get("分类", record.category)
                    record.description = diff.get("备注", record.description)
                    has_db_change = True
                    if "金额" in diff:
                        linked_costs = db.query(CostItem).filter(CostItem.finance_record_id == record.id).all()
                        for cost in linked_costs: cost.actual_cost = new_abs_amount
            if has_db_change:
                db.commit()
                st.rerun()

        with st.popover("🗑️ 删除记录"):
            del_options = df_display.to_dict('records')
            selected_del = st.selectbox("选择要删除的记录", del_options, format_func=lambda x: f"{x['日期']} | {x['收支']} {x['金额']} | {x['分类']}")
            if st.button("确认删除选中记录"):
                del_id = selected_del['ID']
                db.query(CostItem).filter(CostItem.finance_record_id == del_id).delete()
                db.query(FixedAsset).filter(FixedAsset.finance_record_id == del_id).delete()
                db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == del_id).delete()
                db.query(CompanyBalanceItem).filter(CompanyBalanceItem.finance_record_id == del_id).delete()
                db.query(FinanceRecord).filter(FinanceRecord.id == del_id).delete()
                db.commit()
                st.toast("删除成功 (关联项目已清理)", icon="🗑️")
                st.rerun()
    else:
        st.info("暂无财务记录")