import streamlit as st
import pandas as pd
from datetime import date
# 引入新定义的 Log 模型
from models import FixedAsset, FixedAssetLog

def show_fixed_asset_page(db):
    st.header("🏢 固定资产明细表")
    
    # 获取所有资产
    assets = db.query(FixedAsset).all()
    
    # ================= 1. 资产列表展示 =================
    if assets:
        data_list = []
        total_val = 0        # 采购总值
        total_remain_val = 0 # 剩余总值
        
        # 用于下拉菜单的选项 (过滤掉剩余数量为0的)
        active_assets = []
        
        for a in assets:
            t_price = a.unit_price * a.quantity         # 总价 (采购时)
            r_val = a.unit_price * a.remaining_qty      # 剩余价值 (当前)
            
            data_list.append({
                "项目": a.name,
                "单价": a.unit_price,
                "初始数量": a.quantity,
                "剩余数量": a.remaining_qty, # 重点展示
                "总价(采购)": t_price,
                "剩余价值": r_val,
                "店名": a.shop_name,
                "备注": a.remarks,
                "_id": a.id # 隐藏字段，用于逻辑处理
            })
            
            total_val += t_price
            total_remain_val += r_val
            
            if a.remaining_qty > 0:
                active_assets.append(a)
            
        df = pd.DataFrame(data_list)
        
        # --- 顶部统计卡片 ---
        c1, c2 = st.columns(2)
        c1.metric("资产采购总值", f"¥ {total_val:,.2f}")
        c2.metric("当前剩余价值 (计入公司资产)", f"¥ {total_remain_val:,.2f}", help="单价 x 剩余数量")
        
        # --- 主表格 ---
        st.dataframe(
            df, 
            column_config={
                "单价": st.column_config.NumberColumn(format="¥ %.2f"),
                "总价(采购)": st.column_config.NumberColumn(format="¥ %.2f"),
                "剩余价值": st.column_config.NumberColumn(format="¥ %.2f"),
                # 隐藏内部ID列
                "_id": None 
            },
            column_order=["项目", "单价", "初始数量", "剩余数量", "剩余价值", "总价(采购)", "店名", "备注"],
            use_container_width=True,
            hide_index=True
        )
        
        st.divider()

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