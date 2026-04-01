import streamlit as st
import pandas as pd
from services.cost_service import CostService
from constants import PRODUCT_COST_CATEGORIES
from cache_manager import sync_all_caches

def show_cost_page(db):
    st.header("🧵 商品成本核算")
    
    service = CostService(db)
    
    # === 0. 全局设置 ===
    exchange_rate_input = st.session_state.get("global_rate_input", 4.8)
    exchange_rate = exchange_rate_input / 100.0

    # 1. 选择商品
    products = service.get_all_products()
    if not products:
        st.warning("请先在“产品管理”中添加产品！")
        return

    product_names = [p.name for p in products]
    selected_prod_name = st.selectbox("请选择要核算的商品", product_names)
    prod = service.get_product_by_name(selected_prod_name)
    
    # 可销售数量 (产品级)
    make_qty = prod.marketable_quantity if prod.marketable_quantity is not None else prod.total_quantity
    
    st.divider()

    # ================= 1. 添加预算功能 (数据录入区) =================
    with st.expander("➕ 添加预算项目 (Budget)", expanded=False):
        st.caption("在此处录入的条目仅作为预算参考，实付金额默认为0。")
        
        c_cat, c_name = st.columns([1, 1.5])
        b_cat = c_cat.selectbox("预算分类", service.ALL_CATS, key="budget_cat_select")
        b_name = c_name.text_input("项目名称", placeholder="如：面料预算", key="budget_name_input")
        
        b_unit_price = 0.0
        b_qty = 1.0
        b_unit_text = ""
        b_remarks = ""
        
        if b_cat in service.DETAILED_CATS:
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
                try:
                    service.add_budget_item(prod.id, b_cat, b_name, b_unit_price, b_qty, b_unit_text, b_remarks)
                    st.toast("预算已添加", icon="✅")
                    
                    keys_to_clear = ["budget_name_input", "b_p_in", "b_q_in", "b_u_in", "b_t_in", "b_r_in"]
                    for k in keys_to_clear:
                        if k in st.session_state:
                            del st.session_state[k]
                            
                    st.rerun()
                except Exception as e:
                    st.error(f"保存失败: {e}")

    # 获取当前商品的所有成本项
    all_items = service.get_cost_items(prod.id)
    
    # 布局：左侧表格，右侧总览
    c1, c2 = st.columns([3.5, 1.2]) 
    
    # ================= 左侧：支出明细表 (可编辑) =================
    with c1:
        st.subheader("📋 支出明细表")
        has_data = False
        
        for cat in service.ALL_CATS:
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
                    actual_unit_price = (i.actual_cost / i.quantity) if (not is_budget_item and i.quantity > 0) else None

                    data_list.append({
                        "_id": i.id,
                        "支出内容": i.item_name,
                        "单位": i.unit or "",
                        "预算数量": budget_qty or 0,
                        "预算单价": budget_unit_price or 0,
                        "预算总价": budget_total or 0,
                        "实际数量": actual_qty or 0,
                        "实付单价": actual_unit_price or 0,
                        "实付总价": actual_total or 0,
                        "供应商": i.supplier or "",
                        "相关链接": getattr(i, 'url', '') or "",
                        "备注": i.remarks or "",
                        "_is_budget": is_budget_item
                    })
                    delete_options[f"{i.item_name} | ￥{i.actual_cost} ({i.supplier or '未填'})"] = i.id
                
                df = pd.DataFrame(data_list)
                
                # --- 渲染表格 ---
                if cat in service.DETAILED_CATS:
                    col_order = ["支出内容", "单位", "预算数量", "预算单价", "预算总价", "实际数量", "实付单价", "实付总价", "供应商", "相关链接", "备注"]
                    col_cfg = {
                        "_id": None, "_is_budget": None,
                        "支出内容": st.column_config.TextColumn(disabled=True),
                        "单位": st.column_config.TextColumn(), 
                        "预算数量": st.column_config.NumberColumn(min_value=0.0, step=0.01, format="%.2f"),
                        "预算单价": st.column_config.NumberColumn(min_value=0.0, step=0.01, format="¥ %.2f"),
                        "预算总价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                        "实际数量": st.column_config.NumberColumn(format="%.2f", disabled=True),
                        "实付单价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                        "实付总价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                        "供应商": st.column_config.TextColumn(),
                        "相关链接": st.column_config.LinkColumn("相关链接", display_text="🔗 URL"),
                        "备注": st.column_config.TextColumn(),
                    }
                else:
                    col_order = ["支出内容", "预算总价", "实付总价", "供应商", "相关链接", "备注"]
                    col_cfg = {
                        "_id": None, "_is_budget": None,
                        "支出内容": st.column_config.TextColumn(disabled=True),
                        "预算总价": st.column_config.NumberColumn(min_value=0.0, step=10.0, format="¥ %.2f"),
                        "实付总价": st.column_config.NumberColumn(format="¥ %.2f", disabled=True),
                        "供应商": st.column_config.TextColumn(),
                        "相关链接": st.column_config.LinkColumn("相关链接", display_text="🔗 URL"),
                        "备注": st.column_config.TextColumn(),
                    }

                edited_df = st.data_editor(
                    df, key=f"editor_{cat}_{prod.id}", column_order=col_order,
                    width="stretch", hide_index=True, column_config=col_cfg
                )

                # --- 处理编辑保存 ---
                if st.session_state.get(f"editor_{cat}_{prod.id}") and st.session_state[f"editor_{cat}_{prod.id}"].get("edited_rows"):
                    changes = st.session_state[f"editor_{cat}_{prod.id}"]["edited_rows"]
                    any_db_change = False
                    
                    for idx_str, diff in changes.items():
                        row_data = df.iloc[int(idx_str)]
                        item_id = int(row_data["_id"])
                        is_budget = bool(row_data["_is_budget"])
                        
                        updates = {}
                        if "单位" in diff: updates["unit"] = diff["单位"]
                        if "供应商" in diff: updates["supplier"] = diff["供应商"]
                        if "相关链接" in diff: updates["url"] = diff["相关链接"]
                        if "备注" in diff: updates["remarks"] = diff["备注"]
                        
                        updates["is_budget"] = is_budget
                        if is_budget:
                            if "预算数量" in diff: updates["quantity"] = diff["预算数量"]
                            if "预算单价" in diff: updates["unit_price"] = diff["预算单价"]
                            if "预算总价" in diff: updates["total_budget"] = diff["预算总价"]
                        
                        if service.update_cost_item(item_id, updates):
                            any_db_change = True
                    
                    if any_db_change:
                        st.toast(f"已更新: {cat}", icon="💾")
                        
                        # 👇 核心修复：强制清空数据表格的记忆，防止它用旧状态覆盖新数据
                        if f"editor_{cat}_{prod.id}" in st.session_state:
                            del st.session_state[f"editor_{cat}_{prod.id}"]
                            
                        st.rerun()

                # --- 删除功能 ---
                c_del_sel, c_del_btn = st.columns([3, 1])
                selected_del_label = c_del_sel.selectbox("选择要删除的项目", options=list(delete_options.keys()), key=f"sel_del_{cat}", label_visibility="collapsed", index=None, placeholder="选择要删除的项目...")
                
                if selected_del_label:
                    with c_del_btn.popover("🗑️ 删除", width="stretch"):
                        st.markdown(f"确认删除 `{selected_del_label.split('|')[0].strip()}` ？")
                        if st.button("🔴 确认", key=f"btn_confirm_del_{cat}", type="primary"):
                            try:
                                del_id = delete_options[selected_del_label]
                                service.delete_cost_item(del_id)
                                
                                # 👇 核心修复：清空下拉框和表格的记忆
                                if f"sel_del_{cat}" in st.session_state:
                                    del st.session_state[f"sel_del_{cat}"]
                                if f"editor_{cat}_{prod.id}" in st.session_state:
                                    del st.session_state[f"editor_{cat}_{prod.id}"]
                                    
                                st.rerun()
                            except Exception as e:
                                st.error(f"删除失败: {e}")

                # 计算小计并显示
                cat_total_real = sum([i.actual_cost for i in cat_items])
                budget_map = {i.item_name: i.unit_price * i.quantity for i in cat_items if i.supplier == "预算设定"}
                cat_total_budget = sum(budget_map.values())
                for i in cat_items:
                    if i.supplier != "预算设定" and i.item_name not in budget_map:
                        cat_total_budget += i.actual_cost

                cat_unit_real = cat_total_real / make_qty if make_qty > 0 else 0
                cat_unit_budget = cat_total_budget / make_qty if make_qty > 0 else 0

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
            
            # --- 计算总成本 (产品级) ---
            total_real_cost = sum([i.actual_cost for i in all_items])
            budget_map = {i.item_name: i.unit_price * i.quantity for i in all_items if i.supplier == "预算设定"}
            total_budget_cost = sum(budget_map.values())
            for i in all_items:
                if i.supplier != "预算设定" and i.item_name not in budget_map:
                    total_budget_cost += i.actual_cost

            st.metric("📦 项目总支出 (实付)", f"¥ {total_real_cost:,.2f}")
            st.caption(f"📝 预算总成本: ¥ {total_budget_cost:,.2f}")
            st.divider()
            
            # 预计可销售数量 (产品级)
            st.metric("🔢 预计可销售数量", f"{int(make_qty)} 件", help="此数值通过库存变动自动更新。")
            st.divider()
            
            # --- 价格获取辅助函数：从颜色款式对象获取价格 ---
            def get_color_price(color_obj, platform_key):
                if not color_obj or not color_obj.prices:
                    return 0.0
                for p in color_obj.prices:
                    if p.platform == platform_key:
                        return p.price
                return 0.0

            # --- 计算单件综合成本 (产品级) ---
            if make_qty > 0:
                unit_real_cost = total_real_cost / make_qty
                unit_budget_cost = total_budget_cost / make_qty
                
                st.metric("💰 单套综合成本 (实付)", f"¥ {unit_real_cost:,.2f}")
                st.caption(f"📝 预算单套成本: ¥ {unit_budget_cost:,.2f}")
                st.divider()

                # --- 分颜色款式显示毛利参考 ---
                st.markdown("**📈 各款式毛利参考 (基于实付)**")
                
                # 定义平台映射
                platforms_config = [
                    ("weidian", "微店 (CNY)", False),
                    ("offline_cn", "中国线下 (CNY)", False),
                    ("other", "其他 (CNY)", False),
                    ("booth", "Booth (JPY)", True),
                    ("instagram", "Instagram (JPY)", True),
                    ("offline_jp", "日本线下 (JPY)", True),
                    ("other_jpy", "其他 (JPY)", True),
                ]

                # 遍历产品的每一个款式
                for color in prod.colors:
                    with st.expander(f"🎨 款式：{color.color_name}", expanded=False):
                        has_price_for_this_color = False
                        
                        for pf_key, label, is_jpy in platforms_config:
                            # 获取该款式在特定平台的价格
                            price_val = get_color_price(color, pf_key)
                            
                            if price_val > 0:
                                has_price_for_this_color = True
                                
                                # 平台手续费计算 (针对微店和Booth)
                                fee_val = 0.0
                                if pf_key == "weidian":
                                    fee_val = price_val * 0.006 # 微店0.6%
                                elif pf_key == "booth":
                                    fee_val = price_val * 0.056 + 22 # Booth 5.6% + 22JPY
                                    
                                # 换算为 CNY (含手续费折算)
                                price_cny = price_val * exchange_rate if is_jpy else price_val
                                fee_cny = fee_val * exchange_rate if is_jpy else fee_val
                                
                                # 毛利 = 平台折算价 - 预估手续费 - 产品单套综合成本
                                margin = price_cny - fee_cny - unit_real_cost
                                margin_rate = (margin / price_cny * 100) if price_cny > 0 else 0
                                
                                st.markdown(f"**{label}**")
                                if is_jpy: st.caption(f"定价: {price_val:,.0f} JPY")
                                
                                st.metric(
                                    label="单件毛利 (已扣手续费)", 
                                    value=f"¥ {margin:,.2f}", 
                                    delta=f"{margin_rate:.1f}%",
                                    delta_color="normal" if margin > 0 else "inverse"
                                )
                                # 新增：上方小字显示预估手续费
                                st.caption(f"预估单件手续费: ¥ {fee_cny:,.2f}")
                                
                                # 这里的总预期毛利可以根据该款式的计划数量来算
                                total_profit = margin * color.quantity
                                st.caption(f"该款式预期总毛利: ¥ {total_profit:,.2f}")
                                st.divider()
                        
                        if not has_price_for_this_color:
                            st.caption("该款式暂未在商品管理中设置任何价格")
            else:
                st.error("⚠️ 预计数量为 0，无法计算毛利。")

    # ================= 5. 强制结单/修正功能 =================
    with st.expander("🛠️ 生产结单 / 账目修正 (高级)", expanded=False):
        st.warning("⚠️ **功能说明**：如果该商品已经生产完成，但在【公司资产一览】中仍显示有“在制资产”余额，请点击下方按钮。")
        
        current_offset = service.get_wip_offset(prod.id)
        remaining_wip = total_real_cost + current_offset
        
        c_fix1, c_fix2 = st.columns([2, 1])
        c_fix1.metric("当前残留 WIP (应为0)", f"¥ {remaining_wip:,.2f}")
        
        if c_fix2.button("🚀 强制修正 + 同步大货资产", type="primary"):
            try:
                added_val, _ = service.perform_wip_fix(prod.id)
                st.success(f"修正完成！追加成本 {added_val:,.2f} 已结转。")
                sync_all_caches()
                st.rerun()
            except Exception as e:
                st.error(f"修正失败: {e}")

        st.markdown("---")
        st.subheader("⚖️ 库存价值重估 (Revaluation)")
        st.caption("当单价因追加成本或调整可售数量发生剧烈变化时，使用此功能将账面资产价值同步为 [剩余数量 × 当前单价]。")

        reval_data = service.calculate_revaluation_data(prod.id)
        if reval_data:
            c_rv1, c_rv2, c_rv3 = st.columns(3)
            c_rv1.metric("当前实际库存", f"{reval_data['current_stock_qty']} 件")
            c_rv2.metric("当前账面价值", f"¥ {reval_data['current_inv_val']:,.2f}")
            c_rv3.metric("目标重估价值", f"¥ {reval_data['target_inv_val']:,.2f}", help=f"计算公式: {reval_data['current_stock_qty']} * {reval_data['unit_cost']:.2f}")

            if abs(reval_data['diff']) > 1.0:
                st.info(f"💡 检测到价值偏差: ¥ {reval_data['diff']:+,.2f}")
                if st.button("🔄 执行资产重估 / 补差", type="secondary"):
                    try:
                        service.perform_inventory_revaluation(prod.id)
                        st.success("重估完成！账面资产已与最新单价对齐。")
                        sync_all_caches()
                        st.rerun()
                    except Exception as e:
                        st.error(f"重估失败: {e}")
            else:
                st.success("✅ 账面价值与理论价值一致，无需重估。")