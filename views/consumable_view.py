import streamlit as st
import pandas as pd
from datetime import date
from models import ConsumableItem, ConsumableLog

def show_consumable_page(db, exchange_rate):
    st.header("📦 耗材资产管理 (消耗品)")
    
    # === 1. 库存操作区 (消耗/补货) ===
    st.markdown("### ⚡ 快速库存操作")
    with st.container(border=True):
        # 调整列比例，增加备注栏
        col_op1, col_op2, col_op3, col_op4, col_op5 = st.columns([1.5, 1.2, 1, 1.5, 0.8])
        
        all_items = db.query(ConsumableItem).filter(ConsumableItem.remaining_qty > 0).all()
        item_names = [i.name for i in all_items]
        
        selected_name = col_op1.selectbox("选择耗材", item_names or ["暂无库存"])
        op_type = col_op2.radio("操作类型", ["消耗/出库 (-)", "补货/入库 (+)"], horizontal=True)
        op_qty = col_op3.number_input("数量", min_value=1, step=1, value=1)
        
        # 【修改点 1】新增备注输入框
        op_remark = col_op4.text_input("操作备注", placeholder="如：打包发货使用")
        
        if col_op5.button("提交", type="primary", use_container_width=True):
            if selected_name and selected_name != "暂无库存":
                item = db.query(ConsumableItem).filter(ConsumableItem.name == selected_name).first()
                if item:
                    # 确定正负号
                    sign = -1 if "消耗" in op_type else 1
                    qty_delta = op_qty * sign
                    
                    # 校验库存
                    if qty_delta < 0 and item.remaining_qty < op_qty:
                        st.error("库存不足！")
                        st.stop()
                    
                    # 1. 更新库存
                    item.remaining_qty += qty_delta
                    
                    # 2. 【修改点 2】记录日志
                    # 计算价值折算 CNY
                    curr = getattr(item, "currency", "CNY")
                    rate = exchange_rate if curr == "JPY" else 1.0
                    
                    # 变动价值 = 变动数量 * 单价 * 汇率
                    val_change_cny = qty_delta * item.unit_price * rate
                    
                    new_log = ConsumableLog(
                        item_name=item.name,
                        change_qty=qty_delta,
                        value_cny=val_change_cny,
                        note=op_remark,
                        date=date.today()
                    )
                    db.add(new_log)
                    
                    db.commit()
                    
                    msg_icon = "📉" if qty_delta < 0 else "📈"
                    st.toast(f"已更新：{item.name} {qty_delta} (折合 ¥{val_change_cny:.2f})", icon=msg_icon)
                    st.rerun()

    st.divider()

    # === 2. 耗材列表展示 (可编辑) ===
    items = db.query(ConsumableItem).all()
    
    if items:
        data_list = []
        total_remain_val_cny = 0 
        
        for i in items:
            curr = getattr(i, "currency", "CNY") 
            rate = exchange_rate if curr == "JPY" else 1.0
            
            # 基础数据 (原币)
            purchase_total_origin = i.unit_price * i.initial_quantity
            
            # 【核心修改】剩余价值统一算成 CNY
            remain_val_cny = (i.unit_price * i.remaining_qty) * rate
            
            total_remain_val_cny += remain_val_cny
            
            data_list.append({
                "ID": i.id,
                "项目": i.name,
                "分类": i.category,
                "币种": curr,
                "单价 (原币)": i.unit_price,
                "总价 (原币)": purchase_total_origin,
                "初始数量": i.initial_quantity,
                "剩余数量": i.remaining_qty,
                "剩余价值 (CNY)": remain_val_cny, # 【修改】只显示 CNY
                "店铺": i.shop_name,
                "备注": i.remarks
            })
            
        df = pd.DataFrame(data_list)
        
        # 统计指标
        c1, c2 = st.columns(2)
        c1.metric("耗材种类数", f"{len(items)} 种")
        c2.metric("当前库存总值 (折合CNY)", f"¥ {total_remain_val_cny:,.2f}")
        
        # --- 使用 DataEditor ---
        edited_df = st.data_editor(
            df,
            key="consumable_editor",
            use_container_width=True,
            hide_index=True,
            # 锁定列
            disabled=["ID", "项目", "分类", "币种", "单价 (原币)", "总价 (原币)", "初始数量", "剩余数量", "剩余价值 (CNY)"],
            column_config={
                "ID": None,
                "币种": st.column_config.TextColumn(width="small"),
                "单价 (原币)": st.column_config.NumberColumn(format="%.4f"), 
                "总价 (原币)": st.column_config.NumberColumn(format="%.2f"),
                # 【修改】显示格式为 CNY
                "剩余价值 (CNY)": st.column_config.NumberColumn(format="¥ %.2f"),
                "剩余数量": st.column_config.ProgressColumn(
                    format="%d", min_value=0, max_value=max(df["初始数量"]) if not df.empty else 100
                ),
                "店铺": st.column_config.TextColumn("店铺/供应商", required=True),
                "备注": st.column_config.TextColumn("备注"),
            },
            column_order=["项目", "分类", "币种", "单价 (原币)", "总价 (原币)", "初始数量", "剩余数量", "剩余价值 (CNY)", "店铺", "备注"]
        )

        # --- 捕获修改并更新 ---
        if st.session_state.get("consumable_editor") and st.session_state["consumable_editor"].get("edited_rows"):
            changes = st.session_state["consumable_editor"]["edited_rows"]
            has_change = False
            
            for index, diff in changes.items():
                original_row = df.iloc[int(index)]
                item_id = int(original_row["ID"])
                
                item_obj = db.query(ConsumableItem).filter(ConsumableItem.id == item_id).first()
                if item_obj:
                    if "店铺" in diff:
                        item_obj.shop_name = diff["店铺"]
                        has_change = True
                    if "备注" in diff:
                        item_obj.remarks = diff["备注"]
                        has_change = True
            
            if has_change:
                try:
                    db.commit()
                    st.toast("耗材信息已更新", icon="💾")
                    st.rerun()
                except Exception as e:
                    st.error(f"更新失败: {e}")
        
        # 删除功能
        with st.popover("🗑️ 删除耗材项"):
            del_name = st.selectbox("删除哪个项目?", df["项目"].tolist())
            if st.button("确认删除耗材"):
                db.query(ConsumableItem).filter(ConsumableItem.name == del_name).delete()
                db.commit()
                st.rerun()
    else:
        st.info("暂无耗材数据。请在【财务流水账】中录入‘耗材购入’支出。")

    # === 3. 【修改点 3】新增：耗材消耗/补充记录表 ===
    st.divider()
    st.subheader("📜 耗材消耗/补充记录")
    
    logs = db.query(ConsumableLog).order_by(ConsumableLog.id.desc()).all()
    
    if logs:
        log_data = []
        for l in logs:
            log_data.append({
                "日期": l.date,
                "耗材名称": l.item_name,
                "变动数量": l.change_qty,
                "价值折算 (CNY)": l.value_cny,
                "备注": l.note
            })
        
        st.dataframe(
            pd.DataFrame(log_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "日期": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "价值折算 (CNY)": st.column_config.NumberColumn(format="¥ %.2f"),
                "变动数量": st.column_config.NumberColumn(format="%d")
            }
        )
    else:
        st.caption("暂无操作记录")