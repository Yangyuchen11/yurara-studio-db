import streamlit as st
import pandas as pd
from models import Product, CostItem, FinanceRecord

def show_cost_page(db):
    st.header("🧵 商品成本核算")
    
    # === 0. 全局设置 ===
    # 获取全局汇率 (用于折算日元平台的毛利)
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
    
    # 【关键修改 1】: 强制使用商品管理页面设定的总数作为计算基准
    make_qty = prod.total_quantity 
    
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
        b_qty = 1
        b_unit_text = ""
        b_remarks = ""
        
        if b_cat in detailed_cats:
            c1_b, c2_b, c3_b = st.columns([1, 1, 1])
            b_price_input = c1_b.number_input("预算单价", min_value=0.0, step=1.0, format="%.2f", key="b_p_in")
            b_qty_input = c2_b.number_input("预算数量", min_value=1, step=1, value=1, key="b_q_in")
            b_unit_text = c3_b.text_input("单位", placeholder="米/个/件", key="b_u_in")
            
            st.markdown(f"**💰 预算总价: ¥ {b_price_input * b_qty_input:,.2f}**")
            b_unit_price = b_price_input
            b_qty = b_qty_input
        else:
            b_total_input = st.number_input("预算总价", min_value=0.0, step=100.0, format="%.2f", key="b_t_in")
            b_unit_price = b_total_input
            b_qty = 1

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
            # 筛选该分类下的项目
            cat_items = [i for i in all_items if i.category == cat or (cat=="检品发货等人工费" and "检品" in i.category)]
            
            if cat_items:
                has_data = True
                st.markdown(f"#### 🔹 {cat}")
                
                # --- 准备表格数据 ---
                data_list = []
                # 创建映射字典用于删除 { display_name : item_id }
                delete_options = {}
                
                for i in cat_items:
                    budget_total = i.unit_price * i.quantity
                    real_unit = i.actual_cost / i.quantity if i.quantity > 0 else 0
                    
                    row = {
                        "_id": i.id, # 隐藏ID用于更新
                        "支出内容": i.item_name,
                        "单位": i.unit,
                        "预算数量": i.quantity,
                        "实际数量": i.quantity if i.supplier != "预算设定" else 0, # 仅展示用
                        "预算单价": i.unit_price,
                        "实付单价": real_unit,
                        "预算总价": budget_total,
                        "实付总价": i.actual_cost,
                        "供应商": i.supplier,
                        "备注": i.remarks,
                    }
                    data_list.append(row)
                    
                    option_label = f"{i.item_name} | ￥{i.actual_cost} ({i.supplier})"
                    delete_options[option_label] = i.id
                
                df = pd.DataFrame(data_list)

                # --- 渲染可编辑表格 ---
                if cat in detailed_cats:
                    col_order = ["支出内容", "单位", "预算数量", "预算单价", "预算总价", "实付单价", "实付总价", "供应商", "备注"]
                else:
                    col_order = ["支出内容", "预算总价", "实付总价", "供应商", "备注"] 

                edited_df = st.data_editor(
                    df,
                    key=f"editor_{cat}_{prod.id}",
                    column_order=col_order,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "_id": None,
                        "支出内容": st.column_config.TextColumn(disabled=True),
                        "实付总价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                        "预算总价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                        "实付单价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                        "预算数量": st.column_config.NumberColumn(min_value=0, step=1, format="%d", required=True),
                        "预算单价": st.column_config.NumberColumn(min_value=0.0, step=0.1, format="¥ %.2f", required=True),
                        "供应商": st.column_config.TextColumn(),
                        "备注": st.column_config.TextColumn(),
                    }
                )

                # --- 处理编辑保存 ---
                for index, row in edited_df.iterrows():
                    item_id = row["_id"]
                    target_item = db.query(CostItem).filter(CostItem.id == item_id).first()
                    
                    if target_item:
                        has_change = False
                        # 简单的变更检测
                        if row.get("单位") != (target_item.unit or ""):
                            target_item.unit = row.get("单位"); has_change = True
                        if int(row.get("预算数量", 0)) != target_item.quantity:
                            target_item.quantity = int(row.get("预算数量")); has_change = True
                        if abs(row.get("预算单价", 0) - target_item.unit_price) > 0.01:
                            target_item.unit_price = row.get("预算单价"); has_change = True
                        if row.get("供应商") != (target_item.supplier or ""):
                            target_item.supplier = row.get("供应商"); has_change = True
                        if row.get("备注") != (target_item.remarks or ""):
                            target_item.remarks = row.get("备注"); has_change = True
                        
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
                                # 若关联了财务流水，需置零
                                if item_to_del.finance_record_id:
                                    fin_rec = db.query(FinanceRecord).filter(FinanceRecord.id == item_to_del.finance_record_id).first()
                                    if fin_rec:
                                        fin_rec.amount = 0; fin_rec.category = "取消/冲销"; fin_rec.description = f"【已取消】{fin_rec.description}"
                                db.delete(item_to_del)
                                db.commit()
                                st.rerun()

                # --- 分类小计 ---
                cat_total_real = sum([i.actual_cost for i in cat_items])
                st.caption(f"小计实付: ¥ {cat_total_real:,.2f}")
                st.divider()

        if not has_data:
            st.info("该商品暂无支出或预算记录。")

    # ================= 右侧：总核算结果 (核心修改区) =================
    with c2:
        with st.container(border=True):
            st.subheader("📊 核算面板")
            total_cost = sum([i.actual_cost for i in all_items])
            
            st.metric("📦 项目总支出 (实付)", f"¥ {total_cost:,.2f}")
            
            # 【修改点 2】: 标签更名为“预计制作总数量”，且数值只读
            st.metric("🔢 预计制作总数量", f"{make_qty} 件")
            
            st.divider()
            
            if make_qty > 0:
                unit_cost = total_cost / make_qty
                st.metric("💰 单套综合成本 (实付)", f"¥ {unit_cost:,.2f}")
                
                st.divider()
                st.markdown("**📈 各平台毛利参考**")
                
                # 【修改点 3】: 动态渲染所有设定了价格的平台毛利
                # 格式: (数据库字段名, 显示名称, 是否为日元)
                platforms_config = [
                    ("price_weidian", "微店 (CNY)", False),
                    ("price_offline_cn", "中国线下 (CNY)", False),
                    ("price_other", "其他 (CNY)", False),
                    ("price_booth", "Booth (JPY)", True),
                    ("price_instagram", "Instagram (JPY)", True),
                    ("price_offline_jp", "日本线下 (JPY)", True),
                    ("price_other_jpy", "其他 (JPY)", True),
                ]

                # 遍历所有平台配置
                has_platform_price = False
                for field, label, is_jpy in platforms_config:
                    # 使用 getattr 安全获取属性，默认为 0
                    price_val = getattr(prod, field, 0)
                    
                    if price_val > 0:
                        has_platform_price = True
                        # 计算人民币等值价格
                        price_cny = price_val * exchange_rate if is_jpy else price_val
                        
                        # 计算毛利
                        margin = price_cny - unit_cost
                        margin_rate = (margin / price_cny * 100) if price_cny > 0 else 0
                        
                        # 使用 expander 让布局更整洁
                        with st.expander(f"{label}", expanded=True):
                            # 显示原币种售价 (如果是日元)
                            if is_jpy:
                                st.caption(f"定价: {price_val:,.0f} JPY")
                            
                            st.metric(
                                label="单件毛利", 
                                value=f"¥ {margin:,.2f}", 
                                delta=f"{margin_rate:.1f}%",
                                delta_color="normal" if margin > 0 else "inverse"
                            )
                            # 显示总预期毛利
                            total_profit = margin * make_qty
                            st.caption(f"总预期毛利: ¥ {total_profit:,.2f}")

                if not has_platform_price:
                    st.caption("暂未在商品管理中设置任何平台价格")

            else:
                st.error("⚠️ 预计制作总数为 0，请先在【商品管理】中设定规格与数量。")