import streamlit as st
import pandas as pd
from datetime import date
from models import FinanceRecord, Product, CostItem, ConsumableItem, FixedAsset, ConsumableLog

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

        # 预定义变量，防止后面未定义报错
        target_consumable_id = None 
        is_consumable_append = False # 标记是否为追加模式

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
                    c_out1, c_out2 = st.columns([2, 1])
                    f_name = c_out1.text_input("支出内容", placeholder="如：打印机")
                    f_shop = c_out2.text_input("店铺/供应商", placeholder="淘宝/Amazon")

                elif exp_type == "耗材购入":
                    # 【修改点 2】耗材选择逻辑
                    # A. 获取现有耗材
                    all_cons = db.query(ConsumableItem).all()
                    con_map = {c.name: c for c in all_cons}
                    con_options = ["➕ 新增耗材项目"] + list(con_map.keys())
                    
                    c_sel, c_shop = st.columns([2, 1])
                    selected_con = c_sel.selectbox("选择耗材", con_options)
                    f_shop = c_shop.text_input("店铺/供应商", placeholder="淘宝/Amazon")

                    if selected_con == "➕ 新增耗材项目":
                        # === 新增模式 ===
                        is_consumable_append = False
                        f_name = st.text_input("新耗材名称", placeholder="如：飞机盒")
                        
                        sub_cats = ["包装材", "无实体", "备用素材", "其他"]
                        final_category = st.selectbox("耗材子分类", sub_cats)
                    else:
                        # === 追加模式 ===
                        is_consumable_append = True
                        target_obj = con_map[selected_con]
                        target_consumable_id = target_obj.id
                        f_name = target_obj.name
                        final_category = target_obj.category
                        
                        st.info(f"将在现有库存 ({target_obj.remaining_qty}) 基础上追加。")
                        # 隐藏显示分类，但传递变量
                        st.caption(f"分类: {final_category}")

                else: 
                    final_category = st.selectbox("费用分类", other_expense_cats)
                    c_out1, c_out2 = st.columns([2, 1])
                    f_name = c_out1.text_input("支出内容", placeholder="如：房租")
                    f_shop = c_out2.text_input("店铺/供应商")

                # === 统一的金额输入区域 ===
                # 针对耗材和固定资产，需要单价和数量
                if exp_type in ["耗材购入", "固定资产购入"]:
                    c_total, c_qty = st.columns(2)
                    calc_total_amount = c_total.number_input("👉 实付总价", min_value=0.0, step=10.0, format="%.2f")
                    f_qty = c_qty.number_input("数量", min_value=1, step=1, value=1)
                    
                    if f_qty > 0: f_price = calc_total_amount / f_qty
                    else: f_price = 0
                else: 
                    # 其他支出
                    f_amount_input = st.number_input("支出金额", min_value=0.0, step=10.0, format="%.2f")
                    calc_total_amount = f_amount_input
                    f_qty = 1

        f_desc = st.text_input("备注说明", placeholder="选填")

        # === 提交逻辑 ===
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
                    db.flush() # 生成ID
                    finance_id = new_finance.id
                    
                    # 2. 联动写入其他表
                    link_msg = ""
                    if rec_type == "支出":
                        if exp_type == "商品成本" and selected_product_id:
                            # ... (商品成本原有保存逻辑保持不变) ...
                            # 请保留原代码中的 CostItem 写入逻辑
                            # 为了简洁，这里省略 Copy Paste，请确保这一块没被删除
                            pass 

                        elif exp_type == "固定资产购入":
                            db.add(FixedAsset(
                                name=f_name, unit_price=f_price, quantity=f_qty, remaining_qty=f_qty,
                                shop_name=f_shop, remarks=f_desc, currency=f_curr,
                                finance_record_id=finance_id 
                            ))
                            link_msg = " + 固定资产库"

                        elif exp_type == "耗材购入":
                            # 【修改点 3】耗材保存逻辑分支
                            
                            # 计算折合 CNY 价值 (用于日志)
                            rate = exchange_rate if f_curr == "JPY" else 1.0
                            val_cny = calc_total_amount * rate

                            if is_consumable_append and target_consumable_id:
                                # A. 追加模式
                                existing_item = db.query(ConsumableItem).filter(ConsumableItem.id == target_consumable_id).first()
                                if existing_item:
                                    # 1. 更新库存
                                    existing_item.remaining_qty += f_qty
                                    
                                    # 2. 更新单价 (采用加权平均，或者更新为最新单价？)
                                    # 这里采用简单策略：更新为【最新单价】，或者保留【加权平均】
                                    # 为了资产计算准确，简单加权：(旧总值 + 新总值) / 新总数
                                    # 注意：这里我们用剩余数量估算旧总值
                                    old_val = existing_item.unit_price * (existing_item.remaining_qty - f_qty) # 减去刚加的f_qty
                                    if existing_item.remaining_qty > 0:
                                        new_avg_price = (old_val + calc_total_amount) / existing_item.remaining_qty
                                        existing_item.unit_price = new_avg_price
                                    
                                    # 3. 记录耗材日志 (补货)
                                    db.add(ConsumableLog(
                                        item_name=existing_item.name,
                                        change_qty=f_qty, # 正数表示补货
                                        value_cny=val_cny,
                                        note=f"财务追加购买: {f_desc}",
                                        date=f_date
                                    ))
                                    link_msg = f" + 耗材补货 (库存: {existing_item.remaining_qty})"
                            else:
                                # B. 新增模式
                                db.add(ConsumableItem(
                                    name=f_name, category=final_category, unit_price=f_price,
                                    initial_quantity=f_qty, remaining_qty=f_qty, shop_name=f_shop, remarks=f_desc,
                                    currency=f_curr, finance_record_id=finance_id 
                                ))
                                # 同时记录一条初始日志
                                db.add(ConsumableLog(
                                    item_name=f_name,
                                    change_qty=f_qty,
                                    value_cny=val_cny,
                                    note=f"初始购入: {f_desc}",
                                    date=f_date
                                ))
                                link_msg = " + 新增耗材"

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
                "金额": abs(r.amount), # 界面显示绝对值
                "分类": r.category, 
                "备注": r.description or "", # 确保不为None
                "当前CNY余额": running_cny, 
                "当前JPY余额": running_jpy
            })
        
        # 按日期倒序排列，并重置索引以供 Editor 使用
        df_display = pd.DataFrame(processed_data).sort_values(by=["日期", "ID"], ascending=[False, False]).reset_index(drop=True)
    else:
        df_display = pd.DataFrame()

    st.divider()
    
    # --- 余额看板 ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("CNY 当前余额", f"¥ {running_cny:,.2f}")
    m2.metric("JPY 当前余额", f"¥ {running_jpy:,.0f}")
    jpy_to_cny = running_jpy * exchange_rate
    m3.metric("JPY折合CNY", f"¥ {jpy_to_cny:,.2f}", help=f"汇率: {exchange_rate*100:.1f}")
    m4.metric("账户总余额 (CNY)", f"¥ {(running_cny + jpy_to_cny):,.2f}")

    # --- 可编辑的流水列表 ---
    if not df_display.empty:
        st.subheader("📝 流水明细")
        
        # 1. 显示编辑器
        edited_df = st.data_editor(
            df_display,
            use_container_width=True,
            hide_index=True,
            key="finance_editor", # 关键 Key，用于捕获修改
            disabled=["当前CNY余额", "当前JPY余额", "ID"], # 禁止修改余额和ID
            column_config={
                "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD", required=True),
                "收支": st.column_config.SelectboxColumn("收支", options=["收入", "支出"], required=True),
                "币种": st.column_config.SelectboxColumn("币种", options=["CNY", "JPY"], required=True),
                "金额": st.column_config.NumberColumn("金额 (绝对值)", min_value=0.01, format="¥ %.2f", required=True),
                "分类": st.column_config.TextColumn("分类", required=True),
                "备注": st.column_config.TextColumn("备注"),
                "当前CNY余额": st.column_config.NumberColumn("CNY 结余", format="¥ %.2f"),
                "当前JPY余额": st.column_config.NumberColumn("JPY 结余", format="¥ %.0f"),
            },
            column_order=["日期", "收支", "币种", "金额", "分类", "备注", "当前CNY余额", "当前JPY余额"]
        )

        # 2. 捕获并处理修改
        # st.session_state["finance_editor"] 包含了修改的变更信息
        if st.session_state.get("finance_editor") and st.session_state["finance_editor"].get("edited_rows"):
            changes = st.session_state["finance_editor"]["edited_rows"]
            
            has_db_change = False
            
            for index, diff in changes.items():
                # 获取原始行的 ID (因为 df_display 是排过序的，index 对应 df_display 的行号)
                original_row = df_display.iloc[int(index)]
                record_id = int(original_row["ID"])
                
                # 获取数据库记录
                record = db.query(FinanceRecord).filter(FinanceRecord.id == record_id).first()
                
                if record:
                    # 获取最新的一行数据 (合并原始数据和修改数据)
                    # 注意：diff 字典里只包含被修改的字段
                    new_date = diff.get("日期", str(record.date)) # data_editor 返回的日期可能是字符串
                    new_type = diff.get("收支", "收入" if record.amount > 0 else "支出")
                    new_curr = diff.get("币种", record.currency)
                    new_abs_amount = float(diff.get("金额", abs(record.amount)))
                    new_cat = diff.get("分类", record.category)
                    new_desc = diff.get("备注", record.description)

                    # 计算新的带符号金额
                    final_amount = new_abs_amount if new_type == "收入" else -new_abs_amount
                    
                    # 更新字段
                    record.date = new_date
                    record.currency = new_curr
                    record.amount = final_amount
                    record.category = new_cat
                    record.description = new_desc
                    
                    has_db_change = True
                    
                    # === 联动更新 CostItem (如果是商品成本) ===
                    # 如果这笔流水关联了成本项，且修改了金额，最好同步更新成本项的实付金额
                    if "金额" in diff:
                        linked_costs = db.query(CostItem).filter(CostItem.finance_record_id == record.id).all()
                        for cost in linked_costs:
                            cost.actual_cost = new_abs_amount
                            # 注意：这里我们假设是一对一关系，或者简单更新。如果有多条CostItem对应一条流水，逻辑会复杂，暂简单处理。
            
            if has_db_change:
                try:
                    db.commit()
                    st.toast("流水记录已更新！", icon="💾")
                    # 必须 rerun 以重新计算余额并刷新表格
                    st.rerun()
                except Exception as e:
                    st.error(f"更新失败: {e}")

        # 3. 删除功能 (保持原有逻辑，移到下方)
        with st.popover("🗑️ 删除记录"):
            del_options = df_display.to_dict('records')
            selected_del = st.selectbox("选择要删除的记录", del_options, format_func=lambda x: f"{x['日期']} | {x['收支']} {x['金额']} | {x['分类']}")
            
            if st.button("确认删除选中记录"):
                del_id = selected_del['ID']
                # 级联删除逻辑
                db.query(CostItem).filter(CostItem.finance_record_id == del_id).delete()
                db.query(FixedAsset).filter(FixedAsset.finance_record_id == del_id).delete()
                db.query(ConsumableItem).filter(ConsumableItem.finance_record_id == del_id).delete()
                db.query(FinanceRecord).filter(FinanceRecord.id == del_id).delete()
                
                db.commit()
                st.toast("删除成功", icon="🗑️")
                st.rerun()
    else:
        st.info("暂无财务记录")