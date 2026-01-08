import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy import func
from models import Product, InventoryLog, ProductColor, CompanyBalanceItem, CostItem

# === 辅助函数：获取产品单位成本 ===
def get_unit_cost(db, product_id):
    """
    计算逻辑：该产品【成本表】中记录的实付总价之和 / 【主产品表】记录的总制作数量
    """
    # 1. 计算分子：所有成本项的实付总金额
    total_actual_cost = db.query(func.sum(CostItem.actual_cost))\
        .filter(CostItem.product_id == product_id).scalar() or 0.0
    
    # 2. 计算分母：直接获取产品设定的总制作数量
    # 注意：不能累加 CostItem.quantity，否则多条成本项会导致分母翻倍
    product = db.query(Product).filter(Product.id == product_id).first()
    total_qty = product.total_quantity if product else 0
    
    if total_qty > 0:
        return total_actual_cost / total_qty
    
    # 备选：如果总数量为0 (防止除以0报错)，尝试返回0
    return 0.0

# === 辅助函数：获取首发平台售价 (换算为CNY) ===
def get_selling_price(product, exchange_rate):
    platform = product.target_platform
    price = 0.0
    
    if platform == "微店": price = product.price_weidian
    elif platform == "中国线下": price = product.price_offline_cn
    elif platform == "其他": price = product.price_other
    elif platform == "Booth": price = product.price_booth * exchange_rate
    elif platform == "Instagram": price = getattr(product, 'price_instagram', 0) * exchange_rate
    elif platform == "日本线下": price = product.price_offline_jp * exchange_rate
    elif platform == "其他(JPY)": price = getattr(product, 'price_other_jpy', 0) * exchange_rate
         
    return price

