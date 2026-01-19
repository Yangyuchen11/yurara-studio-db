import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy import func, or_
from models import Product, InventoryLog, ProductColor, CompanyBalanceItem, CostItem, PreShippingItem, FinanceRecord

# === 定义成本分类 ===
COST_CATEGORIES = ["大货材料费", "大货加工费", "物流邮费", "包装费", "设计开发费", "检品发货等人工费", "宣发费", "其他成本"]

# === 辅助函数：获取产品单位成本 ===
def get_unit_cost(db, product_id):
    total_actual_cost = db.query(func.sum(CostItem.actual_cost))\
        .filter(CostItem.product_id == product_id).scalar() or 0.0
    product = db.query(Product).filter(Product.id == product_id).first()
    # 使用可销售数量作为分母，如果未设置则回退到总数量
    denom = product.marketable_quantity if (product and product.marketable_quantity is not None) else (product.total_quantity if product else 0)
    
    if denom > 0:
        return total_actual_cost / denom
    return 0.0

# === 辅助函数：更新资产（按名称） ===
def update_bi_by_name(db, name, delta, category="asset", currency="CNY", finance_id=None):
    item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name==name).first()
    if item: 
        item.amount += delta
        # 容错：只有当金额极小且无关联流水时才物理删除，防止误删
        if abs(item.amount) <= 0.01 and not item.finance_record_id: 
            db.delete(item)
    else: 
        db.add(CompanyBalanceItem(
            name=name, amount=delta, category=category, 
            currency=currency, finance_record_id=finance_id
        ))

