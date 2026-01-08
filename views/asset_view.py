import streamlit as st
import pandas as pd
from datetime import date
from models import FixedAsset, FixedAssetLog

def show_fixed_asset_page(db, exchange_rate):
    st.header("🏢 固定资产明细表")
    
    # 获取所有资产
    assets = db.query(FixedAsset).all()
    
    # ================= 1. 资产列表展示 (可编辑) =================
    if assets:
        data_list = []
        total_val_cny = 0        # 采购总值 (CNY)
        total_remain_val_cny = 0 # 剩余总值 (CNY)
        
        active_assets = []
        
        for a in assets:
            # 1. 确定汇率
            rate = exchange_rate if a.currency == "JPY" else 1.0
            
            # 2. 基础计算
            t_price_origin = a.unit_price * a.quantity    # 采购总价 (原币)
            
            # 【核心修改】剩余价值统一算成 CNY
            r_val_cny = (a.unit_price * a.remaining_qty) * rate
            
            # 统计总池 (用于顶部卡片)
            total_val_cny += t_price_origin * rate
            total_remain_val_cny += r_val_cny

            data_list.append({
                "ID": a.id,
                "项目": a.name,
                "币种": a.currency,
                "单价 (原币)": a.unit_price,       # 单价保持原币，方便核对
                "初始数量": a.quantity,
                "剩余数量": a.remaining_qty,
                "总价 (原币)": t_price_origin,     # 采购历史总价保持原币
                "剩余价值 (CNY)": r_val_cny,       # 【修改】只显示折合后的 CNY
                "店名": a.shop_name,
                "备注": a.remarks
            })
            
            if a.remaining_qty > 0:
                active_assets.append(a)
            
        # --- 顶部统计卡片 ---
        c1, c2 = st.columns(2)
        c1.metric("资产采购总值 (折合CNY)", f"¥ {total_val_cny:,.2f}")
        c2.metric("当前剩余价值 (折合CNY)", f"¥ {total_remain_val_cny:,.2f}", help="计入公司资产的总额")
        
        st.divider()
        st.markdown("#### 📋 资产清单 (剩余价值已折算为CNY)")

        # --- 构造 DataFrame ---
        df = pd.DataFrame(data_list)
        
        # --- 使用 DataEditor ---
        edited_df = st.data_editor(
            df,
            key="asset_editor",
            use_container_width=True,
            hide_index=True,
            # 锁定不需要修改的列
            disabled=["ID", "项目", "币种", "单价 (原币)", "初始数量", "剩余数量", "总价 (原币)", "剩余价值 (CNY)"],
            column_config={
                "ID": None,
                "币种": st.column_config.TextColumn(width="small"),
                "单价 (原币)": st.column_config.NumberColumn(format="%.2f"),
                "总价 (原币)": st.column_config.NumberColumn(format="%.2f"),
                "剩余价值 (CNY)": st.column_config.NumberColumn(format="¥ %.2f"),
                "店名": st.column_config.TextColumn("店名/来源", required=True),
                "备注": st.column_config.TextColumn("备注"),
            },
            column_order=["项目", "币种", "单价 (原币)", "初始数量", "剩余数量", "总价 (原币)", "剩余价值 (CNY)", "店名", "备注"]
        )

        # --- 捕获修改并更新数据库 ---
        if st.session_state.get("asset_editor") and st.session_state["asset_editor"].get("edited_rows"):
            changes = st.session_state["asset_editor"]["edited_rows"]
            has_change = False
            
            for index, diff in changes.items():
                original_row = df.iloc[int(index)]
                asset_id = int(original_row["ID"])
                asset_obj = db.query(FixedAsset).filter(FixedAsset.id == asset_id).first()
                
                if asset_obj:
                    if "店名" in diff:
                        asset_obj.shop_name = diff["店名"]
                        has_change = True
                    if "备注" in diff:
                        asset_obj.remarks = diff["备注"]
                        has_change = True
            
            if has_change:
                try:
                    db.commit()
                    st.toast("资产信息已更新", icon="💾")
                    st.rerun()
                except Exception as e:
                    st.error(f"更新失败: {e}")

        # ================= 2. 资产核销操作区 =================
        st.subheader("📉 资产核销/报废")
        with st.container(border=True):
            if active_assets:
                c_op1, c_op2, c_op3, c_op4 = st.columns([2, 1, 2, 1])
                
                # 1. 选择资产
                # 创建一个字典映射: "名称 (剩余: 5)" -> 资产对象
                asset_map = {f"{a.name} (余: {a.remaining_qty})": a for a in active_assets}
                selected_label = c_op1.selectbox("选择要核销的资产", options=list(asset_map.keys()))
                target_asset = asset_map[selected_label]
                
                # 2. 选择数量
                # 最大值不能超过剩余数量
                del_qty = c_op2.number_input(
                    "核销数量", 
                    min_value=1, 
                    max_value=target_asset.remaining_qty, 
                    step=1,
                    value=1
                )
                
                # 3. 原因
                del_reason = c_op3.text_input("核销原因", placeholder="如：损坏、丢失、折旧")
                
                # 4. 提交按钮
                if c_op4.button("确认核销", type="primary"):
                    if not del_reason:
                        st.error("请填写核销原因")
                    else:
                        # A. 减少库存
                        target_asset.remaining_qty -= del_qty
                        
                        # B. 记录日志
                        new_log = FixedAssetLog(
                            asset_name=target_asset.name,
                            decrease_qty=del_qty,
                            reason=del_reason,
                            date=date.today()
                        )
                        db.add(new_log)
                        db.commit()
                        
                        st.success(f"已核销 {del_qty} 个 {target_asset.name}")
                        st.rerun()
            else:
                st.info("当前没有可核销的资产 (剩余数量均为0)")

        # ================= 3. 核销历史记录 =================
        st.subheader("📜 固定资产核销记录")
        logs = db.query(FixedAssetLog).order_by(FixedAssetLog.id.desc()).all()
        
        if logs:
            log_data = [{
                "日期": l.date,
                "资产名称": l.asset_name,
                "核销数量": l.decrease_qty,
                "原因": l.reason
            } for l in logs]
            
            st.dataframe(
                pd.DataFrame(log_data),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "日期": st.column_config.DateColumn(format="YYYY-MM-DD")
                }
            )
        else:
            st.caption("暂无核销记录")

    else:
        st.info("暂无固定资产数据。请在【财务流水账】中录入‘固定资产购入’。")