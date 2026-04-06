import streamlit as st
import pandas as pd
from datetime import date
from services.inventory_service import InventoryService
from cache_manager import sync_all_caches
from constants import PRODUCT_COST_CATEGORIES, StockLogReason

if hasattr(st, "fragment"):
    fragment_decorator = st.fragment
else:
    fragment_decorator = st.experimental_fragment

# ================= 新增：独立的局部刷新变动录入面板 =================
@fragment_decorator
def render_inventory_movement_panel(db, service, selected_product_id, p_name, colors, wh_options):
    st.subheader("📝 库存变动录入")
    if not wh_options:
        st.warning("⚠️ 请先到【仓库管理】标签页中添加至少一个仓库！")
        return
        
    with st.container(border=True):
        c_date, c_type = st.columns(2)
        input_date = c_date.date_input("日期", value=date.today())
        move_type = c_type.selectbox("变动类型", [
            StockLogReason.IN_INSPECT, StockLogReason.INSPECT_COMPLETED, 
            StockLogReason.OTHER_IN, StockLogReason.OUT_STOCK, StockLogReason.TRANSFER
        ])
        
        selected_to_wh_id = None
        if move_type == StockLogReason.TRANSFER:
            c_wh_from, c_wh_to = st.columns(2)
            wh_options_from = {"未分配仓库 (旧数据)": None}
            wh_options_from.update(wh_options)
            wh_from_label = c_wh_from.selectbox("移出仓库", list(wh_options_from.keys()))
            default_to_idx = 1 if len(wh_options) > 1 else 0
            wh_to_label = c_wh_to.selectbox("移入仓库", list(wh_options.keys()), index=default_to_idx)
            selected_wh_id = wh_options_from[wh_from_label]
            selected_to_wh_id = wh_options[wh_to_label]
        else:
            wh_label = st.selectbox("目标操作仓库", list(wh_options.keys()))
            selected_wh_id = wh_options[wh_label]
        
        color_options = [c.color_name for c in colors] if selected_product_id and colors else ["通用"]
        
        c_var, c_set, c_pt, c_qty = st.columns([1.2, 0.8, 1, 1], vertical_alignment="bottom")
        p_var = c_var.selectbox("款式", color_options)
        
        current_parts = []
        if selected_product_id:
            target_c = next((c for c in colors if c.color_name == p_var), None)
            if target_c and target_c.parts:
                current_parts = [p.part_name for p in target_c.parts]
        
        if current_parts:
            is_set = c_set.checkbox("整套操作", value=True, help="该款式所有部件同比例增减，并记账。")
        else:
            is_set = True
            c_set.checkbox("整套操作", value=True, disabled=True, help="该款式未拆分部件，默认整套。")
        
        p_part = None
        if not is_set and current_parts:
            p_part = c_pt.selectbox("具体部件", current_parts)
        else:
            c_pt.selectbox("具体部件", ["-"], disabled=True)
            
        input_qty = c_qty.number_input("数量", min_value=1, step=1)
        
        out_type = "其他"
        cons_cat = "其他成本"
        cons_content = ""
        p_remark = st.text_input("备注", placeholder="选填备注")

        if move_type == StockLogReason.OUT_STOCK:
            out_type = st.radio("出库类型", ["消耗", "其他"], horizontal=True)
            if out_type == "消耗":
                c_cons1, c_cons2 = st.columns([1, 2])
                cons_cat = c_cons1.selectbox("计入成本分类", service.COST_CATEGORIES)
                cons_content = c_cons2.text_input("消耗内容 (必填)", placeholder="如：宣发样衣")
        
        if st.button("🚀 提交变动", type="primary", use_container_width=True):
            if move_type == StockLogReason.OUT_STOCK and out_type == "消耗" and not cons_content.strip():
                st.error("❌ 请填写【消耗内容】。")
            else:
                try:
                    msg = service.add_inventory_movement(
                        product_id=selected_product_id, product_name=p_name, variant=p_var,
                        quantity=input_qty, move_type=move_type, date_obj=input_date,
                        remark=p_remark, warehouse_id=selected_wh_id, to_warehouse_id=selected_to_wh_id,
                        is_set=is_set, part_name=p_part,
                        out_type=out_type, cons_cat=cons_cat, cons_content=cons_content
                    )
                    service.commit()
                    st.toast(msg, icon="✅")
                    # 提交变动后，强制刷新全局，以便外面的表格能看到最新数据
                    st.rerun() 
                except Exception as e:
                    service.db.rollback()
                    st.error(f"操作失败: {e}")

