import streamlit as st
import pandas as pd
from datetime import date
from models import FinanceRecord, Product, CostItem, ConsumableItem, FixedAsset

def show_finance_page(db, exchange_rate):
    st.header("💰 财务资金流水")
    
    # ================= 1. 新增记录区域 =================
    with st.expander("➕ 新增收支记录 (自动联动)", expanded=True):
        r1_c1, r1_c2, r1_c3 = st.columns([1, 1, 1])
        f_date = r1_c1.date_input("日期", date.today())
        rec_type = r1_c2.selectbox("收支类型", ["支出", "收入"])
        f_curr = r1_c3.selectbox("币种", ["CNY", "JPY"])

        f_name = ""
        f_shop = ""
        final_category = ""
        calc_total_amount = 0.0 
        f_qty = 1
        f_price = 0.0 
        default_budget_remarks = ""
        f_unit = "" 

        income_cats = ["销售收入", "日元兑换", "退款", "借款", "投资", "其他收入"]
        cost_cats_detailed = ["大货材料费", "大货加工费", "物流邮费", "包装费"]
        cost_cats_simple = ["设计开发费", "检品发货等人工费", "宣发费", "其他成本"]
        product_cost_cats = cost_cats_detailed + cost_cats_simple
        other_expense_cats = ["差旅费", "利润分红", "手续费", "房租水电", "其他支出"]
        
        selected_product_id = None
        exp_type = None 
        # 新增变量用于逻辑判断
        target_budget_id = None 
        is_manual_mode = True

        st.divider()

        # >>>>> 场景 A: 收入录入 <<<<<
        if rec_type == "收入":
            final_category = st.selectbox("收入分类", income_cats)
            c_in1, c_in2, c_in3 = st.columns([2, 1.5, 1])
            f_name = c_in1.text_input("收入内容", placeholder="如：微店1月结算")
            f_shop = c_in2.text_input("收入来源", placeholder="微店/支付宝")
            f_amount_input = c_in3.number_input("入账金额", min_value=0.0, step=100.0, format="%.2f")
            calc_total_amount = f_amount_input
            f_qty = 1

        # >>>>> 场景 B: 支出录入 <<<<<
        else: 
            exp_type = st.selectbox("支出类型", ["商品成本", "固定资产购入", "耗材购入", "其他"])
            
            # --- 商品成本 ---
            if exp_type == "商品成本":
                c_p1, c_p2 = st.columns(2)
                products = db.query(Product).all()
                if products:
                    prod_opts = {p.id: p.name for p in products}
                    selected_product_id = c_p1.selectbox("选择归属商品", options=list(prod_opts.keys()), format_func=lambda x: prod_opts[x])
                else:
                    c_p1.warning("暂无商品")
                
                final_category = c_p2.selectbox("成本分类", product_cost_cats)
                
                # 查询预算
                budget_items = []
                default_budget_price = 0.0
                default_budget_qty = 0
                default_budget_unit = ""

                if selected_product_id:
                    budget_items = db.query(CostItem).filter(
                        CostItem.product_id == selected_product_id,
                        CostItem.category == final_category,
                        CostItem.supplier == "预算设定"
                    ).all()
                
                budget_map = {b.item_name: b for b in budget_items}
                select_options = ["➕ 手动输入新内容"] + list(budget_map.keys())
                
                c_out1, c_out2 = st.columns([2, 1])
                selected_item_name = c_out1.selectbox("支出内容 (可选已有预算)", select_options)
                f_shop = c_out2.text_input("店铺/供应商", placeholder="淘宝/工厂")
                
                if selected_item_name == "➕ 手动输入新内容":
                    is_manual_mode = True
                    f_name = c_out1.text_input("请输入具体内容", placeholder="如：追加面料")
                    default_budget_price = 0.0
                    default_budget_qty = 0
                    default_budget_remarks = ""
                    default_budget_unit = ""
                else:
                    is_manual_mode = False
                    f_name = selected_item_name
                    target_budget = budget_map[selected_item_name]
                    target_budget_id = target_budget.id # 记录ID用于后续更新
                    default_budget_price = target_budget.unit_price
                    default_budget_qty = target_budget.quantity
                    default_budget_remarks = target_budget.remarks 
                    default_budget_unit = target_budget.unit if target_budget.unit else ""
                    st.toast(f"已加载【{f_name}】的预算标准", icon="📋")

                # 动态输入
                if final_category in cost_cats_detailed:
                    c_b_price, c_b_qty, c_unit, c_act_qty, c_act_pay = st.columns([1, 0.8, 0.8, 1, 1.2])
                    
                    budget_price = c_b_price.number_input("预算单价", value=float(default_budget_price), format="%.2f", disabled=True)
                    _ = c_b_qty.number_input("预算数量", value=int(default_budget_qty), disabled=True)
                    
                    f_unit = c_unit.text_input("单位", value=default_budget_unit, placeholder="米/个")
                    
                    default_act_qty = int(default_budget_qty) if int(default_budget_qty) > 0 else 1
                    f_qty = c_act_qty.number_input("👉 实付数量", min_value=0, step=1, value=default_act_qty)
                    real_pay = c_act_pay.number_input("👉 实付总金额", min_value=0.0, step=10.0, format="%.2f")
                    
                    calc_total_amount = real_pay
                    f_price = budget_price 
                else:
                    c_b_total, c_real_pay = st.columns([1, 1.2])
                    budget_total = c_b_total.number_input("预算总价", value=float(default_budget_price), format="%.2f", disabled=True)
                    real_pay = c_real_pay.number_input("👉 实付总金额", min_value=0.0, step=10.0, format="%.2f")
                    
                    calc_total_amount = real_pay
                    f_qty = 1
                    f_price = real_pay 

            # --- 其他类型 ---
            else:
                if exp_type == "固定资产购入":
                    final_category = "固定资产购入"
                    st.caption("已自动分类为：固定资产购入")
                elif exp_type == "耗材购入":
                    final_category = "耗材购入"
                    st.caption("已自动分类为：耗材购入")
                else: 
                    final_category = st.selectbox("费用分类", other_expense_cats)

                c_out1, c_out2 = st.columns([2, 1])
                f_name = c_out1.text_input("支出内容", placeholder="如：飞机盒、打印机")
                f_shop = c_out2.text_input("店铺/供应商", placeholder="淘宝/Amazon")
                
                if exp_type == "耗材购入":
                    c_total, c_qty = st.columns(2)
                    calc_total_amount = c_total.number_input("👉 实付总价", min_value=0.0, step=10.0, format="%.2f")
                    f_qty = c_qty.number_input("数量", min_value=1, step=1, value=1)
                    if f_qty > 0: f_price = calc_total_amount / f_qty
                    else: f_price = 0

                elif exp_type == "固定资产购入":
                    c_price, c_qty = st.columns(2)
                    f_price = c_price.number_input("单价", min_value=0.0, step=1.0, format="%.2f")
                    f_qty = c_qty.number_input("数量", min_value=1, step=1, value=1)
                    calc_total_amount = f_price * f_qty
                    st.markdown(f"**💰 合计: {f_curr} {calc_total_amount:,.2f}**")

                else: 
                    f_amount_input = st.number_input("支出金额", min_value=0.0, step=10.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    f_qty = 1

        f_desc = st.text_input("备注说明", placeholder="选填")

        if st.button("💾 确认记账", type="primary"):
            if calc_total_amount == 0:
                st.warning("金额不能为0")
            elif not f_name:
                st.warning("请输入内容")
            else:
                try:
                    final_amount = calc_total_amount if rec_type == "收入" else -calc_total_amount
                    if rec_type == "收入": note_detail = f"来源: {f_shop}"
                    else:
                        note_detail = f"{f_shop}"
                        if f_qty > 1: note_detail += f" (x{f_qty})"
                    if f_desc: note_detail += f" | {f_desc}"

                    # 1. 创建财务对象
                    new_finance = FinanceRecord(
                        date=f_date, amount=final_amount, currency=f_curr,
                        category=final_category, description=f"{f_name} [{note_detail}]"
                    )
                    db.add(new_finance)
                    # === 关键：先Flush，生成ID ===
                    db.flush() 
                    finance_id = new_finance.id
                    
                    # 2. 联动写入其他表
                    link_msg = ""
                    if rec_type == "支出":
                        # === 商品成本：区分 新增 / 更新 ===
                        if exp_type == "商品成本" and selected_product_id:
                            # 备注合并逻辑
                            final_cost_remarks = f_desc
                            if default_budget_remarks:
                                if f_desc: final_cost_remarks = f"{default_budget_remarks} | {f_desc}"
                                else: final_cost_remarks = default_budget_remarks
                            
                            if is_manual_mode:
                                # A. 手动模式：新增一条 CostItem
                                db.add(CostItem(
                                    product_id=selected_product_id, item_name=f_name, actual_cost=calc_total_amount, 
                                    supplier=f_shop, category=final_category, unit_price=f_price, quantity=f_qty, 
                                    remarks=final_cost_remarks,
                                    unit=f_unit,
                                    finance_record_id=finance_id 
                                ))
                                link_msg = " + 商品成本 (新增)"
                            else:
                                # B. 预算模式：更新现有的 CostItem (实现行内合并)
                                if target_budget_id:
                                    existing_item = db.query(CostItem).filter(CostItem.id == target_budget_id).first()
                                    if existing_item:
                                        existing_item.actual_cost = calc_total_amount
                                        existing_item.supplier = f_shop # 更新供应商 (不再是 '预算设定')
                                        existing_item.quantity = f_qty  # 更新为实付数量
                                        existing_item.unit = f_unit     # 更新单位
                                        existing_item.remarks = final_cost_remarks
                                        existing_item.finance_record_id = finance_id # 关联流水
                                        
                                        link_msg = " + 商品成本 (预算核销)"
                                    else:
                                        # 防御性代码：如果找不到ID，退化为新增
                                        db.add(CostItem(
                                            product_id=selected_product_id, item_name=f_name, actual_cost=calc_total_amount, 
                                            supplier=f_shop, category=final_category, unit_price=f_price, quantity=f_qty, 
                                            remarks=final_cost_remarks,
                                            unit=f_unit,
                                            finance_record_id=finance_id 
                                        ))
                                        link_msg = " + 商品成本 (预算ID丢失，转为新增)"

                        elif exp_type == "固定资产购入":
                            db.add(FixedAsset(
                                name=f_name, unit_price=f_price, quantity=f_qty, remaining_qty=f_qty,
                                shop_name=f_shop, remarks=f_desc, currency=f_curr,
                                finance_record_id=finance_id 
                            ))
                            link_msg = " + 固定资产库"

                        elif exp_type == "耗材购入":
                            db.add(ConsumableItem(
                                name=f_name, category="财务录入", unit_price=f_price,
                                initial_quantity=f_qty, remaining_qty=f_qty, shop_name=f_shop, remarks=f_desc,
                                finance_record_id=finance_id 
                            ))
                            link_msg = " + 耗材库存"

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
                "ID": r.id, "日期": r.date, "币种": r.currency, 
                "收支": "收入" if r.amount > 0 else "支出",
                "金额": r.amount, "分类": r.category, "备注": r.description,
                "当前CNY余额": running_cny, "当前JPY余额": running_jpy
            })
        df_display = pd.DataFrame(processed_data).sort_values(by=["日期", "ID"], ascending=[False, False])
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
        st.dataframe(
            df_display, use_container_width=True, hide_index=True,
            column_config={
                "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD"),
                "金额": st.column_config.NumberColumn("变动金额", format="¥ %.2f"),
                "当前CNY余额": st.column_config.NumberColumn("CNY 结余", format="¥ %.2f"),
                "当前JPY余额": st.column_config.NumberColumn("JPY 结余", format="¥ %.0f"),
            },
            column_order=["日期", "收支", "币种", "金额", "当前CNY余额", "当前JPY余额", "分类", "备注"]
        )
        with st.popover("🗑️ 删除记录"):
            del_options = df_display.to_dict('records')
            selected_del = st.selectbox("选择要删除的记录", del_options, format_func=lambda x: f"{x['日期']} | {x['收支']} {x['金额']} | {x['分类']}")
            
            # === 联动删除逻辑 ===
            if st.button("确认删除选中记录"):
                del_id = selected_del['ID']
                
                # 1. 删除关联的 成本项 (CostItem)
                db.query(CostItem).filter(CostItem.finance_record_id == del_id).delete()
                
                # 2. 删除关联的 固定资产 (FixedAsset)
                db.query(FixedAsset).filter(FixedAsset.finance_record_id == del_id).delete()
                
                # 3. 删除关联的 耗材 (ConsumableItem)
                db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == del_id).delete()
                
                # 4. 最后删除 财务流水 (FinanceRecord)
                db.query(FinanceRecord).filter(FinanceRecord.id == del_id).delete()
                
                db.commit()
                st.toast("财务记录及其关联数据已删除", icon="🗑️")
                st.rerun()
    else:
        st.info("暂无财务记录")