# === 主页面逻辑 ===
def show_inventory_page(db):

    # 获取全局汇率
    exchange_rate_input = st.session_state.get("global_rate_input", 4.8)
    exchange_rate = exchange_rate_input / 100.0

    st.header("📦 库存出入库记录")
    st.caption("记录库存变动并自动联动公司资产价值。")
    
    # 1. 获取所有产品
    products = db.query(Product).all()
    product_names = [p.name for p in products]
    
    with st.container():
        st.subheader("📝 录入变动")
        
        # --- 第一行：选择产品与查看剩余 ---
        c_sel, c_view = st.columns([1, 3])
        p_name = c_sel.selectbox("选择产品", product_names or ["暂无产品"])

        selected_product = None
        selected_product_id = None

        if products and p_name != "暂无产品":
            selected_product = next((p for p in products if p.name == p_name), None)
            selected_product_id = selected_product.id
            
            with c_view:
                if selected_product_id:
                    # 1. 获取该产品的所有规格信息
                    colors = db.query(ProductColor).filter(ProductColor.product_id == selected_product_id).all()
                    
                    # 2. 获取日志并在内存中计算库存
                    all_logs = db.query(InventoryLog).filter(InventoryLog.product_name == p_name).all()
                    
                    real_stock_map = {} 
                    pre_in_map = {}   
                    pre_out_map = {}  

                    for log in all_logs:
                        if log.reason in ["入库", "出库"]:
                            real_stock_map[log.variant] = real_stock_map.get(log.variant, 0) + log.change_amount
                        elif log.reason == "预入库":
                            pre_in_map[log.variant] = pre_in_map.get(log.variant, 0) + log.change_amount
                        elif log.reason == "预出库":
                            pre_out_map[log.variant] = pre_out_map.get(log.variant, 0) + abs(log.change_amount)
                        # "预入库完成" 不计入统计

                    if colors:
                        # 3. 构造对比数据 & 交互式表格
                        total_real_all = sum(real_stock_map.values())
                        total_pre_in_all = sum(pre_in_map.values())
                        total_pre_out_all = sum(pre_out_map.values())
                        
                        # 顶部统计
                        col_m1, col_m2, col_m3 = st.columns(3)
                        col_m1.metric("全款式 实际库存", f"{int(total_real_all)} 件")
                        col_m2.metric("全款式 预入库", f"{int(total_pre_in_all)} 件")
                        col_m3.metric("全款式 预出库", f"{int(total_pre_out_all)} 件")

                        st.divider()
                        st.markdown("#### 🔢 库存明细与操作")

                        # === 自定义表头 (增加生产数量列) ===
                        # 比例: 款式(2) | 生产(1.2) | 实际(1.2) | 预入(1.2) | 预出(1.2) | 状态(1.2) | 操作(2.2)
                        cols_cfg = [2, 1.2, 1.2, 1.2, 1.2, 1.2, 2.2]
                        h1, h2, h3, h4, h5, h6, h7 = st.columns(cols_cfg)
                        h1.markdown("**款式/颜色**")
                        h2.markdown("**生产数量**") # 新增
                        h3.markdown("**实际库存**")
                        h4.markdown("**预入库**")
                        h5.markdown("**预出库**")
                        h6.markdown("**状态**")
                        h7.markdown("**操作**")
                        
                        st.markdown("<hr style='margin: 5px 0; opacity:0.5;'>", unsafe_allow_html=True)

                        # === 遍历每一行 ===
                        for c in colors:
                            plan_qty = c.quantity # 生产数量
                            real_qty = real_stock_map.get(c.color_name, 0)
                            pre_in_qty = pre_in_map.get(c.color_name, 0)
                            pre_out_qty = pre_out_map.get(c.color_name, 0)
                            
                            status = "🔴 缺货" if real_qty <= 0 else "🟢 有货"

                            r1, r2, r3, r4, r5, r6, r7 = st.columns(cols_cfg)
                            
                            r1.write(f"🎨 {c.color_name}")
                            r2.write(f"**{plan_qty}**") # 显示生产数量
                            r3.write(f"{int(real_qty)}")
                            r4.write(f"{int(pre_in_qty)}")
                            r5.write(f"{int(pre_out_qty)}")
                            r6.write(status)
                            
                            # === 操作按钮区域 ===
                            with r7:
                                c_btn1, c_btn2 = st.columns([1, 1])
                                
                                # 按钮 1: 生产完成
                                # 【核心修改】：增加 and real_qty == 0 的判断
                                # 只有当“预入库”和“实际库存”都为0时，才代表完全未开始/未入库，才显示生产完成
                                if pre_in_qty == 0 and real_qty == 0 and plan_qty > 0:
                                    if c_btn1.button("🏭 生产完成", key=f"btn_prod_done_{c.id}", help="点击后增加预入库，并从在制资产中扣除"):
                                        # ... (内部逻辑保持不变)
                                        # 1. 登记日志：预入库
                                        log_in = InventoryLog(
                                            product_name=p_name, variant=c.color_name,
                                            change_amount=plan_qty, reason="预入库",
                                            note="生产完成", date=date.today()
                                        )
                                        db.add(log_in)

                                        # 2. 资产处理
                                        unit_cost = get_unit_cost(db, selected_product_id)
                                        asset_val = plan_qty * unit_cost

                                        # A. 增加预入库大货资产 (正数)
                                        db.add(CompanyBalanceItem(
                                            name=f"预入库大货资产-{p_name}",
                                            amount=asset_val, category="asset", currency="CNY"
                                        ))

                                        # B. 冲销在制资产 (负数)
                                        db.add(CompanyBalanceItem(
                                            name=f"在制资产冲销-{p_name}",
                                            amount=-asset_val, category="asset", currency="CNY"
                                        ))

                                        db.commit()
                                        st.toast(f"已登记生产完成：{plan_qty} 件转入预入库", icon="🏭")
                                        st.rerun()

                                # 按钮 2: 入库完成 (将预入库转为实际)
                                # (保持不变)
                                if pre_in_qty > 0:
                                    if c_btn2.button("📥 入库完成", key=f"btn_finish_{c.id}"):
                                        # ... (内部逻辑保持不变)
                                        unit_cost = get_unit_cost(db, selected_product_id)
                                        asset_val = pre_in_qty * unit_cost
                                        
                                        pre_asset = db.query(CompanyBalanceItem).filter(
                                            CompanyBalanceItem.name == f"预入库大货资产-{p_name}"
                                        ).first()
                                        if pre_asset: pre_asset.amount -= asset_val
                                        
                                        real_asset = db.query(CompanyBalanceItem).filter(
                                            CompanyBalanceItem.name == f"大货资产-{p_name}"
                                        ).first()
                                        if real_asset: real_asset.amount += asset_val
                                        else:
                                            db.add(CompanyBalanceItem(
                                                name=f"大货资产-{p_name}", amount=asset_val, category="asset", currency="CNY"
                                            ))

                                        pending_logs = db.query(InventoryLog).filter(
                                            InventoryLog.product_name == p_name,
                                            InventoryLog.variant == c.color_name,
                                            InventoryLog.reason == "预入库"
                                        ).all()
                                        for pl in pending_logs: pl.reason = "预入库完成"
                                        
                                        db.add(InventoryLog(
                                            product_name=p_name, variant=c.color_name,
                                            change_amount=pre_in_qty, reason="入库",
                                            note="预入库转实物", date=date.today()
                                        ))
                                        
                                        c.quantity += pre_in_qty
                                        db.commit()
                                        st.toast(f"入库完成", icon="✅")
                                        st.rerun()
                            
                            st.markdown("<hr style='margin: 5px 0; opacity:0.1;'>", unsafe_allow_html=True)

                    else:
                        st.info("该产品暂无颜色/款式信息")

        st.divider()

        # --- 第二行：录入表单 ---
        f1, f2, f3, f4, f5 = st.columns(5)
        move_type = f1.selectbox("变动类型", ["出库", "入库", "预出库", "预入库"])
        color_options = [c.color_name for c in colors] if selected_product_id and colors else ["通用/无颜色"]
        p_var = f2.selectbox("款式/颜色", color_options)
        input_qty = f3.number_input("数量", min_value=1, step=1, value=1)
        p_remark = f4.text_input("备注", "")
        
        with f5:
            st.write("") 
            submit_btn = st.button("提交变动", type="primary", use_container_width=True)

        if submit_btn:
            # ... (手动提交变动的逻辑保持不变，用于特殊调整) ...
            if p_name == "暂无产品":
                st.error("请先创建产品！")
            else:
                qty_change = input_qty if move_type in ["入库", "预入库"] else -input_qty
                
                db.add(InventoryLog(
                    product_name=p_name, variant=p_var, 
                    change_amount=qty_change, reason=move_type, 
                    note=p_remark, date=date.today()
                ))
                
                if selected_product_id and move_type in ["入库", "出库"]:
                     color_record = db.query(ProductColor).filter(
                        ProductColor.product_id == selected_product_id,
                        ProductColor.color_name == p_var
                    ).first()
                     if color_record: color_record.quantity += qty_change

                # 资产联动 (保持逻辑一致)
                unit_cost = get_unit_cost(db, selected_product_id)
                val_change = input_qty * unit_cost
                
                # 辅助函数
                def update_bi(name, delta):
                    item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name==name).first()
                    if item: item.amount += delta
                    else: db.add(CompanyBalanceItem(name=name, amount=delta, category="asset"))

                if move_type == "入库": update_bi(f"大货资产-{p_name}", val_change)
                elif move_type == "出库": update_bi(f"大货资产-{p_name}", -val_change)
                elif move_type == "预入库": update_bi(f"预入库大货资产-{p_name}", val_change)
                elif move_type == "预出库": 
                    update_bi(f"预入库大货资产-{p_name}", -val_change)
                    sp = get_selling_price(selected_product, exchange_rate)
                    update_bi(f"预售额-{p_name}", input_qty * sp)

                db.commit()
                st.rerun()

    st.divider()

    # --- 显示日志表格 ---
    logs = db.query(InventoryLog).order_by(InventoryLog.id.desc()).all()
    if logs:
        st.subheader("📜 历史记录")
        display_data = []
        for l in logs:
            display_data.append({
                "日期": l.date, "产品": l.product_name, "款式": l.variant,
                "数量": l.change_amount, "类型": l.reason, "备注": l.note
            })
        st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
    else:
        st.info("暂无记录")