def show_inventory_page(db):
    st.header("📦 库存管理系统")
    
    service = InventoryService(db)
    tab1, tab2 = st.tabs(["📦 库存管理与操作", "🏢 仓库管理与明细"])
    
    # ================= 标签页 1：库存管理 =================
    with tab1:
        products = service.get_all_products()
        product_names = [p.name for p in products]
        warehouses = service.get_all_warehouses()
        wh_options = {w.name: w.id for w in warehouses}
        
        c_sel, c_btn, _ = st.columns([1.5, 1.5, 2], vertical_alignment="bottom")
        p_name = c_sel.selectbox("选择产品", product_names or ["暂无产品"])
        
        selected_product_id = None
        colors = []

        if products and p_name != "暂无产品":
            selected_product = next((p for p in products if p.name == p_name), None)
            selected_product_id = selected_product.id
            colors = service.get_product_colors(selected_product_id)
            
            with c_btn:
                wip_balance = service.get_wip_balance(selected_product_id)
                if not selected_product.is_production_completed or abs(wip_balance) > 0.01:
                    if st.button("🚀 生产完成 (清零在制)", help="点击清零在制资产并根据已生产数量重新计算可销售数量", use_container_width=True):
                        try:
                            service.clear_wip_for_product(selected_product_id)
                            st.toast("在制资产已清零，可售数量已重新核算！", icon="✅")
                            sync_all_caches()
                            st.rerun()
                        except Exception as e:
                            st.error(f"操作失败: {e}")
                else:
                    st.markdown(
                        "<div style='display: flex; align-items: center; justify-content: center; "
                        "background-color: rgba(76, 175, 80, 0.1); border: 1px solid #4caf50; "
                        "border-radius: 6px; color: #4caf50; font-size: 15px; font-weight: bold; "
                        "height: 38px; margin-bottom: 16px;'>"
                        "✅ 已完成生产结单</div>", 
                        unsafe_allow_html=True
                    )
            
            stats = service.get_stock_overview_by_parts(selected_product_id, p_name)
            
            if stats:
                cols_cfg = [1.5, 1, 1, 1, 1, 1]
                h1, h2, h3, h4, h5, h6 = st.columns(cols_cfg)
                h1.markdown("**款式**")
                h2.markdown("**计划生产**")
                h3.markdown("**已生产**")
                h4.markdown("**验收中**")  
                h5.markdown("**实库存 (成套)**") 
                h6.markdown("**状态**")
                
                st.markdown("<hr style='margin: 5px 0; opacity:0.5;'>", unsafe_allow_html=True)
                
                excess_parts_data = []

                for c in colors:
                    v_name = c.color_name
                    s = stats.get(v_name, {})
                    actual_qty = s.get("actual", 0)
                    status = "🔴 缺货" if actual_qty <= 0 else "🟢 有货"

                    r1, r2, r3, r4, r5, r6 = st.columns(cols_cfg)
                    r1.write(f"🎨 {v_name}")
                    r2.write(f"**{s.get('planned', 0)}**")
                    r3.write(f"{s.get('produced', 0)}")
                    r4.write(f"{s.get('inspecting', 0)}")
                    r5.write(f"{actual_qty}")
                    r6.write(status)
                    st.markdown("<hr style='margin: 5px 0; opacity:0.1;'>", unsafe_allow_html=True)
                    
                    for pt, qty in s.get("excess", {}).items():
                        excess_parts_data.append({"款式": v_name, "散落部件": pt, "多余数量": qty})

                if excess_parts_data:
                    with st.expander("🔍 查看无法成套的多余部件", expanded=False):
                        st.dataframe(pd.DataFrame(excess_parts_data), width="stretch", hide_index=True)
            else:
                st.info("该产品暂无款式信息")
                
        st.divider()

        render_inventory_movement_panel(db, service, selected_product_id, p_name, colors, wh_options)

        st.subheader("📜 变动历史记录")
        logs = service.get_recent_logs(p_name)
        if logs:
            log_data = []
            wh_map_inv = {w.id: w.name for w in warehouses}
            for l in logs:
                desc = l.note or ""
                part_display = l.part_name if l.part_name else "[成套]"
                wh_display = wh_map_inv.get(l.warehouse_id, "未分配仓库")
                
                log_data.append({
                    "_id": l.id, "日期": l.date, "产品": l.product_name, "款式": l.variant, 
                    "部件/模式": part_display, "相关仓库": wh_display,
                    "数量": l.change_amount, "类型": l.reason, "详情": desc
                })
            
            df_logs = pd.DataFrame(log_data)
            st.data_editor(
                df_logs, key="log_editor", width="stretch", hide_index=True,
                column_config={"_id": None, "日期": st.column_config.DateColumn(required=True), "产品": st.column_config.TextColumn(disabled=True), "款式": st.column_config.TextColumn(disabled=True), "部件/模式": st.column_config.TextColumn(disabled=True), "相关仓库": st.column_config.TextColumn(disabled=True), "数量": st.column_config.NumberColumn(disabled=True), "类型": st.column_config.TextColumn(disabled=True), "详情": st.column_config.TextColumn(label="详情 (可编辑)", required=False)}
            )
            
            if st.session_state.get("log_editor") and st.session_state["log_editor"].get("edited_rows"):
                changes = {}
                for idx_str, diff in st.session_state["log_editor"]["edited_rows"].items():
                    changes[int(df_logs.iloc[int(idx_str)]["_id"])] = diff
                if service.update_logs_batch(changes):
                    st.toast("日志已更新", icon="💾")
                    st.rerun()

            with st.popover("🗑️ 删除记录 (级联回滚)", width="stretch"):
                st.warning("⚠️ 删除操作将自动回滚：库存与资产价值。库存移动记录删除时需将进出两笔记录分别进行删除。")
                del_opts = {f"[ID:{l.id}] {l.date} | {l.variant} ({l.part_name if l.part_name else '[成套]'}) | {l.reason} {l.change_amount}": l.id for l in logs}
                selected_del = st.selectbox("选择要删除的记录", list(del_opts.keys()))
                if st.button("🔴 确认删除并回滚"):
                    try:
                        full_msg = service.delete_log_cascade(del_opts[selected_del])
                        st.success(full_msg)
                        st.rerun()
                    except Exception as e:
                        service.db.rollback()
                        st.error(f"删除失败: {e}")
        else:
            st.info("暂无记录")

    # ================= 标签页 2：仓库管理 =================
    with tab2:
        st.subheader("🏢 仓库管理")
        
        with st.expander("➕ 添加新仓库", expanded=False):
            w_name = st.text_input("仓库名称", placeholder="如：北京1号仓")
            w_remark = st.text_input("仓库备注", placeholder="地址或联系人等")
            if st.button("💾 保存仓库", type="primary"):
                if not w_name: st.error("名称不能为空")
                else:
                    try:
                        service.add_warehouse(w_name, w_remark)
                        st.toast("添加成功", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        
        st.divider()
        st.markdown("#### 📦 各仓库明细")
        
        wh_details = service.get_warehouse_inventory_details()
        if not wh_details:
            st.info("尚未创建任何仓库")
            
        # ✨ 获取产品和需求映射，用于计算该仓库的实物能凑出多少整套
        products = service.get_all_products()
        req_map = {} 
        for prod in products:
            req_map[prod.name] = {}
            for c in prod.colors:
                req_map[prod.name][c.color_name] = {p.part_name: p.quantity for p in c.parts} if c.parts else {"整套": 1}
        
        for w_id, w_data in wh_details.items():
            if w_id is None and not w_data["stock"]: continue 
            
            with st.expander(f"🏬 {w_data['name']}", expanded=True):
                if not w_data["stock"]:
                    st.caption("该仓库当前为空。")
                    if w_id is not None:
                        if st.button("🗑️ 删除该仓库", key=f"del_wh_{w_id}"):
                            try:
                                service.delete_warehouse(w_id)
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                else:
                    has_any_stock = False
                    
                    # ✨ 核心改动：按商品独立分类和建表
                    for prod_n, v_dict in w_data["stock"].items():
                        prod_table = []
                        for var_n, pt_dict in v_dict.items():
                            
                            # 获取该款式的部件配比要求
                            reqs = req_map.get(prod_n, {}).get(var_n, {"整套": 1})
                            
                            # ✨ 根据仓库里的物理散件数量和配比，木桶原理计算能凑出的整套数
                            possible_sets = 0
                            if reqs:
                                possible_sets = min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items())
                                
                            for pt_n, qty in pt_dict.items():
                                if qty != 0:
                                    prod_table.append({
                                        "款式": var_n, 
                                        "部件": pt_n, 
                                        "物理数量": qty,
                                        "可组装整套数": possible_sets
                                    })
                        
                        # 渲染该商品专属的子表格
                        if prod_table:
                            has_any_stock = True
                            st.markdown(f"##### 🛍️ {prod_n}")
                            st.dataframe(pd.DataFrame(prod_table), width="stretch", hide_index=True)
                            
                    if not has_any_stock:
                        st.caption("库存已全部清空。")
                        
                    if w_id is not None:
                        if st.button("🗑️ 删除该仓库", key=f"del_wh_{w_id}_btn"):
                            try:
                                service.delete_warehouse(w_id)
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))