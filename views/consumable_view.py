import streamlit as st
import pandas as pd
from datetime import date
from services.consumable_service import ConsumableService
from cache_manager import sync_all_caches
from constants import PRODUCT_COST_CATEGORIES

# 兼容性处理：适配不同版本的 Streamlit
if hasattr(st, "fragment"):
    fragment_decorator = st.fragment
else:
    fragment_decorator = st.experimental_fragment

# ================= 🚀 核心性能优化：将表单区封装为局部渲染组件 =================
@fragment_decorator
def render_operation_panel(db, exchange_rate, service):
    st.markdown("#### ⚡ 快速库存操作")
    
    # 获取活跃库存项用于下拉
    active_items = service.get_active_consumables()
    item_names = [i.name for i in active_items]
    
    # --- 第一行：日期 | 选择资产 | 操作类型 ---
    c_date, c_item, c_type = st.columns([1, 1.5, 1.2])
    op_date = c_date.date_input("📅 日期", value=date.today())
    selected_name = c_item.selectbox("📦 选择项目", item_names or ["暂无库存"])
    op_type = c_type.radio("⚙️ 操作类型", ["出库 (消耗/销售) -", "入库 (补货) +"], horizontal=True)
    
    # 数量输入
    c_qty, c_space = st.columns([1, 3.2])
    op_qty = c_qty.number_input("🔢 操作数量", min_value=0.01, step=1.0, value=1.0, format="%.2f")
    
    # 状态变量
    target_product_id = None
    target_cost_category = "包装费"
    is_link_product = False
    is_sale_mode = False
    
    # 销售信息
    sale_content = ""
    sale_source = ""
    sale_amount = 0.0
    sale_currency = "CNY"
    sale_remark = ""
    # 消耗/补货备注
    op_remark = "" 
    
    # === 核心逻辑分支 ===
    if "出库" in op_type:
        st.markdown("---")
        out_mode = st.radio("📤 出库目的", ["🏢 内部消耗 (计入成本)", "💰 对外销售 (计入收入)"], horizontal=True)
        
        if "对外销售" in out_mode:
            is_sale_mode = True
            st.caption("📝 请填写财务信息 (将自动生成【销售收入】流水并存入流动资金)")
            
            r1_c1, r1_c2, r1_c3, r1_c4 = st.columns([2, 1.5, 1, 1])
            default_content = f"售出 {selected_name}" if selected_name else ""
            sale_content = r1_c1.text_input("收入内容", value=default_content, placeholder="如：闲鱼出物")
            sale_source = r1_c2.text_input("收入来源", placeholder="如：闲鱼/线下")
            sale_amount = r1_c3.number_input("销售总额", min_value=0.0, step=10.0, format="%.2f")
            sale_currency = r1_c4.selectbox("币种", ["CNY", "JPY"])
            sale_remark = st.text_input("备注", placeholder="选填，将记录在流水备注中")
            
        else:
            # 内部消耗
            is_sale_mode = False
            lc1, lc2, lc3 = st.columns([0.8, 1.6, 1.6])
            is_link_product = lc1.checkbox("🔗 计入商品成本", help="勾选后，消耗金额将分摊到指定商品的成本中")
            op_remark = st.text_input("消耗备注", placeholder="如：打包使用") 
            
            if is_link_product:
                products = service.get_all_products()
                prod_opts = {p.id: p.name for p in products}
                if prod_opts:
                    target_product_id = lc2.selectbox("归属商品", options=list(prod_opts.keys()), format_func=lambda x: prod_opts[x], label_visibility="collapsed")
                    target_cost_category = lc3.selectbox("成本分类", options=PRODUCT_COST_CATEGORIES, index=3, label_visibility="collapsed")
    
    else:
        # 入库
        op_remark = st.text_input("补货备注", placeholder="如：淘宝补货")

    # --- 提交按钮 ---
    st.write("") 
    if st.button("🚀 提交更新", type="primary", width="stretch"):
        if selected_name and selected_name != "暂无库存":
            try:
                # 确定变动方向
                sign = -1 if "出库" in op_type else 1
                qty_delta = op_qty * sign
                
                # 准备参数
                mode = "normal"
                s_info = None
                c_info = None
                final_remark = op_remark

                if "出库" in op_type:
                    if is_sale_mode:
                        mode = "sale"
                        if sale_amount <= 0:
                            st.warning("⚠️ 销售金额为0，仅扣减库存，未生成流水")
                        
                        if not sale_content:
                            st.error("请输入收入内容")
                            st.stop()
                            
                        s_info = {
                            "content": sale_content,
                            "source": sale_source,
                            "amount": sale_amount,
                            "currency": sale_currency,
                            "remark": sale_remark
                        }
                    elif is_link_product and target_product_id:
                        mode = "cost"
                        c_info = {
                            "product_id": target_product_id,
                            "category": target_cost_category,
                            "remark": op_remark
                        }
                
                # 调用 Service
                name, delta, link_msg = service.process_inventory_change(
                    item_name=selected_name,
                    date_obj=op_date,
                    delta_qty=qty_delta,
                    exchange_rate=exchange_rate,
                    mode=mode,
                    sale_info=s_info,
                    cost_info=c_info,
                    base_remark=final_remark
                )
                
                msg_icon = "💰" if is_sale_mode else ("📉" if qty_delta < 0 else "📈")
                st.toast(f"更新成功：{name} {delta}{link_msg}", icon=msg_icon)
                sync_all_caches()
                st.rerun() 
                
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"操作失败: {e}")

