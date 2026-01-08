import streamlit as st
import pandas as pd
from datetime import date
from models import ConsumableItem

def show_consumable_page(db):
    st.header("📦 耗材资产管理 (消耗品)")
    
    # === 1. 库存操作区 (消耗/补货) ===
    st.markdown("### ⚡ 快速库存操作")
    with st.container(border=True):
        col_op1, col_op2, col_op3, col_op4 = st.columns([2, 1.5, 1.5, 1])
        
        all_items = db.query(ConsumableItem).filter(ConsumableItem.remaining_qty > 0).all()
        item_names = [i.name for i in all_items]
        
        selected_name = col_op1.selectbox("选择耗材", item_names or ["暂无库存"])
        op_type = col_op2.radio("操作类型", ["消耗/出库 (-)", "补货/入库 (+)"], horizontal=True)
        op_qty = col_op3.number_input("变动数量", min_value=1, step=1, value=1)
        
        if col_op4.button("提交变动", type="primary"):
            if selected_name and selected_name != "暂无库存":
                item = db.query(ConsumableItem).filter(ConsumableItem.name == selected_name).first()
                if item:
                    if "消耗" in op_type:
                        if item.remaining_qty >= op_qty:
                            item.remaining_qty -= op_qty
                            st.toast(f"已消耗 {op_qty} 个 {item.name}", icon="📉")
                        else:
                            st.error("库存不足！")
                            st.stop()
                    else:
                        item.remaining_qty += op_qty
                        st.toast(f"已补货 {op_qty} 个 {item.name}", icon="📈")
                    
                    db.commit()
                    st.rerun()

    st.divider()

    # === 2. 耗材列表展示 ===
    items = db.query(ConsumableItem).all()
    
    if items:
        data_list = []
        total_remain_val = 0
        
        for i in items:
            remain_val = i.unit_price * i.remaining_qty
            # 计算采购时的总价 (初始数量 * 单价)
            purchase_total = i.unit_price * i.initial_quantity
            
            data_list.append({
                # 去掉ID列
                "项目": i.name,
                "分类": i.category,
                "单价": i.unit_price,
                "总价": purchase_total, # 新增：采购总价
                "初始数量": i.initial_quantity,
                "剩余数量": i.remaining_qty,
                "剩余价值": remain_val,
                "店铺": i.shop_name,
                "备注": i.remarks
            })
            total_remain_val += remain_val
            
        df = pd.DataFrame(data_list)
        
        # 统计指标
        c1, c2 = st.columns(2)
        c1.metric("耗材种类数", f"{len(items)} 种")
        c2.metric("当前库存总值 (计入公司资产)", f"¥ {total_remain_val:,.2f}")
        
        # 展示表格
        st.dataframe(
            df,
            column_config={
                "单价": st.column_config.NumberColumn(format="¥ %.4f"), 
                "总价": st.column_config.NumberColumn(format="¥ %.2f"), # 显示总价格式
                "剩余价值": st.column_config.NumberColumn(format="¥ %.2f"),
                "剩余数量": st.column_config.ProgressColumn(
                    format="%d",
                    min_value=0,
                    max_value=max(df["初始数量"]) if not df.empty else 100,
                ),
            },
            # 调整顺序：项目 -> 分类 -> 单价 -> 总价 ...
            column_order=["项目", "分类", "单价", "总价", "初始数量", "剩余数量", "剩余价值", "店铺", "备注"],
            use_container_width=True,
            hide_index=True
        )
        
        # 删除功能
        with st.popover("🗑️ 删除耗材项"):
            del_name = st.selectbox("删除哪个项目?", df["项目"].tolist())
            if st.button("确认删除耗材"):
                # 通过名称查找删除 (只要名称唯一)
                db.query(ConsumableItem).filter(ConsumableItem.name == del_name).delete()
                db.commit()
                st.rerun()
    else:
        st.info("暂无耗材数据。请在【财务流水账】中录入‘耗材购入’支出。")