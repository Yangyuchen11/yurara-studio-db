import streamlit as st
import pandas as pd
from datetime import date
from models import Product, InventoryLog, ProductColor

def show_inventory_page(db):
    st.header("📦 库存出入库记录")
    st.caption("注：此处用于记录发货、赠送等后续变动，并会自动更新对应颜色的当前库存。")
    
    with st.expander("📝 录入变动", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        
        # 1. 获取所有产品列表
        products = db.query(Product).all()
        product_names = [p.name for p in products]
        
        # 第一列：选择产品
        p_name = c1.selectbox("产品", product_names or ["暂无产品"])
        
        # 2. 根据选中的产品，获取对应的颜色列表
        color_options = []
        selected_product_id = None
        
        if products and p_name != "暂无产品":
            # 找到当前选中的产品对象
            selected_product = next((p for p in products if p.name == p_name), None)
            if selected_product:
                selected_product_id = selected_product.id
                # 查询该产品下的颜色
                colors = db.query(ProductColor).filter(ProductColor.product_id == selected_product.id).all()
                color_options = [c.color_name for c in colors]

        # 第二列：选择颜色 (从 text_input 改为 selectbox)
        # 如果没有配置颜色，给一个默认选项
        if not color_options:
            color_options = ["通用/无颜色"]
            
        p_var = c2.selectbox("款式/颜色", color_options)
        
        # 第三列：数量
        p_change = c3.number_input("数量 (出库填负数)", step=1, value=0)
        
        # 第四列：原因
        p_reason = c4.text_input("原因", "淘宝订单发货")
        
        # --- 提交逻辑 ---
        if st.button("提交变动"):
            if p_name == "暂无产品":
                st.error("请先创建产品！")
            else:
                # A. 记录日志 (InventoryLog)
                log = InventoryLog(
                    product_name=p_name, 
                    variant=p_var, 
                    change_amount=p_change, 
                    reason=p_reason, 
                    date=date.today()
                )
                db.add(log)
                
                # B. 实时更新库存 (核心逻辑)
                # 1. 更新子表 (ProductColor) 的库存
                if selected_product_id:
                    # 找到对应的颜色记录
                    color_record = db.query(ProductColor).filter(
                        ProductColor.product_id == selected_product_id,
                        ProductColor.color_name == p_var
                    ).first()
                    
                    if color_record:
                        color_record.quantity += p_change
                    else:
                        # 如果是"通用/无颜色"或者找不到记录(极少情况)，可能需要手动处理或忽略
                        pass

                    # 2. 更新主表 (Product) 的总库存
                    product_record = db.query(Product).filter(Product.id == selected_product_id).first()
                    if product_record:
                        product_record.total_quantity += p_change

                db.commit()
                st.success(f"已记录！《{p_name} - {p_var}》库存变动: {p_change}")
                st.rerun()
            
    # 显示日志表格
    logs = db.query(InventoryLog).order_by(InventoryLog.id.desc()).all()
    if logs:
        # 优化表格显示，加入款式列
        st.dataframe(
            pd.DataFrame([
                {"日期": l.date, "产品": l.product_name, "款式/颜色": l.variant, "变动": l.change_amount, "原因": l.reason} 
                for l in logs
            ]),
            use_container_width=True
        )