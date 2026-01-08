import streamlit as st
import pandas as pd
from models import Product, CostItem, FinanceRecord

def show_cost_page(db):
    st.header("🧵 商品成本核算")
    
    # 1. 选择商品
    products = db.query(Product).all()
    if not products:
        st.warning("请先在“产品管理”中添加产品！")
        return

    product_names = [p.name for p in products]
    selected_prod_name = st.selectbox("请选择要核算的商品", product_names)
    prod = db.query(Product).filter(Product.name == selected_prod_name).first()
    
    make_qty = prod.total_quantity if prod.total_quantity > 0 else 1
    
    st.divider()

    # ================= 0. 添加预算功能 =================
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

    # 获取数据
    all_items = db.query(CostItem).filter(CostItem.product_id == prod.id).all()
    
    c1, c2 = st.columns([3.5, 1]) 
    
    # ================= 左侧：支出明细表 (可编辑版) =================
    with c1:
        st.subheader("📋 支出明细表")
        
        has_data = False
        
        # 遍历每一个分类
        for cat in all_cats:
            # 筛选该分类下的项目
            cat_items = [i for i in all_items if i.category == cat or (cat=="检品发货等人工费" and "检品" in i.category)]
            
            if cat_items:
                has_data = True
                st.markdown(f"#### 🔹 {cat}")
                
                # --- 1. 准备表格数据 ---
                data_list = []
                # 创建一个映射字典供删除使用 { display_name : item_id }
                delete_options = {}
                
                for i in cat_items:
                    budget_total = i.unit_price * i.quantity
                    real_unit = i.actual_cost / i.quantity if i.quantity > 0 else 0
                    
                    if i.supplier == "预算设定":
                        actual_qty = 0
                        status_label = "📝 预算"
                    else:
                        actual_qty = i.quantity
                        status_label = "💸 实付"

                    row = {
                        "_id": i.id, # 隐藏ID
                        "支出内容": i.item_name,
                        "单位": i.unit,
                        "预算数量": i.quantity,
                        "实际数量": actual_qty,
                        "预算单价": i.unit_price,
                        "实付单价": real_unit,
                        "预算总价": budget_total,
                        "实付总价": i.actual_cost,
                        "供应商": i.supplier,
                        "备注": i.remarks,
                    }
                    data_list.append(row)
                    
                    # 构建删除选项的显示文本
                    option_label = f"{i.item_name} | ￥{i.actual_cost} ({i.supplier})"
                    delete_options[option_label] = i.id
                
                df = pd.DataFrame(data_list)

                # --- 2. 渲染可编辑表格 (去掉删除列) ---
                if cat in detailed_cats:
                    col_order = ["支出内容", "单位", "预算数量", "预算单价", "预算总价", "实际数量", "实付单价", "实付总价", "供应商", "备注"]
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
                        "实际数量": st.column_config.NumberColumn(format="%d", disabled=True),
                        # 可编辑列
                        "单位": st.column_config.TextColumn(),
                        "预算数量": st.column_config.NumberColumn(min_value=0, step=1, format="%d", required=True),
                        "预算单价": st.column_config.NumberColumn(min_value=0.0, step=0.1, format="¥ %.2f", required=True),
                        "供应商": st.column_config.TextColumn(),
                        "备注": st.column_config.TextColumn(),
                    }
                )

                # --- 3. 处理编辑保存 ---
                # 检测 edited_df 是否有变化
                for index, row in edited_df.iterrows():
                    item_id = row["_id"]
                    target_item = db.query(CostItem).filter(CostItem.id == item_id).first()
                    
                    if target_item:
                        has_change = False
                        
                        # 检查各个字段是否有变化
                        if row.get("单位") != (target_item.unit or ""):
                            target_item.unit = row.get("单位")
                            has_change = True
                        if int(row.get("预算数量", 0)) != target_item.quantity:
                            target_item.quantity = int(row.get("预算数量"))
                            has_change = True
                        if abs(row.get("预算单价", 0) - target_item.unit_price) > 0.01:
                            target_item.unit_price = row.get("预算单价")
                            has_change = True
                        if row.get("供应商") != (target_item.supplier or ""):
                            target_item.supplier = row.get("供应商")
                            has_change = True
                        if row.get("备注") != (target_item.remarks or ""):
                            target_item.remarks = row.get("备注")
                            has_change = True
                        
                        if has_change:
                            db.commit()
                            st.toast(f"已更新: {target_item.item_name}", icon="💾")
                            # 这里不立即rerun，以免打断编辑流，但数据已存

                # --- 4. 删除功能区 (使用 Popover 实现按钮确认) ---
                # 将删除功能折叠或放在表格下方，避免误触
                c_del_sel, c_del_btn = st.columns([3, 1])
                
                # 选择要删除的项目
                selected_del_label = c_del_sel.selectbox(
                    "选择要删除的项目", 
                    options=list(delete_options.keys()), 
                    key=f"sel_del_{cat}",
                    label_visibility="collapsed",
                    index=None,
                    placeholder="选择要删除的项目..."
                )
                
                # 删除按钮 + 确认弹窗
                if selected_del_label:
                    # 使用 popover 作为确认框
                    with c_del_btn.popover("🗑️ 删除", use_container_width=True):
                        st.markdown(f"**确认删除 `{selected_del_label.split('|')[0].strip()}` 吗？**")
                        st.warning("⚠️ 若此项目已关联财务流水，流水将被标记为【取消/冲销】。")
                        
                        if st.button("🔴 确认删除", key=f"btn_confirm_del_{cat}", type="primary"):
                            del_id = delete_options[selected_del_label]
                            target_item = db.query(CostItem).filter(CostItem.id == del_id).first()
                            
                            if target_item:
                                # 联动处理财务流水
                                if target_item.finance_record_id:
                                    fin_rec = db.query(FinanceRecord).filter(FinanceRecord.id == target_item.finance_record_id).first()
                                    if fin_rec:
                                        fin_rec.amount = 0  # 金额归零
                                        fin_rec.category = "取消/冲销"
                                        fin_rec.description = f"【已取消】{fin_rec.description}"
                                        st.toast(f"关联流水已取消 (ID: {fin_rec.id})", icon="🔄")
                                
                                db.delete(target_item)
                                db.commit()
                                st.toast("删除成功", icon="🗑️")
                                st.rerun()

                # --- 统计区域 ---
                cat_total_real = sum([i.actual_cost for i in cat_items])
                cat_total_budget = sum([i.unit_price * i.quantity for i in cat_items])
                diff_total = cat_total_real - cat_total_budget
                cat_unit_real = cat_total_real / make_qty
                
                if cat in detailed_cats:
                    cat_unit_budget = cat_total_budget / make_qty
                    diff_unit = cat_unit_real - cat_unit_budget
                    s1, s2, s3 = st.columns([1, 1, 1])
                    s1.metric(label="实付总合计", value=f"¥ {cat_total_real:,.2f}", delta=f"{diff_total:,.2f}", delta_color="inverse")
                    s2.metric(label="单套实付均摊", value=f"¥ {cat_unit_real:,.2f}", delta=f"{diff_unit:,.2f}", delta_color="inverse")
                    s3.caption(f"🎯 预算基准: 总 ¥{cat_total_budget:,.2f} | 单套 ¥{cat_unit_budget:,.2f}")
                else:
                    s1, s2 = st.columns([1, 2])
                    s1.metric(label="实付总合计", value=f"¥ {cat_total_real:,.2f}", delta=f"{diff_total:,.2f}", delta_color="inverse")
                    s2.caption(f"📊 分摊到单套: `¥{cat_unit_real:,.2f}` | 预算合计: `¥{cat_total_budget:,.2f}`")
                
                st.write("") 
                st.divider()

        if not has_data:
            st.info("该商品暂无支出或预算记录。")

    # ================= 右侧：总核算结果 =================
    with c2:
        with st.container(border=True):
            st.subheader("📊 总核算结果")
            total_cost = sum([i.actual_cost for i in all_items])
            
            st.metric("📦 项目总支出 (实付)", f"¥ {total_cost:,.2f}")
            st.metric("🔢 产品制作总数", f"{prod.total_quantity} 件")
            st.divider()
            
            if prod.total_quantity > 0:
                unit_cost = total_cost / prod.total_quantity
                st.metric("💰 单套综合成本 (实付)", f"¥ {unit_cost:,.2f}")
                
                st.caption("各平台毛利参考:")
                if prod.price_weidian > 0:
                    margin = prod.price_weidian - unit_cost
                    st.metric("微店单件毛利", f"¥ {margin:,.2f}", delta=f"毛利率 {margin/prod.price_weidian*100:.1f}%")
                    st.metric("总预期毛利", f"¥ {margin * prod.total_quantity:,.2f}")
                
                if prod.price_offline_cn > 0:
                     margin_off = prod.price_offline_cn - unit_cost
                     st.metric("线下单件毛利", f"¥ {margin_off:,.2f}", delta_color="off")
                     st.metric("总预期毛利", f"¥ {margin_off * prod.total_quantity:,.2f}")
            else:
                st.error("⚠️ 产品总数为0")