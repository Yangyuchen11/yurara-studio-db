import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy import func, or_ # 需要引入 or_
from models import Product, InventoryLog, ProductColor, CompanyBalanceItem, CostItem, PreShippingItem, FinanceRecord

# === 辅助函数：获取产品单位成本 ===
def get_unit_cost(db, product_id):
    total_actual_cost = db.query(func.sum(CostItem.actual_cost))\
        .filter(CostItem.product_id == product_id).scalar() or 0.0
    product = db.query(Product).filter(Product.id == product_id).first()
    total_qty = product.total_quantity if product else 0
    if total_qty > 0:
        return total_actual_cost / total_qty
    return 0.0

# === 辅助函数：更新资产（按名称） ===
def update_bi_by_name(db, name, delta, category="asset", currency="CNY", finance_id=None):
    item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name==name).first()
    if item: 
        item.amount += delta
        # 只有当金额非常接近0且无流水的孤立资产才删除，防止频繁创建删除
        if abs(item.amount) <= 0.01: db.delete(item)
    else: 
        db.add(CompanyBalanceItem(
            name=name, amount=delta, category=category, 
            currency=currency, finance_record_id=finance_id
        ))

# === 主页面逻辑 ===
def show_inventory_page(db):
    exchange_rate_input = st.session_state.get("global_rate_input", 4.8)
    exchange_rate = exchange_rate_input / 100.0

    st.header("📦 库存与销售额管理")
    
    # ================= 1. 销售额一览 =================
    st.subheader("📊 销售数据一览")
    with st.container(border=True):
        logs_sold = db.query(InventoryLog).filter(InventoryLog.is_sold == True).all()
        logs_other = db.query(InventoryLog).filter(InventoryLog.is_other_out == True).all()

        total_sales_cny = sum([l.sale_amount for l in logs_sold if l.currency == 'CNY'])
        total_sales_jpy = sum([l.sale_amount for l in logs_sold if l.currency == 'JPY'])
        total_qty_sold = sum([-l.change_amount for l in logs_sold])
        total_qty_other = sum([abs(l.change_amount) for l in logs_other])

        platform_stats = {}
        for l in logs_sold:
            pf = l.platform or "未知平台"
            if pf not in platform_stats:
                platform_stats[pf] = {'amount': 0.0, 'qty': 0}
            platform_stats[pf]['amount'] += l.sale_amount
            platform_stats[pf]['qty'] += -l.change_amount

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("总销售额 (CNY)", f"¥ {total_sales_cny:,.2f}")
        m2.metric("总销售额 (JPY)", f"¥ {total_sales_jpy:,.0f}")
        m3.metric("净售出数量", f"{total_qty_sold} 件")
        m4.metric("其他出库数量", f"{total_qty_other} 件")

        if platform_stats:
            st.caption("各平台销售详情 (含退款抵扣):")
            data_list = []
            for pf, stats in platform_stats.items():
                data_list.append({
                    "平台": pf,
                    "销售额 (原币累加)": f"{stats['amount']:,.2f}",
                    "净销量": stats['qty']
                })
            st.dataframe(pd.DataFrame(data_list), use_container_width=True, hide_index=True)

    st.divider()

    # ================= 2. 预出库列表管理 =================
    st.subheader("🚚 预出库/待发货管理")
    st.caption("此处管理的商品尚未扣减实际库存，但已计入债务与预售额。")
    pre_items = db.query(PreShippingItem).all()
    
    if pre_items:
        pre_data = []
        for p in pre_items:
            pre_data.append({
                "日期": p.created_date,
                "产品": f"{p.product_name} - {p.variant}",
                "数量": p.quantity,
                "预售额": f"{p.pre_sale_amount} {p.currency}",
                "备注": p.note
            })
        st.dataframe(pd.DataFrame(pre_data), use_container_width=True, hide_index=True)
        
        c_p1, c_p2 = st.columns([3, 1])
        selected_pre_id = c_p1.selectbox("选择要完成发货的订单", [p.id for p in pre_items], format_func=lambda x: next((f"{i.created_date} | {i.product_name}-{i.variant} (Qty:{i.quantity})" for i in pre_items if i.id == x), "Unknown"))
        
        if c_p2.button("✅ 出库完成 (转收入)", type="primary"):
            target_pre = db.query(PreShippingItem).filter(PreShippingItem.id == selected_pre_id).first()
            if target_pre:
                try:
                    if target_pre.related_debt_id:
                        debt_item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_pre.related_debt_id).first()
                        if debt_item: db.delete(debt_item) 
                    
                    fin_rec = FinanceRecord(date=date.today(), amount=target_pre.pre_sale_amount, currency=target_pre.currency, category="销售收入", description=f"预出库转实销: {target_pre.product_name}-{target_pre.variant} (x{target_pre.quantity})")
                    db.add(fin_rec)
                    db.flush()
                    
                    target_asset_name = f"流动资金({target_pre.currency})"
                    update_bi_by_name(db, target_asset_name, target_pre.pre_sale_amount, category="asset", currency=target_pre.currency, finance_id=fin_rec.id)

                    log_out = InventoryLog(product_name=target_pre.product_name, variant=target_pre.variant, change_amount=-target_pre.quantity, reason="出库", note=f"预出库完成: {target_pre.note}", is_sold=True, sale_amount=target_pre.pre_sale_amount, currency=target_pre.currency, platform="预售转出")
                    db.add(log_out)
                    
                    db.delete(target_pre)
                    db.commit()
                    st.toast(f"出库完成！资金已存入 {target_asset_name}", icon="💰")
                    st.rerun()
                except Exception as e:
                    st.error(f"操作失败: {e}")
    else:
        st.info("当前没有挂起的预出库项目。")

    st.divider()

    # ================= 3. 库存一览与操作 =================
    st.subheader("📝 库存变动录入")
    
    products = db.query(Product).all()
    product_names = [p.name for p in products]
    
    c_sel, c_view = st.columns([1, 3])
    p_name = c_sel.selectbox("选择产品", product_names or ["暂无产品"])
    
    selected_product_id = None
    colors = []

    if products and p_name != "暂无产品":
        selected_product = next((p for p in products if p.name == p_name), None)
        selected_product_id = selected_product.id
        
        with c_view:
            if selected_product_id:
                colors = db.query(ProductColor).filter(ProductColor.product_id == selected_product_id).order_by(ProductColor.id.asc()).all()
                all_logs = db.query(InventoryLog).filter(InventoryLog.product_name == p_name).all()
                
                real_stock_map = {}
                pre_in_map = {}
                
                for log in all_logs:
                    if log.reason in ["入库", "出库", "额外生产入库", "退货入库"]:
                        real_stock_map[log.variant] = real_stock_map.get(log.variant, 0) + log.change_amount
                    
                    # 统计预入库：包含正常的“预入库”和“计划入库减少”
                    elif log.reason in ["预入库", "计划入库减少"]:
                        pre_in_map[log.variant] = pre_in_map.get(log.variant, 0) + log.change_amount
                
                pre_out_items = db.query(PreShippingItem).filter(PreShippingItem.product_name == p_name).all()
                pre_out_map = {}
                for item in pre_out_items:
                    pre_out_map[item.variant] = pre_out_map.get(item.variant, 0) + item.quantity

                if colors:
                    cols_cfg = [1.5, 1, 1, 1, 1, 1, 1, 2.5]
                    h1, h2, h3, h4, h5, h6, h7, h8 = st.columns(cols_cfg)
                    h1.markdown("**款式**")
                    h2.markdown("**计划**")
                    h3.markdown("**已产**")
                    h4.markdown("**库存**") 
                    h5.markdown("**预入**")
                    h6.markdown("**预出**") 
                    h7.markdown("**状态**")
                    h8.markdown("**操作**")
                    
                    st.markdown("<hr style='margin: 5px 0; opacity:0.5;'>", unsafe_allow_html=True)

                    for c in colors:
                        real_qty = real_stock_map.get(c.color_name, 0)
                        pre_in_qty = pre_in_map.get(c.color_name, 0)
                        pre_out_qty = pre_out_map.get(c.color_name, 0)
                        produced_qty = c.produced_quantity if c.produced_quantity is not None else 0
                        status = "🔴 缺货" if real_qty <= 0 else "🟢 有货"

                        r1, r2, r3, r4, r5, r6, r7, r8 = st.columns(cols_cfg)
                        r1.write(f"🎨 {c.color_name}")
                        r2.write(f"**{c.quantity}**")
                        r3.write(f"{produced_qty}")
                        r4.write(f"{int(real_qty)}")
                        r5.write(f"{int(pre_in_qty)}")
                        r6.write(f"{int(pre_out_qty)}")
                        r7.write(status)

                        with r8:
                            c_btn1, c_btn2 = st.columns([1, 1])
                            
                            # 按钮 1: 生产完成 (逻辑不变)
                            if pre_in_qty == 0 and c.quantity > 0:
                                if c_btn1.button("🏭 生产完成", key=f"btn_prod_done_{c.id}"):
                                    db.add(InventoryLog(product_name=p_name, variant=c.color_name, change_amount=c.quantity, reason="预入库", note="生产完成", date=date.today()))
                                    unit_cost = get_unit_cost(db, selected_product_id)
                                    val = c.quantity * unit_cost
                                    update_bi_by_name(db, f"预入库大货资产-{p_name}", val)
                                    update_bi_by_name(db, f"在制资产冲销-{p_name}", -val)
                                    db.commit()
                                    st.rerun()

                            # =======================================================
                            # 【修复版】按钮 2: 入库完成 / 结单清理
                            # =======================================================
                            
                            # 1. 检测当前商品是否有挂起的流程
                            has_pending_logs = False
                            for log in all_logs:
                                if log.variant == c.color_name and log.reason in ["预入库", "计划入库减少"]:
                                    has_pending_logs = True
                                    break
                            
                            if has_pending_logs:
                                btn_label = "📥 入库完成" if pre_in_qty > 0 else "✅ 结单/清理"
                                
                                if c_btn2.button(btn_label, key=f"btn_finish_{c.id}"):
                                    try:
                                        unit_cost = get_unit_cost(db, selected_product_id)
                                        
                                        # --- A. 正常入库逻辑 (仅当数量>0时执行) ---
                                        if pre_in_qty > 0:
                                            val = pre_in_qty * unit_cost
                                            # 资产转移：预入库 -> 大货
                                            update_bi_by_name(db, f"预入库大货资产-{p_name}", -val)
                                            update_bi_by_name(db, f"大货资产-{p_name}", val)
                                            
                                            # 记录入库日志
                                            db.add(InventoryLog(product_name=p_name, variant=c.color_name, change_amount=pre_in_qty, reason="入库", note="预入库转实物", date=date.today()))
                                            
                                            # 更新颜色表的已产数量
                                            if c.produced_quantity is None: c.produced_quantity = 0
                                            c.produced_quantity += pre_in_qty
                                        
                                        # --- B. 状态更新 (将当前款式的预入库标记为完成) ---
                                        # 获取当前款式的所有挂起日志
                                        pending_logs = db.query(InventoryLog).filter(
                                            InventoryLog.product_name == p_name,
                                            InventoryLog.variant == c.color_name,
                                            or_(InventoryLog.reason == "预入库", InventoryLog.reason == "计划入库减少")
                                        ).all()
                                        for pl in pending_logs: pl.reason = "预入库完成"
                                        
                                        # 归零计划数量
                                        c.quantity = 0 
                                        
                                        # --- C. 全局清理检测 (关键修复：避免卡死和资产回滚错误) ---
                                        
                                        # 核心技巧：查询“除当前款式外”是否还有其他挂起日志
                                        # 这样不需要等待数据库 flush 当前的修改，避免死锁
                                        other_pending_count = db.query(func.count(InventoryLog.id)).filter(
                                            InventoryLog.product_name == p_name,
                                            or_(InventoryLog.reason == "预入库", InventoryLog.reason == "计划入库减少"),
                                            InventoryLog.variant != c.color_name # <--- 排除当前正在处理的款式
                                        ).scalar()
                                        
                                        # 如果其他款式都搞定了，说明这是最后一个动作 -> 执行清理
                                        if other_pending_count == 0:
                                            
                                            # 1. 计算该商品的历史总投入成本 (正数)
                                            total_actual_cost = db.query(func.sum(CostItem.actual_cost))\
                                                .filter(CostItem.product_id == selected_product_id).scalar() or 0.0
                                            
                                            wip_asset_name = f"预入库大货资产-{p_name}"
                                            offset_asset_name = f"在制资产冲销-{p_name}"
                                            
                                            # 2. 清理【预入库资产】 (如果有残余，说明是误差，记录调整并删除)
                                            wip_item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == wip_asset_name).first()
                                            if wip_item:
                                                if abs(wip_item.amount) > 0.01:
                                                    db.add(FinanceRecord(
                                                        date=date.today(),
                                                        amount=-wip_item.amount,
                                                        currency="CNY",
                                                        category="生产完成时开销调整",
                                                        description=f"【自动】{p_name} 预入库资产残余清理: {wip_item.amount:.2f}"
                                                    ))
                                                db.delete(wip_item)
                                            
                                            # 3. 修正【在制资产冲销】 (关键！不能删除，必须设为 -总成本)
                                            # 逻辑：资产负债表里的“在制资产” = 总成本(CostItems) + 冲销项。
                                            # 要让它归零，冲销项必须等于 -总成本。
                                            target_offset_val = -total_actual_cost
                                            
                                            offset_item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == offset_asset_name).first()
                                            if not offset_item:
                                                # 如果之前被误删了，这里重建
                                                offset_item = CompanyBalanceItem(
                                                    name=offset_asset_name,
                                                    amount=target_offset_val,
                                                    category="asset",
                                                    currency="CNY"
                                                )
                                                db.add(offset_item)
                                            else:
                                                offset_item.amount = target_offset_val
                                            
                                            # 只有当真正的总成本为0时，才删除冲销项
                                            if abs(total_actual_cost) < 0.01 and offset_item:
                                                 db.delete(offset_item)
                                        
                                        db.commit()
                                        st.toast("操作成功", icon="✅")
                                        st.rerun()
                                        
                                    except Exception as e:
                                        db.rollback()
                                        st.error(f"操作发生错误: {e}")

                        st.markdown("<hr style='margin: 5px 0; opacity:0.1;'>", unsafe_allow_html=True)
                else:
                    st.info("该产品暂无颜色/款式信息")

    st.divider()

    # ================= 4. 变动录入表单 =================
    f_type, f_var, f_qty, f_remark, f_btn = st.columns([1.2, 1.2, 0.8, 1.2, 0.8])
    move_type = f_type.selectbox("变动类型", ["出库", "入库", "退货入库", "预入库", "预出库", "额外生产入库", "计划入库减少"])
    
    color_options = [c.color_name for c in colors] if selected_product_id and colors else ["通用"]
    p_var = f_var.selectbox("款式", color_options)
    input_qty = f_qty.number_input("数量", min_value=1, step=1)
    p_remark = f_remark.text_input("备注")
    
    extra_info_col = st.container()
    
    out_type = "其他"
    sale_price = 0.0
    sale_curr = "CNY"
    sale_platform = "其他"
    pre_sale_price = 0.0
    pre_sale_curr = "CNY"
    refund_amount = 0.0
    refund_curr = "CNY"
    refund_platform = "其他"

    if move_type == "预出库":
        with extra_info_col:
            st.info("💡 预出库不扣减实际库存。将创建一笔【成本债务】并增加预售额记录。")
            c1, c2 = st.columns(2)
            pre_sale_price = c1.number_input("预售总额", min_value=0.0, step=100.0)
            pre_sale_curr = c2.selectbox("币种", ["CNY", "JPY"], key="pre_curr")

    elif move_type == "出库":
        with extra_info_col:
            out_type = st.radio("出库类型", ["售出", "其他"], horizontal=True)
            if out_type == "售出":
                c1, c2, c3 = st.columns(3)
                sale_curr = c1.selectbox("币种", ["CNY", "JPY"], key="out_curr")
                pf_options = ["微店", "中国线下", "其他"] if sale_curr == "CNY" else ["Booth", "Instagram", "日本线下", "其他"]
                sale_platform = c2.selectbox("销售平台", pf_options)
                unit_price = c3.number_input("单价", min_value=0.0)
                sale_price = unit_price * input_qty 
                st.caption(f"💰 总销售额: {sale_price:,.2f} {sale_curr} (自动存入流动资金)")

    elif move_type == "退货入库":
        with extra_info_col:
            st.info("💡 退货入库：增加库存，同时从流动资金中扣除退款。")
            rc1, rc2, rc3 = st.columns(3)
            refund_curr = rc1.selectbox("退款币种", ["CNY", "JPY"], key="ref_curr")
            refund_amount = rc2.number_input("退款总额", min_value=0.0, step=100.0)
            refund_platform = rc3.text_input("退款平台", placeholder="如：微店")

    elif move_type == "计划入库减少":
        with extra_info_col:
            st.warning("⚠️ 此操作将减少【预入库】数量，并回滚资产。请确保预入库数量足够扣减。")

    with f_btn:
        st.write("")
        if st.button("提交", type="primary"):
            if p_name == "暂无产品":
                st.error("无效产品")
                st.stop()

            # =======================================================
            # 【新增校验】: 计划入库减少前的库存检查
            # =======================================================
            if move_type == "计划入库减少":
                # 计算当前款式的“有效预入库数量”
                # 逻辑与上方表格的统计逻辑一致：只统计状态为 "预入库" 或 "计划入库减少" 的日志
                current_pre_in_qty = 0
                check_logs = db.query(InventoryLog).filter(
                    InventoryLog.product_name == p_name,
                    InventoryLog.variant == p_var,
                    or_(InventoryLog.reason == "预入库", InventoryLog.reason == "计划入库减少")
                ).all()
                
                for l in check_logs:
                    current_pre_in_qty += l.change_amount
                
                if current_pre_in_qty <= 0:
                    st.error(f"❌ 失败：款式【{p_var}】当前没有挂起的预入库数量，无法执行减少操作。")
                    st.stop()
                
                if input_qty > current_pre_in_qty:
                    st.error(f"❌ 失败：减少数量 ({input_qty}) 不能超过当前预入库总数 ({current_pre_in_qty})。")
                    st.stop()
            # =======================================================

            try:
                # --- 1. 预出库 ---
                if move_type == "预出库":
                    unit_cost = get_unit_cost(db, selected_product_id)
                    cost_debt_amount = unit_cost * input_qty
                    debt_name = f"{p_name}-{p_var}-预出库成本"
                    debt_item = CompanyBalanceItem(name=debt_name, amount=cost_debt_amount, category="liability", currency="CNY")
                    db.add(debt_item)
                    db.flush() 
                    pre_item = PreShippingItem(product_name=p_name, variant=p_var, quantity=input_qty, pre_sale_amount=pre_sale_price, currency=pre_sale_curr, related_debt_id=debt_item.id, note=p_remark)
                    db.add(pre_item)
                    st.toast(f"预出库登记成功！", icon="🚚")

                # --- 2. 出库 ---
                elif move_type == "出库":
                    is_sold = (out_type == "售出")
                    final_sale_amount = sale_price if is_sold else 0
                    log = InventoryLog(product_name=p_name, variant=p_var, change_amount=-input_qty, reason="出库", note=f"{out_type} | {p_remark}", is_sold=is_sold, sale_amount=final_sale_amount, currency=sale_curr if is_sold else None, platform=sale_platform if is_sold else None, is_other_out=not is_sold)
                    db.add(log)
                    if is_sold:
                        fin_rec = FinanceRecord(date=date.today(), amount=final_sale_amount, currency=sale_curr, category="销售收入", description=f"{p_name}-{p_var} 售出 (x{input_qty}) @{sale_platform}")
                        db.add(fin_rec)
                        update_bi_by_name(db, f"流动资金({sale_curr})", final_sale_amount, category="asset", currency=sale_curr, finance_id=fin_rec.id)
                    unit_cost = get_unit_cost(db, selected_product_id)
                    cost_val = input_qty * unit_cost
                    update_bi_by_name(db, f"大货资产-{p_name}", -cost_val)
                    st.toast(f"出库成功！", icon="📤")

                # --- 3. 退货入库 ---
                elif move_type == "退货入库":
                    db.add(InventoryLog(product_name=p_name, variant=p_var, change_amount=input_qty, reason="退货入库", note=f"平台: {refund_platform} | {p_remark}", date=date.today(), is_sold=True, sale_amount=-refund_amount, currency=refund_curr, platform=refund_platform))
                    fin_rec = FinanceRecord(date=date.today(), amount=-refund_amount, currency=refund_curr, category="销售退款", description=f"{p_name}-{p_var} 退货 (x{input_qty}) | {p_remark}")
                    db.add(fin_rec)
                    update_bi_by_name(db, f"流动资金({refund_curr})", -refund_amount, category="asset", currency=refund_curr)
                    unit_cost = get_unit_cost(db, selected_product_id)
                    asset_val = input_qty * unit_cost
                    update_bi_by_name(db, f"大货资产-{p_name}", asset_val)
                    st.toast("退货入库完成", icon="↩️")

                # --- 4. 计划入库减少 ---
                elif move_type == "计划入库减少":
                    # 1. 记录负向日志，理由为“计划入库减少”
                    db.add(InventoryLog(product_name=p_name, variant=p_var, change_amount=-input_qty, reason="计划入库减少", note=f"修正预入库: {p_remark}", date=date.today()))
                    
                    # 2. 资产回滚：减少预入库资产，增加在制资产冲销(恢复)
                    unit_cost = get_unit_cost(db, selected_product_id)
                    val = input_qty * unit_cost
                    update_bi_by_name(db, f"预入库大货资产-{p_name}", -val)
                    update_bi_by_name(db, f"在制资产冲销-{p_name}", val)
                    st.toast(f"预入库数量已减少: {input_qty}", icon="📉")

                # --- 5. 入库/预入库/额外生产 ---
                else:
                    qty_change = input_qty 
                    db.add(InventoryLog(product_name=p_name, variant=p_var, change_amount=qty_change, reason=move_type, note=p_remark, date=date.today()))
                    if move_type == "额外生产入库" and selected_product_id:
                        c_rec = db.query(ProductColor).filter(ProductColor.product_id==selected_product_id, ProductColor.color_name==p_var).first()
                        if c_rec: 
                            if c_rec.produced_quantity is None: c_rec.produced_quantity = 0
                            c_rec.produced_quantity += input_qty
                    unit_cost = get_unit_cost(db, selected_product_id)
                    val_change = input_qty * unit_cost
                    if move_type in ["入库", "额外生产入库"]: update_bi_by_name(db, f"大货资产-{p_name}", val_change)
                    elif move_type == "预入库": update_bi_by_name(db, f"预入库大货资产-{p_name}", val_change)
                    st.toast(f"{move_type} 成功", icon="📥")

                db.commit()
                st.rerun()

            except Exception as e:
                db.rollback()
                st.error(f"操作失败: {e}")

    # ================= 5. 库存变动记录 =================
    st.subheader("📜 库存变动记录")
    logs = db.query(InventoryLog).order_by(InventoryLog.id.desc()).all()
    if logs:
        log_data = []
        for l in logs:
            desc = l.note
            if l.is_sold: 
                if l.change_amount < 0: desc = f"售出: ¥{l.sale_amount}{l.currency} ({l.platform})"
                else: desc = f"退货: -¥{abs(l.sale_amount)}{l.currency} ({l.platform})"
            elif l.is_other_out: desc = f"其他出库: {l.note}"
            log_data.append({
                "日期": l.date, "产品": l.product_name, "款式": l.variant,
                "数量": l.change_amount, "类型": l.reason, "详情": desc
            })
        st.dataframe(pd.DataFrame(log_data), use_container_width=True, hide_index=True)
    else:
        st.info("暂无记录")