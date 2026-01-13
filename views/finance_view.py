import streamlit as st
import pandas as pd
from datetime import date
from models import FinanceRecord, Product, CostItem, ConsumableItem, FixedAsset, ConsumableLog, CompanyBalanceItem

# === 核心修复：定义一个统一的获取流动资金账户的函数 ===
def get_cash_asset(db, currency):
    """
    统一查找逻辑：
    1. 优先找名字以 '流动资金' 开头的资产项。
    2. 必须匹配币种。
    3. 按 ID 排序取第一个（保证永远操作同一个，通常是旧的那个）。
    """
    return db.query(CompanyBalanceItem).filter(
        CompanyBalanceItem.name.like("流动资金%"), 
        CompanyBalanceItem.currency == currency,
        CompanyBalanceItem.category == "asset"
    ).order_by(CompanyBalanceItem.id.asc()).first()

def show_finance_page(db, exchange_rate):
    # ================= 0. 全局样式优化 (加深滚动条) =================
    st.markdown("""
        <style>
            /* 针对 Webkit 内核浏览器 (Chrome, Edge, Safari) */
            /* 滚动条整体宽度/高度 */
            ::-webkit-scrollbar {
                width: 12px;
                height: 12px;
            }
            
            /* 滚动条轨道 (背景) */
            ::-webkit-scrollbar-track {
                background: #f0f2f6; 
                border-radius: 6px;
            }
            
            /* 滚动条滑块 (也就是你可以拖动的那部分) */
            ::-webkit-scrollbar-thumb {
                background: #888888; /* 这里设置颜色：深灰色 */
                border-radius: 6px;
            }

            /* 鼠标悬停在滑块上时的颜色 */
            ::-webkit-scrollbar-thumb:hover {
                background: #555555; /* 悬停变黑 */
            }

            /* 针对 Firefox 浏览器 */
            * {
                scrollbar-width: thin;
                scrollbar-color: #888888 #f0f2f6;
            }
        </style>
    """, unsafe_allow_html=True)
    st.header("💰 财务流水")
    
    # ================= 1. 新增记录区域 (保持不变) =================
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
        # >>>>> 场景 C: 货币兑换 <<<<<
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
                        # 1. 记录流水
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
                        
                        # 2. 更新资产余额 (使用统一函数)
                        asset_out = get_cash_asset(db, source_curr)
                        if asset_out: asset_out.amount -= amount_out
                        
                        asset_in = get_cash_asset(db, target_curr)
                        if asset_in: 
                            asset_in.amount += amount_in
                        else:
                            # 如果完全不存在，才新建
                            new_asset = CompanyBalanceItem(category="asset", name=f"流动资金({target_curr})", amount=amount_in, currency=target_curr)
                            db.add(new_asset)

                        db.commit()
                        st.toast(f"兑换成功：-{amount_out}{source_curr}, +{amount_in}{target_curr}", icon="💱")
                        st.rerun()
                    except Exception as e:
                        st.error(f"兑换失败: {e}")

        # =======================================================
        # >>>>> 场景 D: 债务管理 <<<<<
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
                fund_dest = c_type1.selectbox("资金去向", ["存入流动资金", "新增资产项"])
                
                c_d1, c_d2 = st.columns(2)
                new_debt_name = c_d1.text_input("债务名称", placeholder="如：银行贷款 / 欠款采购")
                
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
                            finance_rec = None
                            if fund_dest == "存入流动资金":
                                finance_rec = FinanceRecord(
                                    date=f_date,
                                    amount=debt_amount, 
                                    currency=f_curr,
                                    category="借入资金",
                                    description=f"{related_content} (来源: {debt_source}) | {debt_remark}"
                                )
                                # 更新流动资金
                                cash_asset = get_cash_asset(db, f_curr)
                                if cash_asset: 
                                    cash_asset.amount += debt_amount
                                else:
                                    db.add(CompanyBalanceItem(category="asset", name=f"流动资金({f_curr})", amount=debt_amount, currency=f_curr))
                            else:
                                finance_rec = FinanceRecord(
                                    date=f_date,
                                    amount=0, 
                                    currency=f_curr,
                                    category="债务-资产形成",
                                    description=f"【资产债务】新增资产: {related_content} | 债务: {new_debt_name} | 金额: {debt_amount}"
                                )
                            
                            db.add(finance_rec)
                            db.flush() 

                            # 创建负债
                            new_liability = CompanyBalanceItem(
                                name=new_debt_name,
                                amount=debt_amount, 
                                category="liability",
                                currency=f_curr,
                                finance_record_id=finance_rec.id
                            )
                            db.add(new_liability)

                            # 创建资产
                            if fund_dest == "新增资产项":
                                new_asset = CompanyBalanceItem(
                                    name=related_content,
                                    amount=debt_amount, 
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
                                    new_finance = FinanceRecord(
                                        date=f_date,
                                        amount=-repay_amount, 
                                        currency=target_liab.currency,
                                        category="债务偿还",
                                        description=f"资金偿还: {target_liab.name} | {repay_remark}"
                                    )
                                    db.add(new_finance)
                                    
                                    # 更新流动资金
                                    cash_asset = get_cash_asset(db, target_liab.currency)
                                    if cash_asset: cash_asset.amount -= repay_amount
                                    
                                    target_liab.amount -= repay_amount
                                    if target_liab.amount <= 0.01:
                                        db.delete(target_liab)
                                        st.toast("债务已还清并销账", icon="✅")
                                    else:
                                        st.toast(f"已还款: {repay_amount}", icon="💸")
                                    
                                    db.commit()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"操作失败: {e}")
                                    
                    else:
                        st.caption("ℹ️ 通过退还资产或资产抵消来消除债务。操作将：1.删除指定的资产项 2.删除/减少债务。**不会减少流动资金**。")
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
                                new_finance = FinanceRecord(
                                    date=f_date,
                                    amount=0, 
                                    currency=target_liab.currency,
                                    category="债务-资产核销",
                                    description=f"资产抵消: 用 [{target_asset.name}] 抵消 [{target_liab.name}] | 金额: {offset_amount} | {offset_remark}"
                                )
                                db.add(new_finance)
                                
                                target_asset.amount -= offset_amount
                                if target_asset.amount <= 0.01: db.delete(target_asset)
                                
                                target_liab.amount -= offset_amount
                                if target_liab.amount <= 0.01: db.delete(target_liab)
                                    
                                db.commit()
                                st.toast(f"资产抵消完成，金额: {offset_amount}", icon="🔄")
                                st.rerun()
                             except Exception as e:
                                st.error(f"操作失败: {e}")

        # =======================================================
        # >>>>> 场景 A & B: 普通收入/支出 <<<<<
        # =======================================================
        else:
            with r1_c3:
                f_curr = st.selectbox("币种", ["CNY", "JPY"])

            # -------------------------------------------------------
            # >>>>> 场景 A: 收入录入 <<<<<
            # -------------------------------------------------------
            if rec_type == "收入":
                income_cats = ["销售收入", "退款", "投资", "现有资产增加", "其他资产增加", "新资产增加", "其他现金收入"]
                final_category = st.selectbox("收入分类", income_cats)
                
                if final_category == "投资":
                    st.info("ℹ️ **操作说明**：此操作将记录一笔【资金收入】，增加流动资金；同时增加对应的【资本项】余额。")
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
                        if target_obj.currency != f_curr:
                            c_eq2.warning(f"⚠️ 注意：该项目原币种为 {target_obj.currency}")
                        else:
                            c_eq2.info(f"当前余额: {target_obj.amount:,.2f}")
                            
                    f_amount_input = st.number_input("投资/入账金额", min_value=0.0, step=100.0, format="%.2f", help="实际到账的资金金额")
                    calc_total_amount = f_amount_input
                    balance_item_type = "equity"

                # 【修改点 2】: 增加 "其他资产增加" 的输入框逻辑
                elif final_category == "其他资产增加":
                    st.info("ℹ️ **操作说明**：此操作将记录收入流水，并自动在【其他资产管理】中增加对应的物资库存。")
                    
                    c_add1, c_add2 = st.columns([1.5, 1])
                    f_name = c_add1.text_input("项目名", placeholder="资产/耗材名称")
                    f_shop = c_add2.text_input("店铺/来源", placeholder="供应商")
                    
                    c_add3, c_add4 = st.columns(2)
                    calc_total_amount = c_add3.number_input("总价 (价值)", min_value=0.0, step=10.0, format="%.2f")
                    f_qty = c_add4.number_input("数量", min_value=0.01, step=1.0, value=1.0, format="%.2f")
                    
                    # 自动计算单价
                    f_price = calc_total_amount / f_qty if f_qty > 0 else 0
                    if f_price > 0:
                        st.caption(f"📊 计算单价: {f_price:,.2f}")
                    
                    # 赋值给通用变量
                    f_amount_input = calc_total_amount
                    balance_item_type = None # 不创建通用的 CompanyBalanceItem，而是创建 ConsumableItem

                elif final_category == "现有资产增加":
                    assets = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == 'asset').all()
                    # 【优化】过滤掉流动资金，防止自己增加自己
                    manual_assets = [a for a in assets if not a.name.startswith("在制资产") and not a.name.startswith("预入库") and not a.name.startswith("流动资金")]
                    if not manual_assets:
                        st.warning("暂无手动录入的资产项目")
                        st.stop()
                    asset_map = {a.name: a for a in manual_assets}
                    selected_asset = st.selectbox("选择资产项目", list(asset_map.keys()))
                    target_obj = asset_map[selected_asset]
                    target_balance_item_id = target_obj.id
                    f_name = target_obj.name
                    st.caption(f"当前余额: {target_obj.amount:,.2f}")
                    f_amount_input = st.number_input("增加价值/金额", min_value=0.0, step=100.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    balance_item_type = "asset"

                elif final_category == "新资产增加":
                    st.caption("此操作将记录一笔收入流水，并同时在资产表中创建一个新的资产项目。")
                    c_in1, c_in2, c_in3 = st.columns([2, 1.5, 1])
                    f_name = c_in1.text_input("收入内容 (即新资产名称)", placeholder="如：押金、预付款项")
                    f_shop = c_in2.text_input("收入来源", placeholder="来源方")
                    f_amount_input = c_in3.number_input("入账金额", min_value=0.0, step=100.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    is_new_balance_item = True
                    balance_item_type = "asset"

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
                exp_cats = ["商品成本", "固定资产购入", "其他资产购入", "撤资", "现有资产减少", "其他"]
                exp_type = st.selectbox("支出分类", exp_cats)
                
                if exp_type == "撤资":
                    st.info("ℹ️ **操作说明**：此操作将记录一笔【资金支出】，扣减流动资金；同时扣减对应的【资本项】余额。")
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
                    if target_obj.currency != f_curr:
                        st.warning(f"⚠️ 注意：该项目原币种为 {target_obj.currency}，当前支出币种为 {f_curr}")
                    st.caption(f"当前投入: {target_obj.amount:,.2f}")
                    f_amount_input = st.number_input("撤资/支出金额", min_value=0.0, step=100.0, format="%.2f", help="实际流出的资金金额")
                    calc_total_amount = f_amount_input
                    balance_item_type = "equity"

                elif exp_type == "现有资产减少":
                    final_category = "现有资产减少"
                    assets = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == 'asset').all()
                    # 【优化】过滤掉流动资金
                    manual_assets = [a for a in assets if not a.name.startswith("在制资产") and not a.name.startswith("预入库") and not a.name.startswith("流动资金")]
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
                    f_qty = c_qty.number_input("数量", min_value=0.01, step=0.1, value=1.0, format="%.2f")
                    f_price = calc_total_amount / f_qty if f_qty > 0 else 0
                    
                    if f_price > 0:
                        st.caption(f"📊 自动计算单价: **¥ {f_price:,.2f}**")

                elif exp_type == "其他资产购入":
                    st.info("ℹ️ 此操作将记录支出，并自动增加【其他资产管理】中的库存。")
                    
                    # 第一行：项目名 | 分类 | 店铺
                    c_oa1, c_oa2, c_oa3 = st.columns([1.5, 1, 1])
                    
                    # 为了方便，可以提供现有资产的自动补全，但允许输入新名称
                    all_cons = db.query(ConsumableItem).all()
                    cons_names = [c.name for c in all_cons]
                    
                    # 项目名 (输入或选择)
                    f_name = c_oa1.selectbox("项目名称", ["➕ 手动输入新项"] + cons_names)
                    if f_name == "➕ 手动输入新项":
                        f_name = c_oa1.text_input("请输入新项目名称", placeholder="如：飞机盒")
                    
                    # 分类 (选择)
                    # 尝试根据已选项目自动填充分类
                    default_cat_idx = 0
                    if f_name in cons_names:
                        existing_item = next((c for c in all_cons if c.name == f_name), None)
                        if existing_item and existing_item.category in ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"]:
                            default_cat_idx = ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"].index(existing_item.category)
                            
                    final_category = c_oa2.selectbox("资产分类", ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"], index=default_cat_idx)
                    
                    # 店铺
                    f_shop = c_oa3.text_input("店铺/供应商", placeholder="淘宝/Amazon")

                    # 第二行：总价 | 数量
                    c_total, c_qty = st.columns(2)
                    calc_total_amount = c_total.number_input("👉 支出总价", min_value=0.0, step=10.0, format="%.2f")
                    f_qty = c_qty.number_input("数量", min_value=0.01, step=1.0, value=1.0, format="%.2f")
                    
                    # 自动算单价
                    f_price = calc_total_amount / f_qty if f_qty > 0 else 0
                    if f_price > 0:
                        st.caption(f"📊 自动计算单价: **¥ {f_price:,.2f}**")
                        
                    # 标记
                    is_consumable_append = True # 开启耗材逻辑

                elif exp_type == "固定资产购入":
                    final_category = "固定资产购入"
                    c_out1, c_out2 = st.columns([2, 1])
                    f_name = c_out1.text_input("支出内容")
                    f_shop = c_out2.text_input("店铺/供应商")
                    
                    c_total, c_qty = st.columns(2)
                    calc_total_amount = c_total.number_input("👉 实付总价", min_value=0.0, step=10.0, format="%.2f")
                    f_qty = c_qty.number_input("数量", min_value=0.01, step=0.1, value=1.0, format="%.2f")
                    
                    f_price = calc_total_amount / f_qty if f_qty > 0 else 0
                    if f_price > 0:
                        st.caption(f"📊 自动计算单价: **¥ {f_price:,.2f}**")

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
                        # 1. 记录 FinanceRecord
                        # 支出记为负数
                        final_amount = calc_total_amount if rec_type == "收入" else -calc_total_amount
                        
                        # 备注信息拼接
                        note_detail = f"{f_shop}" if f_shop else ""
                        if f_qty > 1: note_detail += f" (x{f_qty})"
                        if f_desc: note_detail += f" | {f_desc}"
                        
                        new_record = FinanceRecord(
                            date=f_date, amount=final_amount, currency=f_curr,
                            category=final_category, description=f"{f_name} [{note_detail}]"
                        )
                        db.add(new_record)
                        db.flush() # 获取ID
                        
                        # 2. 联动更新资产 (现金流变动) - 【使用统一函数】
                        target_cash_asset = get_cash_asset(db, f_curr)
                        
                        # 如果完全没有，才创建新的
                        if not target_cash_asset:
                            target_cash_asset = CompanyBalanceItem(
                                category="asset",
                                name=f"流动资金({f_curr})",
                                amount=0.0,
                                currency=f_curr
                            )
                            db.add(target_cash_asset)
                        
                        target_cash_asset.amount += final_amount
                        
                        link_msg = "资金变动已记录"
                        
                        # 3. 联动 CompanyBalanceItem
                        if balance_item_type:
                            balance_delta = final_amount 
                            
                            if is_new_balance_item:
                                new_bi = CompanyBalanceItem(
                                    name=f_name, 
                                    amount=balance_delta, 
                                    category=balance_item_type,
                                    currency=f_curr,
                                    finance_record_id=new_record.id # 关联ID
                                )
                                db.add(new_bi)
                                link_msg += f" + 新{balance_item_type} ({balance_delta:+.2f})"
                            
                            elif target_balance_item_id:
                                existing_bi = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_balance_item_id).first()
                                if existing_bi:
                                    existing_bi.amount += balance_delta
                                    if existing_bi.amount <= 0.01:
                                        db.delete(existing_bi)
                                        link_msg += f" ({balance_item_type}已归零并移除)"
                                    else:
                                        link_msg += f" + 更新{balance_item_type} ({balance_delta:+.2f})"

                        # 4. 联动其他表
                        if rec_type == "支出":
                            if exp_type == "商品成本" and selected_product_id:
                                # === 【修改开始】 ===
                                # 逻辑：如果支付币种是 JPY，记入成本表时需折算为 CNY
                                cost_in_cny = calc_total_amount
                                unit_price_cny = f_price
                                
                                # 备注中增加原币说明，方便核对
                                final_remark = f_desc
                                if f_curr == "JPY":
                                    cost_in_cny = calc_total_amount * exchange_rate
                                    unit_price_cny = cost_in_cny / f_qty if f_qty > 0 else 0
                                    # 在备注里追加原币金额信息
                                    curr_note = f"(原币支付: {calc_total_amount:.0f} JPY)"
                                    final_remark = f"{f_desc} {curr_note}".strip()

                                db.add(CostItem(
                                    product_id=selected_product_id, 
                                    item_name=f_name, 
                                    actual_cost=cost_in_cny, # 存入折算后的 CNY
                                    supplier=f_shop, 
                                    category=final_category, 
                                    unit_price=unit_price_cny, # 单价也折算为 CNY
                                    quantity=f_qty, 
                                    remarks=final_remark, 
                                    finance_record_id=new_record.id
                                ))
                                link_msg += " + 商品成本(已折算CNY)"
                                
                            elif exp_type == "固定资产购入":
                                db.add(FixedAsset(name=f_name, unit_price=f_price, quantity=f_qty, remaining_qty=f_qty, shop_name=f_shop, remarks=f_desc, currency=f_curr, finance_record_id=new_record.id))
                                link_msg += " + 固定资产"
                            elif exp_type == "其他资产购入":
                                # 1. 计算汇率价值 (用于记录日志)
                                rate = exchange_rate if f_curr == "JPY" else 1.0
                                val_cny = calc_total_amount * rate
                                
                                # 2. 智能查找目标资产对象 (按名称查重)
                                target_item = db.query(ConsumableItem).filter(ConsumableItem.name == f_name).first()

                                # --- 分支处理：合并 vs 新建 ---
                                if target_item:
                                    # === 合并逻辑 (加权平均算法) ===
                                    # 旧的总价值
                                    old_total_val = target_item.unit_price * target_item.remaining_qty
                                    # 新的总价值
                                    new_total_val = calc_total_amount
                                    
                                    # 更新数量
                                    target_item.remaining_qty += f_qty
                                    
                                    # 更新单价 (总价值 / 总数量)
                                    if target_item.remaining_qty > 0:
                                        target_item.unit_price = (old_total_val + new_total_val) / target_item.remaining_qty
                                    
                                    # 更新店铺/分类 (以最新的为准)
                                    target_item.shop_name = f_shop 
                                    target_item.category = final_category 
                                    
                                    # 记录日志
                                    db.add(ConsumableLog(
                                        item_name=target_item.name, 
                                        change_qty=f_qty, 
                                        value_cny=val_cny, 
                                        note=f"购入入库: {f_desc}", 
                                        date=f_date
                                    ))
                                    link_msg += f" + 其他资产库存 (已合并至: {target_item.name})"
                                    
                                else:
                                    # === 新建逻辑 ===
                                    new_con = ConsumableItem(
                                        name=f_name, 
                                        category=final_category, 
                                        unit_price=f_price, 
                                        initial_quantity=f_qty, 
                                        remaining_qty=f_qty, 
                                        shop_name=f_shop, 
                                        remarks=f_desc, 
                                        currency=f_curr, 
                                        finance_record_id=new_record.id
                                    )
                                    db.add(new_con)
                                    
                                    db.add(ConsumableLog(
                                        item_name=f_name, 
                                        change_qty=f_qty, 
                                        value_cny=val_cny, 
                                        note=f"初始购入: {f_desc}", 
                                        date=f_date
                                    ))
                                    link_msg += " + 新其他资产库存"
                        
                        # 【收入类型的联动处理】
                        elif rec_type == "收入":
                            if final_category == "其他资产增加":
                                # 1. 计算汇率价值
                                rate = exchange_rate if f_curr == "JPY" else 1.0
                                val_cny = calc_total_amount * rate
                                
                                # 2. 查重逻辑 (按名称查找是否已存在)
                                target_item = db.query(ConsumableItem).filter(ConsumableItem.name == f_name).first()
                                
                                if target_item:
                                    # === 合并逻辑 (加权平均) ===
                                    old_total_val = target_item.unit_price * target_item.remaining_qty
                                    new_total_val = calc_total_amount
                                    
                                    target_item.remaining_qty += f_qty
                                    if target_item.remaining_qty > 0:
                                        target_item.unit_price = (old_total_val + new_total_val) / target_item.remaining_qty
                                    
                                    # 更新店铺信息
                                    if f_shop: target_item.shop_name = f_shop
                                    
                                    db.add(ConsumableLog(
                                        item_name=target_item.name,
                                        change_qty=f_qty,
                                        value_cny=val_cny,
                                        note=f"资产增加(收入): {f_desc}",
                                        date=f_date
                                    ))
                                    link_msg += f" + 其他资产库存 (已合并: {target_item.name})"
                                else:
                                    # === 新建逻辑 ===
                                    new_con = ConsumableItem(
                                        name=f_name,
                                        category="其他", # 默认为其他，可在资产管理页修改
                                        unit_price=f_price,
                                        initial_quantity=f_qty,
                                        remaining_qty=f_qty,
                                        shop_name=f_shop,
                                        remarks=f_desc,
                                        currency=f_curr,
                                        finance_record_id=new_record.id
                                    )
                                    db.add(new_con)
                                    
                                    db.add(ConsumableLog(
                                        item_name=f_name,
                                        change_qty=f_qty,
                                        value_cny=val_cny,
                                        note=f"资产增加(初始): {f_desc}",
                                        date=f_date
                                    ))
                                    link_msg += " + 新其他资产库存"

                        db.commit()
                        st.toast(f"记账成功！{link_msg}", icon="✅")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
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
        # 倒序排列，显示最新的在前面
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

    # ================= 3. 流水明细 (带颜色只读表格) =================
    if not df_display.empty:
        st.subheader("📜 流水明细")

        # --- A. 定义颜色样式函数 ---
        def highlight_rows(row):
            type_val = row.get("收支", "")
            # 默认白色背景
            styles = [''] * len(row)
            if type_val == "支出":
                return ['background-color: #ffebee; color: #b71c1c'] * len(row) # 淡红
            elif type_val == "收入":
                return ['background-color: #e8f5e9; color: #1b5e20'] * len(row) # 浅绿
            return styles

        # --- B. 应用样式 ---
        # 格式化日期列为字符串，否则 st.dataframe 有时显示不友好
        df_styled = df_display.copy()
        df_styled['日期'] = pd.to_datetime(df_styled['日期']).dt.strftime('%Y-%m-%d')
        
        # 应用 Styler
        styler = df_styled.style.apply(highlight_rows, axis=1)
        # 格式化金额
        styler = styler.format({
            "金额": "¥ {:.2f}", 
            "当前CNY余额": "¥ {:.2f}", 
            "当前JPY余额": "¥ {:.0f}"
        })

        # --- C. 渲染只读表格 (动态高度) ---
        # 1. 计算高度：(数据行数 + 表头1行) * 每行高度(约35px)
        # 2. 加上一点缓冲
        num_rows = len(df_display)
        row_height = 35 
        calculated_height = (num_rows + 1) * row_height
        
        # 3. 设置限制：最小 300px，最大 1200px (根据您的屏幕需求调整)
        # 这样数据少时不留白，数据多时在全屏下能显示更多行
        final_height = min(max(calculated_height, 300), 1200)

        st.dataframe(
            styler,
            use_container_width=True,
            hide_index=True,
            height=int(final_height), # 使用动态计算的高度
            column_config={"ID": None} 
        )

        # ================= 4. 底部操作区 (编辑 & 删除) =================
        st.divider()
        c_edit, c_del = st.columns([1, 1])

        # 获取用于下拉框的字典列表
        record_options = df_display.to_dict('records')

        # >>> 编辑记录功能 <<<
        with c_edit:
            with st.popover("✏️ 编辑记录", use_container_width=True):
                if not record_options:
                    st.caption("暂无记录可编辑")
                else:
                    # 1. 选择记录
                    sel_edit = st.selectbox(
                        "选择要修改的记录", 
                        record_options, 
                        format_func=lambda x: f"{x['日期']} | {x['收支']} {x['金额']} | {x['分类']} | {x['备注']}",
                        key="edit_select"
                    )
                    
                    if sel_edit:
                        target_id = sel_edit['ID']
                        # 从数据库重新拉取最新对象
                        edit_obj = db.query(FinanceRecord).filter(FinanceRecord.id == target_id).first()
                        
                        if edit_obj:
                            st.markdown(f"**正在编辑 ID: {edit_obj.id}**")
                            
                            # 2. 编辑表单
                            with st.form(key=f"edit_form_{target_id}"):
                                new_date = st.date_input("日期", value=edit_obj.date)
                                
                                c_e1, c_e2 = st.columns(2)
                                new_type = c_e1.selectbox("收支类型", ["收入", "支出"], index=0 if edit_obj.amount > 0 else 1)
                                new_curr = c_e2.selectbox("币种", ["CNY", "JPY"], index=0 if edit_obj.currency == "CNY" else 1)
                                
                                c_e3, c_e4 = st.columns(2)
                                new_amount_abs = c_e3.number_input("金额 (绝对值)", value=abs(edit_obj.amount), min_value=0.0, step=10.0)
                                new_cat = c_e4.text_input("分类", value=edit_obj.category)
                                
                                new_desc = st.text_input("备注", value=edit_obj.description or "")
                                
                                st.warning("⚠️ 注意：修改金额或收支类型将自动更新【流动资金】余额，并联动更新关联的成本/资产项金额。")
                                
                                if st.form_submit_button("✅ 确认修改并保存"):
                                    try:
                                        # A. 计算金额差额 (用于更新流动资金)
                                        # 新的带符号金额
                                        new_signed_amount = new_amount_abs if new_type == "收入" else -new_amount_abs
                                        old_amount = edit_obj.amount
                                        diff = new_signed_amount - old_amount
                                        
                                        # B. 更新 FinanceRecord
                                        edit_obj.date = new_date
                                        edit_obj.currency = new_curr
                                        edit_obj.amount = new_signed_amount
                                        edit_obj.category = new_cat
                                        edit_obj.description = new_desc
                                        
                                        # C. 更新流动资金 (CompanyBalanceItem)
                                        cash_asset = get_cash_asset(db, new_curr)
                                        if cash_asset:
                                            cash_asset.amount += diff
                                        
                                        # D. 联动更新 (CostItem / FixedAsset / Consumable 等)
                                        # 1. 成本 (CostItem)
                                        linked_costs = db.query(CostItem).filter(CostItem.finance_record_id == target_id).all()
                                        for cost in linked_costs:
                                            cost.actual_cost = new_amount_abs
                                            cost.remarks = f"{new_desc} (已修)"
                                            
                                        # 2. 固定资产 (FixedAsset)
                                        linked_assets = db.query(FixedAsset).filter(FixedAsset.finance_record_id == target_id).all()
                                        for fa in linked_assets:
                                            if fa.quantity > 0:
                                                fa.unit_price = new_amount_abs / fa.quantity
                                            fa.currency = new_curr
                                            
                                        # 3. 其他资产 (ConsumableItem)
                                        linked_cons = db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == target_id).all()
                                        for ci in linked_cons:
                                            if ci.initial_quantity > 0:
                                                ci.unit_price = new_amount_abs / ci.initial_quantity
                                            ci.currency = new_curr
                                            
                                        # 4. 公司资产/负债 (CompanyBalanceItem)
                                        linked_bis = db.query(CompanyBalanceItem).filter(
                                            CompanyBalanceItem.finance_record_id == target_id,
                                            CompanyBalanceItem.category != 'asset'
                                        ).all()
                                        for bi in linked_bis:
                                            bi.amount = new_amount_abs
                                            bi.currency = new_curr

                                        db.commit()
                                        st.toast("记录已修改并联动更新！", icon="💾")
                                        st.rerun()
                                        
                                    except Exception as e:
                                        db.rollback()
                                        st.error(f"修改失败: {e}")

        # >>> 删除记录功能 <<<
        with c_del:
            with st.popover("🗑️ 删除记录", use_container_width=True):
                if not record_options:
                    st.caption("暂无记录可删除")
                else:
                    selected_del = st.selectbox(
                        "选择要删除的记录", 
                        record_options, 
                        format_func=lambda x: f"{x['日期']} | {x['收支']} {x['金额']} | {x['分类']} | {x['备注']}",
                        key="del_select"
                    )
                    
                    if st.button("确认删除选中记录", type="primary"):
                        del_id = selected_del['ID']
                        record_to_del = db.query(FinanceRecord).filter(FinanceRecord.id == del_id).first()
                        
                        if record_to_del:
                            msg_list = []
                            try:
                                # 1. 回滚资金余额
                                cash_asset = get_cash_asset(db, record_to_del.currency)
                                if cash_asset:
                                    cash_asset.amount -= record_to_del.amount
                                    msg_list.append("资金已回滚")
                                
                                # 2. 特殊处理：【其他资产购入】回滚库存
                                if record_to_del.category == "其他资产购入":
                                    target_log = db.query(ConsumableLog).filter(
                                        ConsumableLog.date == record_to_del.date,
                                        ConsumableLog.value_cny >= abs(record_to_del.amount) - 0.1,
                                        ConsumableLog.value_cny <= abs(record_to_del.amount) + 0.1,
                                        ConsumableLog.change_qty > 0
                                    ).first()
                                    if target_log:
                                        target_item = db.query(ConsumableItem).filter(ConsumableItem.name == target_log.item_name).first()
                                        if target_item:
                                            target_item.remaining_qty -= target_log.change_qty
                                            msg_list.append(f"库存已扣减 {target_log.change_qty}")
                                        db.delete(target_log)

                                # 3. 级联删除关联项目
                                db.query(CostItem).filter(CostItem.finance_record_id == del_id).delete()
                                db.query(FixedAsset).filter(FixedAsset.finance_record_id == del_id).delete()
                                db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == del_id).delete()
                                db.query(CompanyBalanceItem).filter(CompanyBalanceItem.finance_record_id == del_id).delete()
                                
                                # 4. 删除流水本身
                                db.delete(record_to_del)
                                db.commit()
                                
                                st.toast(f"删除成功: {' | '.join(msg_list)}", icon="🗑️")
                                st.rerun()
                                
                            except Exception as e:
                                db.rollback()
                                st.error(f"删除失败: {e}")
    else:
        st.info("暂无财务记录")