# ================= 主页面入口 =================
def show_other_asset_page(db, exchange_rate):
    st.header("📦 其他资产管理")
    
    service = ConsumableService(db)

    # === 1. 库存操作区 (局部渲染) ===
    with st.container(border=True):
        render_operation_panel(db, exchange_rate, service)

    st.divider()

    # === 2. 资产列表展示 (保持原逻辑不变) ===
    items = service.get_all_consumables()
    
    if items:
        data_list = []
        total_remain_val_cny = 0.0
        total_remain_val_jpy = 0.0

        for i in items:
            curr = getattr(i, "currency", "CNY") 
            qty = i.remaining_qty
            unit_price = i.unit_price
            val_origin = unit_price * qty
            
            row_cny_display = None
            row_jpy_display = None
            
            if curr == "JPY":
                row_jpy_display = val_origin
                if qty > 0.001 and row_jpy_display > 0.001:
                    total_remain_val_jpy += val_origin
            else: 
                row_cny_display = val_origin
                if qty > 0.001 and row_cny_display > 0.001:
                    total_remain_val_cny += val_origin
            
            # 过滤显示：仅显示有库存或有价值的项目，或者最近活跃的
            if qty <= 0.001 and val_origin <= 0.001:
                continue

            data_list.append({
                "ID": i.id,
                "项目": i.name,
                "分类": i.category,
                "币种": curr,
                "单价 (原币)": unit_price,
                "剩余数量": qty,
                "剩余价值 (CNY)": row_cny_display,
                "剩余价值 (JPY)": row_jpy_display,
                "店铺": i.shop_name,
                "相关链接": getattr(i, 'url', '') or "",
                "备注": i.remarks if i.remarks else ""
            })
            
        df = pd.DataFrame(data_list)
        
        grand_total_cny = total_remain_val_cny + (total_remain_val_jpy * exchange_rate)
        
        st.markdown(
            f"**当前资产总值:** "
            f"CNY <span style='color:green'>¥ {total_remain_val_cny:,.2f}</span> | "
            f"JPY <span style='color:red'>¥ {total_remain_val_jpy:,.0f}</span>"
            f" &nbsp;&nbsp;➡️&nbsp;&nbsp; **折算CNY总计: ¥ {grand_total_cny:,.2f}**", 
            unsafe_allow_html=True
        )
        
        if not df.empty:
            edited_df = st.data_editor(
                df, key="other_asset_editor", width="stretch", hide_index=True,
                disabled=["ID", "项目", "分类", "剩余价值 (CNY)", "剩余价值 (JPY)"],
                column_config={
                    "ID": None,
                    "币种": st.column_config.SelectboxColumn(options=["CNY", "JPY"], required=True),
                    "单价 (原币)": st.column_config.NumberColumn(format="%.2f", required=True),
                    "剩余价值 (CNY)": st.column_config.NumberColumn(format="¥ %.2f"),
                    "剩余价值 (JPY)": st.column_config.NumberColumn(format="¥ %.0f"),
                    "剩余数量": st.column_config.NumberColumn(format="%.2f"),
                    "相关链接": st.column_config.LinkColumn("相关链接", display_text="🔗 URL")
                }
            )
            
            # 处理修改
            if st.session_state.get("other_asset_editor") and st.session_state["other_asset_editor"].get("edited_rows"):
                changes = {}
                for idx_str, diff in st.session_state["other_asset_editor"]["edited_rows"].items():
                    item_id = int(df.iloc[int(idx_str)]["ID"])
                    changes[item_id] = diff
                
                if service.update_items_batch(changes):
                    st.toast("信息已更新", icon="💾")
                    st.rerun()
        else:
            st.info("当前无有效库存资产。")
    else:
        st.info("暂无其他资产数据。")

    # === 3. 操作记录 (保持原逻辑不变) ===
    st.divider()
    st.subheader("📜 操作记录")
    
    logs = service.get_logs()
    
    if logs:
        log_data = [{
            "_id": l.id,
            "日期": l.date, 
            "名称": l.item_name, 
            "变动": l.change_qty, 
            "详情": l.note
        } for l in logs]
        df_logs = pd.DataFrame(log_data)
        
        # 动态高度
        num_rows = len(df_logs)
        calc_height = min(max((num_rows + 1) * 35, 300), 800)
        
        edited_logs = st.data_editor(
            df_logs, 
            width="stretch", 
            hide_index=True,
            height=int(calc_height),
            key="cons_log_editor",
            column_config={
                "_id": None,
                "日期": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
                "名称": st.column_config.TextColumn(disabled=True),
                "变动": st.column_config.NumberColumn(disabled=True),
                "详情": st.column_config.TextColumn(disabled=True)
            }
        )
        
        # 日期修改
        if st.session_state.get("cons_log_editor") and st.session_state["cons_log_editor"].get("edited_rows"):
            log_changes = {}
            for idx_str, diff in st.session_state["cons_log_editor"]["edited_rows"].items():
                log_id = int(df_logs.iloc[int(idx_str)]["_id"])
                log_changes[log_id] = diff

            if service.update_logs_batch(log_changes):
                st.toast("日期已更新", icon="📅")
                st.rerun()
    else:
        st.caption("暂无操作记录")