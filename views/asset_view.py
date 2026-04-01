# views/asset_view.py
import streamlit as st
import pandas as pd
from services.asset_service import AssetService

def show_asset_page(db, exchange_rate):
    st.header("🏢 固定资产管理")
    
    # === 1. 获取数据 ===
    assets = AssetService.get_all_assets(db)
    
    # === 2. 顶部统计卡片 ===
    if assets:
        # 调用 Service 进行计算
        val_total, val_remain, val_jpy_raw = AssetService.calculate_asset_totals(assets, exchange_rate)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("资产采购历史总值 (折合)", f"¥ {val_total:,.2f}")
        c2.metric("当前剩余价值 (折合)", f"¥ {val_remain:,.2f}", help="所有资产按当前汇率折算为 CNY 的总和")
        c3.metric("其中日元资产原值", f"¥ {val_jpy_raw:,.0f}", help="仅统计 JPY 资产的日元原值部分")
        
        st.divider()
        st.markdown("#### 📋 资产清单")

        # === 3. 构建表格数据 (View 层负责 UI 数据格式化) ===
        data_list = []
        for a in assets:
            curr = getattr(a, "currency", "CNY")
            remain_origin = a.unit_price * a.remaining_qty
            total_origin = a.unit_price * a.quantity
            
            # 显示逻辑：CNY 和 JPY 分列显示
            show_cny = remain_origin if curr != "JPY" else None
            show_jpy = remain_origin if curr == "JPY" else None

            data_list.append({
                "ID": a.id,
                "项目": a.name,
                "币种": curr,
                "单价 (原币)": a.unit_price,
                "初始数量": a.quantity,
                "剩余数量": a.remaining_qty,
                "总价 (原币)": total_origin,
                "剩余价值 (CNY)": show_cny,
                "剩余价值 (JPY)": show_jpy,
                "店名": a.shop_name,
                "相关链接": getattr(a, 'url', '') or "",
                "备注": a.remarks
            })
            
        df = pd.DataFrame(data_list)
        
        # === 4. 渲染可编辑表格 ===
        edited_df = st.data_editor(
            df,
            key="asset_editor",
            width="stretch",
            hide_index=True,
            disabled=["ID", "项目", "币种", "单价 (原币)", "初始数量", "剩余数量", "总价 (原币)", "剩余价值 (CNY)", "剩余价值 (JPY)"],
            column_config={
                "ID": None,
                "币种": st.column_config.TextColumn(width="small"),
                "单价 (原币)": st.column_config.NumberColumn(format="%.2f"),
                "总价 (原币)": st.column_config.NumberColumn(format="%.2f"),
                "剩余价值 (CNY)": st.column_config.NumberColumn(format="¥ %.2f", help="按汇率折算"),
                "剩余价值 (JPY)": st.column_config.NumberColumn(format="¥ %.0f", help="日元资产原值"),
                "店名": st.column_config.TextColumn("店名/来源", required=True),
                "相关链接": st.column_config.LinkColumn("相关链接", display_text="🔗 URL"),
                "备注": st.column_config.TextColumn("备注"),
            },
            column_order=["项目", "币种", "单价 (原币)", "初始数量", "剩余数量", "总价 (原币)", "剩余价值 (CNY)", "剩余价值 (JPY)", "店名", "相关链接", "备注"]
        )

        # === 5. 处理表格修改 (调用 Service) ===
        if st.session_state.get("asset_editor") and st.session_state["asset_editor"].get("edited_rows"):
            changes = st.session_state["asset_editor"]["edited_rows"]
            any_success = False
            
            for index, diff in changes.items():
                original_row = df.iloc[int(index)]
                asset_id = int(original_row["ID"])
                
                # 准备更新数据映射 (UI列名 -> 数据库字段名)
                updates = {}
                if "店名" in diff: updates["shop_name"] = diff["店名"]
                if "相关链接" in diff: updates["url"] = diff["相关链接"]
                if "备注" in diff: updates["remarks"] = diff["备注"]
                
                if updates:
                    try:
                        if AssetService.update_asset_info(db, asset_id, updates):
                            any_success = True
                    except Exception as e:
                        st.error(f"更新 ID {asset_id} 失败: {e}")
            
            if any_success:
                st.toast("资产信息已更新", icon="💾")
                st.rerun()

        # ================= 6. 资产核销操作区 =================
        st.subheader("📉 资产核销/报废")
        with st.container(border=True):
            # 获取活跃资产 (Service 调用)
            active_assets = AssetService.get_active_assets(db)
            
            if active_assets:
                c_op1, c_op2, c_op3, c_op4 = st.columns([2, 1, 2, 1], vertical_alignment="bottom")
                
                # 构建选择映射
                asset_map = {f"{a.name} (余: {a.remaining_qty})": a for a in active_assets}
                selected_label = c_op1.selectbox("选择要核销的资产", options=list(asset_map.keys()))
                target_asset = asset_map[selected_label]
                
                del_qty = c_op2.number_input(
                    "核销数量", 
                    min_value=1.0, 
                    max_value=float(target_asset.remaining_qty), 
                    step=1.0,
                    value=1.0
                )
                
                del_reason = c_op3.text_input("核销原因", placeholder="如：损坏、丢失、折旧")
                
                # 提交操作
                if c_op4.button("确认核销", type="primary"):
                    if not del_reason:
                        st.error("请填写核销原因")
                    else:
                        try:
                            # 调用 Service 执行写操作
                            name = AssetService.write_off_asset(db, target_asset.id, del_qty, del_reason)
                            st.success(f"已核销 {del_qty} 个 {name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"核销失败: {e}")
            else:
                st.info("当前没有可核销的资产 (剩余数量均为0)")

        # ================= 7. 核销历史记录 =================
        st.subheader("📜 固定资产核销记录")
        logs = AssetService.get_asset_logs(db)
        
        if logs:
            log_data = [{
                "日期": l.date,
                "资产名称": l.asset_name,
                "核销数量": l.decrease_qty,
                "原因": l.reason
            } for l in logs]
            
            st.dataframe(
                pd.DataFrame(log_data),
                width="stretch",
                hide_index=True,
                column_config={
                    "日期": st.column_config.DateColumn(format="YYYY-MM-DD")
                }
            )
        else:
            st.caption("暂无核销记录")

    else:
        st.info("暂无固定资产数据。请在【财务流水账】中录入‘固定资产购入’。")