# === 主页面逻辑 ===
def show_inventory_page(db):
    st.header("📦 库存管理")

    # ================= 1. 库存一览 =================
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
                pre_out_items = db.query(PreShippingItem).filter(PreShippingItem.product_name == p_name).all()
                pre_out_map = {}
                
                for log in all_logs:
                    if log.reason in ["入库", "出库", "额外生产入库", "退货入库", "发货撤销"]:
                        real_stock_map[log.variant] = real_stock_map.get(log.variant, 0) + log.change_amount
                    
                    elif log.reason in ["预入库", "计划入库减少"]:
                        pre_in_map[log.variant] = pre_in_map.get(log.variant, 0) + log.change_amount
                
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
                    h6.markdown("**待发**") # 改名：预出 -> 待发
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
                            
                            # 按钮 1: 生产完成
                            if pre_in_qty == 0 and c.quantity > 0:
                                if c_btn1.button("🏭 生产完成", key=f"btn_prod_done_v2_{c.id}"):
                                    db.add(InventoryLog(product_name=p_name, variant=c.color_name, change_amount=c.quantity, reason="预入库", note="生产完成", date=date.today()))
                                    unit_cost = get_unit_cost(db, selected_product_id)
                                    val = c.quantity * unit_cost
                                    update_bi_by_name(db, f"预入库大货资产-{p_name}", val)
                                    update_bi_by_name(db, f"在制资产冲销-{p_name}", -val)
                                    db.commit()
                                    st.rerun()

                            # 按钮 2: 入库完成
                            has_pending_logs = False
                            for log in all_logs:
                                if log.variant == c.color_name and log.reason in ["预入库", "计划入库减少"]:
                                    has_pending_logs = True
                                    break
                            
                            if has_pending_logs:
                                btn_label = "📥 入库完成" if pre_in_qty > 0 else "✅ 结单/清理"
                                if c_btn2.button(btn_label, key=f"btn_finish_stock_{c.id}"):
                                    try:
                                        unit_cost = get_unit_cost(db, selected_product_id)
                                        
                                        if pre_in_qty > 0:
                                            val = pre_in_qty * unit_cost
                                            update_bi_by_name(db, f"预入库大货资产-{p_name}", -val)
                                            update_bi_by_name(db, f"大货资产-{p_name}", val)
                                            db.add(InventoryLog(product_name=p_name, variant=c.color_name, change_amount=pre_in_qty, reason="入库", note="预入库转实物", date=date.today()))
                                            if c.produced_quantity is None: c.produced_quantity = 0
                                            c.produced_quantity += pre_in_qty
                                        
                                        pending_logs = db.query(InventoryLog).filter(
                                            InventoryLog.product_name == p_name,
                                            InventoryLog.variant == c.color_name,
                                            or_(InventoryLog.reason == "预入库", InventoryLog.reason == "计划入库减少")
                                        ).all()
                                        for pl in pending_logs: pl.reason = "预入库完成"
                                        
                                        c.quantity = 0 
                                        
                                        other_pending_count = db.query(func.count(InventoryLog.id)).filter(
                                            InventoryLog.product_name == p_name,
                                            or_(InventoryLog.reason == "预入库", InventoryLog.reason == "计划入库减少"),
                                            InventoryLog.variant != c.color_name 
                                        ).scalar()
                                        
                                        if other_pending_count == 0:
                                            wip_asset_name = f"预入库大货资产-{p_name}"
                                            offset_asset_name = f"在制资产冲销-{p_name}"
                                            wip_item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == wip_asset_name).first()

                                            if wip_item:
                                                residual_val = wip_item.amount
                                                if abs(residual_val) > 0.01:
                                                    db.add(FinanceRecord(
                                                        date=date.today(),
                                                        amount=0, 
                                                        currency="CNY",
                                                        category="资产价值修正",
                                                        description=f"【调账】{p_name} 结单修正：{residual_val:,.2f}"
                                                    ))
                                                    db.delete(wip_item) 
                                                    st.toast(f"已清理账面偏差: {residual_val:,.2f}", icon="⚖️")

                                            offset_item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == offset_asset_name).first()
                                            if offset_item:
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

    # ================= 2. 出库/发货管理 (原预出库) =================
    st.subheader("🚚 出库/发货管理 (待结算)")
    st.caption("此处显示已从库存扣除、但资金尚未结算到账的订单。")
    pre_items = db.query(PreShippingItem).filter(PreShippingItem.product_name == p_name).all()
    
    if pre_items:
        pre_data_list = []
        for p in pre_items:
            pre_data_list.append({
                "ID": p.id,
                "日期": p.created_date,
                "产品": p.product_name,
                "款式": p.variant,
                "数量": p.quantity,
                "预售/销售额": p.pre_sale_amount, # 改名
                "币种": p.currency,
                "备注": p.note
            })
        
        df_pre = pd.DataFrame(pre_data_list)
        
        edited_pre_df = st.data_editor(
            df_pre, 
            key="pre_shipping_editor",
            use_container_width=True, 
            hide_index=True,
            disabled=["ID", "日期", "产品", "款式"],
            column_config={
                "ID": None,
                "数量": st.column_config.NumberColumn(min_value=1, step=1, disabled=True), # 数量禁止在此修改，因为已经扣了库存，修改会很麻烦
                "预售/销售额": st.column_config.NumberColumn(format="%.2f"),
                "币种": st.column_config.SelectboxColumn(options=["CNY", "JPY"])
            }
        )
        
        # --- 捕获并处理修改 (仅允许修改金额和备注) ---
        if st.session_state.get("pre_shipping_editor") and st.session_state["pre_shipping_editor"].get("edited_rows"):
            changes = st.session_state["pre_shipping_editor"]["edited_rows"]
            has_p_change = False
            
            for index, diff in changes.items():
                item_id = int(df_pre.iloc[int(index)]["ID"])
                p_obj = db.query(PreShippingItem).filter(PreShippingItem.id == item_id).first()
                if p_obj:
                    # 如果修改了金额/币种，联动更新“待结算”资产
                    if "预售/销售额" in diff or "币种" in diff:
                        if "预售/销售额" in diff: p_obj.pre_sale_amount = diff["预售/销售额"]
                        if "币种" in diff: p_obj.currency = diff["币种"]
                        
                        # 查找关联的"待结算"资产项 (ID存储在 related_debt_id 中)
                        if p_obj.related_debt_id:
                            asset_item = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == p_obj.related_debt_id).first()
                            if asset_item:
                                asset_item.amount = p_obj.pre_sale_amount
                                asset_item.currency = p_obj.currency
                        has_p_change = True
                        
                    if "备注" in diff:
                        p_obj.note = diff["备注"]
                        has_p_change = True

            if has_p_change:
                db.commit()
                st.toast("发货单信息已更新", icon="💾")
                st.rerun()
        
        c_p1, c_p2 = st.columns([3.5, 1], vertical_alignment="bottom")
        
        with c_p1:
            pre_item_labels = {
                p.id: f"{p.created_date} | {p.product_name}-{p.variant} (Qty:{p.quantity}) | 📝{p.note or ''}"
                for p in pre_items
            }
            selected_pre_id = st.selectbox(
                "选择要确认收款的订单", 
                options=list(pre_item_labels.keys()), 
                format_func=lambda x: pre_item_labels.get(x, "未知订单"),
                key="sel_pre_ship_order"
            )
            
        with c_p2:
            if st.button("✅ 确认收款 (转收入)", type="primary", use_container_width=True):
                target_pre = db.query(PreShippingItem).filter(PreShippingItem.id == selected_pre_id).first()
                if target_pre:
                    try:
                        # 1. 删除关联的“待结算”资产 (使用 related_debt_id 存储了资产ID)
                        if target_pre.related_debt_id:
                            pending_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_pre.related_debt_id).first()
                            if pending_asset: db.delete(pending_asset)
                        
                        # 2. 记录真实收入并增加现金资产
                        fin_rec = FinanceRecord(
                            date=date.today(), 
                            amount=target_pre.pre_sale_amount, 
                            currency=target_pre.currency, 
                            category="销售收入", 
                            description=f"发货单收款: {target_pre.product_name}-{target_pre.variant} (x{target_pre.quantity})"
                        )
                        db.add(fin_rec)
                        db.flush()
                        
                        target_asset_name = f"流动资金({target_pre.currency})"
                        update_bi_by_name(db, target_asset_name, target_pre.pre_sale_amount, category="asset", currency=target_pre.currency, finance_id=fin_rec.id)

                        # 注意：这里不再写 InventoryLog，也不再扣库存，因为在加入列表时已经扣过了
                        # 只是把 PreShippingItem 删掉
                        db.delete(target_pre)
                        db.commit()
                        st.toast(f"收款完成！资金已存入 {target_asset_name}", icon="💰")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"操作失败: {e}")
    else:
        st.info("当前没有待结算的发货单。")

    # --- 撤销/删除预出库逻辑 (带回滚库存) ---
    st.write("") 
    with st.popover("🗑️ 撤销发货 (库存回滚)", use_container_width=True):
        st.error("⚠️ 注意：此操作将删除发货单，并**自动把库存加回去**。")
        
        del_pre_options = {
            f"{p.created_date} | {p.product_name}-{p.variant} (Qty:{p.quantity}) | 📝{p.note or ''}": p.id 
            for p in pre_items
        }
        
        selected_del_pre_label = st.selectbox(
            "选择要撤销的发货记录", 
            options=list(del_pre_options.keys()), 
            key="del_pre_select_box"
        )
        
        if st.button("🔴 确认撤销并回滚", type="primary", use_container_width=True):
            target_pre_id = del_pre_options[selected_del_pre_label]
            target_pre_obj = db.query(PreShippingItem).filter(PreShippingItem.id == target_pre_id).first()
            
            if target_pre_obj:
                try:
                    # 1. 回滚账面资产 (待结算款)
                    if target_pre_obj.related_debt_id:
                        pending_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_pre_obj.related_debt_id).first()
                        if pending_asset: db.delete(pending_asset)
                    
                    # === 新增逻辑：提取平台信息 ===
                    # 因为 PreShippingItem 把平台存在了 note 里 ("平台:微店 | 备注...")，我们需要提取出来
                    platform_str = "其他" # 默认值
                    if target_pre_obj.note and "平台:" in target_pre_obj.note:
                        try:
                            # 提取逻辑：按 "|" 分割取第一部分，再按 ":" 分割取后面部分
                            part1 = target_pre_obj.note.split("|")[0] 
                            platform_str = part1.split(":")[-1].strip()
                        except:
                            pass
                    
                    # 2. 回滚库存数量 (InventoryLog)
                    # === 核心修改：写入 platform, sale_amount, currency ===
                    # 这样这笔撤销记录就自带了金额和平台，统计页面不需要再“猜”了
                    db.add(InventoryLog(
                        product_name=target_pre_obj.product_name,
                        variant=target_pre_obj.variant,
                        change_amount=target_pre_obj.quantity, # 正数，加回库存
                        reason="发货撤销",
                        note=f"撤销发货单: {target_pre_obj.note}",
                        date=date.today(),
                        
                        # 新增字段记录：
                        platform=platform_str,              # ✅ 记录平台
                        is_sold=False,                      # 撤销不算“已售”，但我们需要它参与计算吗？
                                                            # 💡 策略：
                                                            # 如果设为 True，它会直接出现在 filter(is_sold=True) 里。
                                                            # 如果设为 False (推荐)，保持 reason="发货撤销"，
                                                            # 但我们填上金额，让统计页面的逻辑能直接读到金额。
                        
                        sale_amount=-abs(target_pre_obj.pre_sale_amount), # ✅ 记录负金额 (直接抵扣)
                        currency=target_pre_obj.currency    # ✅ 记录币种
                    ))

                    # 3. 回滚库存资产价值 (CompanyBalance - 大货资产)
                    unit_cost = get_unit_cost(db, selected_product_id)
                    asset_val = target_pre_obj.quantity * unit_cost
                    update_bi_by_name(db, f"大货资产-{p_name}", asset_val) # 加回来

                    # 4. 删除发货单本身
                    db.delete(target_pre_obj)
                    
                    db.commit()
                    st.success(f"发货单已撤销，库存已回滚 (平台: {platform_str})。")
                    st.rerun()
                    
                except Exception as e:
                    db.rollback()
                    st.error(f"撤销失败: {e}")

    st.divider()

    # ================= 3. 变动录入表单 =================

    st.subheader("📝 库存变动录入")
    
    f_date, f_type, f_var, f_qty, f_remark, f_btn = st.columns([1, 1.1, 1.1, 0.7, 1.2, 0.7])
    
    input_date = f_date.date_input("日期", value=date.today())
    # 移除了"预出库"选项，因为现在包含在"出库"流程中
    move_type = f_type.selectbox("变动类型", ["出库", "入库", "退货入库", "预入库", "额外生产入库", "计划入库减少"])
    
    color_options = [c.color_name for c in colors] if selected_product_id and colors else ["通用"]
    p_var = f_var.selectbox("款式", color_options)
    input_qty = f_qty.number_input("数量", min_value=1, step=1)
    p_remark = f_remark.text_input("备注")
    
    extra_info_col = st.container()
    
    out_type = "其他"
    sale_price = 0.0
    sale_curr = "CNY"
    sale_platform = "其他"
    refund_amount = 0.0
    refund_curr = "CNY"
    refund_platform = "其他"
    
    cons_cat = "其他成本"
    cons_content = ""

    if move_type == "出库":
        with extra_info_col:
            out_type = st.radio("出库类型", ["售出", "消耗", "其他"], horizontal=True)
            
            if out_type == "售出":
                st.info("ℹ️ **流程说明**：点击提交后，库存将**立即扣减**，订单将进入【发货/出库管理】列表待确认收款。")
                c1, c2, c3 = st.columns(3)
                sale_curr = c1.selectbox("销售币种", ["CNY", "JPY"], key="out_curr")
                
                pf_options = ["微店", "中国线下", "其他"] if sale_curr == "CNY" else ["Booth", "Instagram", "日本线下", "其他"]
                sale_platform = c2.selectbox("销售平台", pf_options)
                
                sale_price = c3.number_input("销售总价 (应收)", min_value=0.0, step=100.0, format="%.2f", help="预计收到的总金额")
                
                if input_qty > 0 and sale_price > 0:
                    unit_val = sale_price / input_qty
                    st.caption(f"📊 折合单价: {unit_val:,.2f} {sale_curr}")

            elif out_type == "消耗":
                st.warning(f"⚠️ 注意：选择【消耗】将自动扣减该商品的【可销售数量】。（记入成本但不产生金额）")
                c_cons1, c_cons2 = st.columns([1, 2])
                cons_cat = c_cons1.selectbox("计入成本分类", COST_CATEGORIES, index=COST_CATEGORIES.index("宣发费") if "宣发费" in COST_CATEGORIES else 0)
                cons_content = c_cons2.text_input("消耗内容 (必填)", placeholder="如：宣发样衣、赠送KOL")

    elif move_type == "退货入库":
        with extra_info_col:
            st.info("💡 退货入库：增加库存，同时从流动资金中扣除退款。")
            rc1, rc2, rc3 = st.columns(3)
            refund_curr = rc1.selectbox("退款币种", ["CNY", "JPY"], key="ref_curr")
            refund_amount = rc2.number_input("退款总额", min_value=0.0, step=100.0)
            refund_platform = rc3.text_input("退款平台", placeholder="如：微店")

    with f_btn:
        st.write("")
        if st.button("提交", type="primary"):
            is_valid = True
            
            if p_name == "暂无产品":
                st.error("无效产品")
                is_valid = False

            if is_valid and move_type == "计划入库减少":
                current_pre_in_qty = 0
                check_logs = db.query(InventoryLog).filter(
                    InventoryLog.product_name == p_name,
                    InventoryLog.variant == p_var,
                    or_(InventoryLog.reason == "预入库", InventoryLog.reason == "计划入库减少")
                ).all()
                for l in check_logs: current_pre_in_qty += l.change_amount
                
                if current_pre_in_qty <= 0:
                    st.error(f"❌ 失败：款式【{p_var}】当前没有挂起的预入库数量。")
                    is_valid = False
                elif input_qty > current_pre_in_qty:
                    st.error(f"❌ 失败：减少数量 ({input_qty}) 不能超过当前预入库总数 ({current_pre_in_qty})。")
                    is_valid = False
            
            if is_valid and move_type == "出库" and out_type == "消耗":
                if not cons_content.strip():
                    st.error("❌ 失败：请填写【消耗内容】。")
                    is_valid = False

            if is_valid:
                target_prod_obj = db.query(Product).filter(Product.id == selected_product_id).first()
                try:
                    # === 核心逻辑修改：出库-售出 ===
                    if move_type == "出库":
                        # 1. 计算库存资产成本 (大货资产减少值)
                        unit_cost = get_unit_cost(db, selected_product_id)
                        cost_val = input_qty * unit_cost

                        is_sold = (out_type == "售出")
                        
                        if is_sold:
                            # === 新逻辑：进入发货管理 ===
                            # A. 创建"待结算"资产 (Pending Sales Amount)
                            asset_name = f"{p_name}-{p_var}-待结算({sale_platform})"
                            pending_asset = CompanyBalanceItem(
                                name=asset_name, 
                                amount=sale_price, 
                                category="asset", 
                                currency=sale_curr
                            )
                            db.add(pending_asset)
                            db.flush() # 获取 ID

                            # B. 创建 PreShippingItem (发货单)
                            pre_item = PreShippingItem(
                                product_name=p_name, 
                                variant=p_var, 
                                quantity=input_qty, 
                                pre_sale_amount=sale_price, 
                                currency=sale_curr, 
                                related_debt_id=pending_asset.id, # 这里复用related_debt_id字段存储待结算资产ID
                                note=f"平台:{sale_platform} | {p_remark}",
                                created_date=input_date
                            )
                            db.add(pre_item)

                            # C. 记录出库日志 (立即扣库存)
                            log = InventoryLog(
                                product_name=p_name, 
                                variant=p_var, 
                                change_amount=-input_qty, # 负数扣库存
                                reason="出库", 
                                note=f"售出待结: {p_remark}", 
                                is_sold=True, 
                                sale_amount=sale_price, 
                                currency=sale_curr, 
                                platform=sale_platform, 
                                date=input_date
                            )
                            db.add(log)

                            # D. 扣减库存资产 (大货资产)
                            update_bi_by_name(db, f"大货资产-{p_name}", -cost_val)

                            st.toast(f"已录入发货单，库存已扣减", icon="🚚")

                        elif out_type == "消耗":
                            # 消耗逻辑保持不变
                            if target_prod_obj:
                                if target_prod_obj.marketable_quantity is None: target_prod_obj.marketable_quantity = target_prod_obj.total_quantity
                                target_prod_obj.marketable_quantity -= input_qty
                                
                                combined_remark = f"款式:{p_var} 数量:{input_qty}"
                                if p_remark: combined_remark += f" | {p_remark}"

                                new_cost = CostItem(
                                    product_id=selected_product_id,
                                    item_name=cons_content, 
                                    actual_cost=0,          
                                    supplier="",            
                                    category=cons_cat,      
                                    unit_price=0,           
                                    quantity=0,             
                                    unit="",                
                                    remarks=combined_remark 
                                )
                                db.add(new_cost)
                                st.toast(f"可销售数量已减少 {input_qty}，记录已添加至【{cons_cat}】", icon="📉")

                            log_note = f"消耗: {cons_content} | {p_remark}"
                            db.add(InventoryLog(product_name=p_name, variant=p_var, change_amount=-input_qty, reason="出库", note=log_note, is_other_out=True, date=input_date))
                            update_bi_by_name(db, f"大货资产-{p_name}", -cost_val)

                        else: # 其他出库
                            log_note = f"其他: {p_remark}"
                            db.add(InventoryLog(product_name=p_name, variant=p_var, change_amount=-input_qty, reason="出库", note=log_note, is_other_out=True, date=input_date))
                            update_bi_by_name(db, f"大货资产-{p_name}", -cost_val)
                            st.toast(f"其他出库成功", icon="📤")

                    elif move_type == "退货入库":
                        db.add(InventoryLog(product_name=p_name, variant=p_var, change_amount=input_qty, reason="退货入库", note=f"平台: {refund_platform} | {p_remark}", date=input_date, is_sold=True, sale_amount=-refund_amount, currency=refund_curr, platform=refund_platform))
                        fin_rec = FinanceRecord(date=input_date, amount=-refund_amount, currency=refund_curr, category="销售退款", description=f"{p_name}-{p_var} 退货 (x{input_qty}) | {p_remark}")
                        db.add(fin_rec)
                        update_bi_by_name(db, f"流动资金({refund_curr})", -refund_amount, category="asset", currency=refund_curr)
                        unit_cost = get_unit_cost(db, selected_product_id)
                        asset_val = input_qty * unit_cost
                        update_bi_by_name(db, f"大货资产-{p_name}", asset_val)
                        st.toast("退货入库完成", icon="↩️")

                    elif move_type == "计划入库减少":
                        if target_prod_obj:
                            if target_prod_obj.marketable_quantity is None: target_prod_obj.marketable_quantity = target_prod_obj.total_quantity
                            target_prod_obj.marketable_quantity -= input_qty
                            st.toast(f"可销售数量已减少 {input_qty}", icon="📉")

                        db.add(InventoryLog(product_name=p_name, variant=p_var, change_amount=-input_qty, reason="计划入库减少", note=f"修正预入库: {p_remark}", date=input_date))
                        unit_cost = get_unit_cost(db, selected_product_id)
                        val = input_qty * unit_cost
                        update_bi_by_name(db, f"预入库大货资产-{p_name}", -val)
                        update_bi_by_name(db, f"在制资产冲销-{p_name}", val)
                        st.toast(f"预入库数量已减少: {input_qty}", icon="📉")

                    else: # 入库, 预入库, 额外生产入库
                        qty_change = input_qty 
                        db.add(InventoryLog(product_name=p_name, variant=p_var, change_amount=qty_change, reason=move_type, note=p_remark, date=input_date))
                        
                        if move_type == "额外生产入库" and selected_product_id:
                            c_rec = db.query(ProductColor).filter(ProductColor.product_id==selected_product_id, ProductColor.color_name==p_var).first()
                            if c_rec: 
                                if c_rec.produced_quantity is None: c_rec.produced_quantity = 0
                                c_rec.produced_quantity += input_qty
                            
                            if target_prod_obj:
                                if target_prod_obj.marketable_quantity is None: target_prod_obj.marketable_quantity = target_prod_obj.total_quantity
                                target_prod_obj.marketable_quantity += input_qty
                                st.toast(f"可销售数量已增加 {input_qty}", icon="📈")

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

    # ================= 4. 库存变动记录 (可编辑 + 删除) =================
    st.subheader("📜 库存变动历史记录")
    
    logs_query = db.query(InventoryLog)
    if selected_product_id:
        logs_query = logs_query.filter(InventoryLog.product_name == p_name)
    
    logs = logs_query.order_by(InventoryLog.id.desc()).limit(100).all() 
    
    if logs:
        log_data = []
        for l in logs:
            desc = l.note or ""
            if l.is_sold: 
                prefix = ""
                if l.change_amount < 0: prefix = f"售出: ¥{l.sale_amount}{l.currency} ({l.platform}) | "
                else: prefix = f"退货: -¥{abs(l.sale_amount)}{l.currency} ({l.platform}) | "
                
                if not desc.startswith("售出:") and not desc.startswith("退货:"):
                    desc = prefix + desc
            elif l.is_other_out and not desc.startswith("其他出库:"):
                desc = f"其他出库: {desc}"
            
            log_data.append({
                "_id": l.id, 
                "日期": l.date, 
                "产品": l.product_name, 
                "款式": l.variant,
                "数量": l.change_amount, 
                "类型": l.reason, 
                "详情": desc
            })
        
        df_logs = pd.DataFrame(log_data)
        
        edited_logs = st.data_editor(
            df_logs,
            key="log_editor",
            use_container_width=True,
            hide_index=True,
            column_config={
                "_id": None,
                "日期": st.column_config.DateColumn(required=True),
                "产品": st.column_config.TextColumn(disabled=True),
                "款式": st.column_config.TextColumn(disabled=True),
                "数量": st.column_config.NumberColumn(disabled=True),
                "类型": st.column_config.TextColumn(disabled=True),
                "详情": st.column_config.TextColumn(label="详情 (可编辑备注)", required=False)
            }
        )
        
        any_change = False
        for index, row in edited_logs.iterrows():
            log_id = row["_id"]
            new_date = row["日期"]
            if isinstance(new_date, pd.Timestamp): new_date = new_date.date()
            new_note = row["详情"]
            
            target_log = db.query(InventoryLog).filter(InventoryLog.id == log_id).first()
            if target_log:
                has_change = False
                if target_log.date != new_date:
                    target_log.date = new_date; has_change = True
                
                if (target_log.note or "") != new_note:
                     target_log.note = new_note
                     has_change = True
                
                if has_change:
                    any_change = True

        if any_change:
            db.commit()
            st.toast("日志已更新", icon="💾")
            st.rerun()

        with st.popover("🗑️ 删除记录 (级联回滚)", use_container_width=True):
            st.warning("⚠️ 删除操作将自动回滚：库存、资产价值、可销售数量。请谨慎操作！")
            
            del_options = {f"{l.date} | {l.product_name} {l.variant} ({l.reason} {l.change_amount}) | {l.note or ''}": l.id for l in logs}
            selected_del_label = st.selectbox("选择要删除的记录", list(del_options.keys()))
            
            if st.button("🔴 确认删除并回滚"):
                log_id = del_options[selected_del_label]
                log_to_del = db.query(InventoryLog).filter(InventoryLog.id == log_id).first()
                
                if log_to_del:
                    try:
                        msg_list = []
                        target_prod = db.query(Product).filter(Product.name == log_to_del.product_name).first()
                        
                        # --- 1. 回滚可销售数量 (Marketable Quantity) ---
                        if target_prod:
                            reasons_affecting_marketable = ["计划入库减少", "额外生产入库"]
                            is_consumable_out = (log_to_del.reason == "出库" and "消耗" in (log_to_del.note or ""))
                            
                            if log_to_del.reason in reasons_affecting_marketable or is_consumable_out:
                                if target_prod.marketable_quantity is None: 
                                    target_prod.marketable_quantity = target_prod.total_quantity
                                
                                old_mq = target_prod.marketable_quantity
                                target_prod.marketable_quantity -= log_to_del.change_amount
                                msg_list.append(f"可售数量 {old_mq} -> {target_prod.marketable_quantity}")
                        else:
                            st.error(f"⚠️ 未找到名为 {log_to_del.product_name} 的产品，跳过可售数量回滚。")

                        # 计算大货资产变动成本
                        unit_cost = get_unit_cost(db, target_prod.id) if target_prod else 0
                        asset_delta = log_to_del.change_amount * unit_cost
                        
                        # --- 2. 根据类型回滚资产和关联单据 ---
                        if log_to_del.reason in ["入库", "额外生产入库", "退货入库"]:
                            update_bi_by_name(db, f"大货资产-{log_to_del.product_name}", -asset_delta)
                            msg_list.append("大货资产已回滚")
                        
                        elif log_to_del.reason == "出库":
                            # A. 回滚大货库存资产 (把扣掉的成本加回来)
                            update_bi_by_name(db, f"大货资产-{log_to_del.product_name}", -asset_delta)
                            msg_list.append("大货资产已回滚")
                            
                            # B. 处理销售关联 (新增了对 PreShippingItem 的检查)
                            if log_to_del.is_sold:
                                # B1. 先尝试找【已完成】的财务流水 (FinanceRecord)
                                target_fin = db.query(FinanceRecord).filter(
                                    FinanceRecord.date == log_to_del.date,
                                    FinanceRecord.amount == log_to_del.sale_amount,
                                    FinanceRecord.category == "销售收入",
                                    FinanceRecord.description.like(f"%{log_to_del.product_name}%")
                                ).first()
                                
                                if target_fin:
                                    # 情况一：已确认收款 -> 回滚现金流 + 删除流水
                                    cash_name = f"流动资金({log_to_del.currency})"
                                    cash_item = db.query(CompanyBalanceItem).filter(
                                        CompanyBalanceItem.name == cash_name
                                    ).first()
                                    
                                    if cash_item:
                                        cash_item.amount -= target_fin.amount
                                        msg_list.append(f"流动资金已扣除 {target_fin.amount}")
                                    
                                    db.delete(target_fin)
                                    msg_list.append("关联销售流水已删除")
                                else:
                                    # 情况二：未确认收款 -> 找【发货单】(PreShippingItem)
                                    # 注意：日志数量是负数，发货单数量是正数，需用 abs()
                                    target_pre = db.query(PreShippingItem).filter(
                                        PreShippingItem.product_name == log_to_del.product_name,
                                        PreShippingItem.variant == log_to_del.variant,
                                        PreShippingItem.quantity == abs(log_to_del.change_amount),
                                        PreShippingItem.pre_sale_amount == log_to_del.sale_amount,
                                        # 这里假设日期一致，如果不一致可能需要放宽条件
                                        PreShippingItem.created_date == log_to_del.date 
                                    ).first()

                                    if target_pre:
                                        # 1. 删除关联的“待结算”挂账资产
                                        if target_pre.related_debt_id:
                                            pending_asset = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_pre.related_debt_id).first()
                                            if pending_asset:
                                                db.delete(pending_asset)
                                                msg_list.append("关联待结算资产已清理")
                                        
                                        # 2. 删除发货单
                                        db.delete(target_pre)
                                        msg_list.append("关联待发货/结算单已删除")
                                    else:
                                        st.warning("⚠️ 未找到完全匹配的【财务流水】或【待结算单】，请手动检查资金账户。")

                            # C. 处理消耗关联
                            if "消耗:" in (log_to_del.note or ""):
                                try:
                                    content_part = log_to_del.note.split("|")[0].replace("消耗:", "").replace("内部消耗:", "").strip()
                                    target_cost = db.query(CostItem).filter(
                                        CostItem.product_id == target_prod.id,
                                        CostItem.actual_cost == 0,
                                        CostItem.item_name.like(f"%{content_part}%")
                                    ).first()
                                    if target_cost:
                                        db.delete(target_cost)
                                        msg_list.append("关联成本记录已删除")
                                except:
                                    pass

                        elif log_to_del.reason in ["预入库", "计划入库减少"]:
                            update_bi_by_name(db, f"预入库大货资产-{log_to_del.product_name}", -asset_delta)
                            update_bi_by_name(db, f"在制资产冲销-{log_to_del.product_name}", asset_delta)
                            msg_list.append("预入库/冲销资产已回滚")

                        db.delete(log_to_del)
                        db.commit()
                        
                        full_msg = " | ".join(msg_list)
                        st.success(f"删除成功！\n{full_msg}")
                        st.rerun()
                        
                    except Exception as e:
                        db.rollback()
                        st.error(f"删除失败: {e}")
    else:
        st.info("暂无记录")
