import streamlit as st
import pandas as pd
from datetime import date
from models import ConsumableItem, ConsumableLog, Product, CostItem, FinanceRecord, CompanyBalanceItem

# === 辅助函数：完全复用财务界面的获取流动资金逻辑 ===
def get_cash_asset_for_other(db, currency):
    """
    与 Finance View 保持一致：
    1. 优先找名字以 '流动资金' 开头的资产项。
    2. 必须匹配币种。
    3. 按 ID 排序取第一个。
    """
    return db.query(CompanyBalanceItem).filter(
        CompanyBalanceItem.name.like("流动资金%"), 
        CompanyBalanceItem.currency == currency,
        CompanyBalanceItem.category == "asset"
    ).order_by(CompanyBalanceItem.id.asc()).first()

def show_other_asset_page(db, exchange_rate):
    st.header("📦 其他资产管理")
    
    # 定义与成本核算一致的分类列表
    COST_CATEGORIES = ["大货材料费", "大货加工费", "物流邮费", "包装费", "设计开发费", "检品发货等人工费", "宣发费", "其他成本"]
    
    # === 1. 库存操作区 ===
    with st.container(border=True):
        st.markdown("#### ⚡ 快速库存操作")
        
        all_items = db.query(ConsumableItem).filter(ConsumableItem.remaining_qty > 0).all()
        item_names = [i.name for i in all_items]
        
        # --- 第一行：日期 | 选择资产 | 操作类型 ---
        c_date, c_item, c_type = st.columns([1, 1.5, 1.2])
        
        # 默认为今天，但允许用户修改，用于补录历史数据
        op_date = c_date.date_input("📅 日期", value=date.today())
        selected_name = c_item.selectbox("📦 选择项目", item_names or ["暂无库存"])
        op_type = c_type.radio("⚙️ 操作类型", ["出库 (消耗/销售) -", "入库 (补货) +"], horizontal=True)
        
        # 数量输入 (通用)
        c_qty, c_space = st.columns([1, 3.2])
        op_qty = c_qty.number_input("🔢 操作数量", min_value=0.01, step=1.0, value=1.0, format="%.2f")
        
        # 初始化变量
        target_product_id = None
        target_cost_category = "包装费"
        is_link_product = False
        is_sale_mode = False
        
        # 销售相关变量 (对应财务界面的5要素)
        sale_content = ""      # 收入内容
        sale_source = ""       # 收入来源
        sale_amount = 0.0      # 销售总额
        sale_currency = "CNY"  # 币种
        sale_remark = ""       # 备注
        
        # === 核心逻辑分支 ===
        if "出库" in op_type:
            st.markdown("---")
            out_mode = st.radio("📤 出库目的", ["🏢 内部消耗 (计入成本)", "💰 对外销售 (计入收入)"], horizontal=True)
            
            if "对外销售" in out_mode:
                is_sale_mode = True
                st.caption("📝 请填写财务信息 (将自动生成【销售收入】流水并存入流动资金)")
                
                # 布局：内容(2) | 来源(1.5) | 金额(1) | 币种(1)
                r1_c1, r1_c2, r1_c3, r1_c4 = st.columns([2, 1.5, 1, 1])
                
                # 1. 收入内容 (默认为：售出 {资产名})
                default_content = f"售出 {selected_name}" if selected_name else ""
                sale_content = r1_c1.text_input("收入内容", value=default_content, placeholder="如：闲鱼出物")
                
                # 2. 收入来源
                sale_source = r1_c2.text_input("收入来源", placeholder="如：闲鱼/线下")
                
                # 3. 销售总额
                sale_amount = r1_c3.number_input("销售总额", min_value=0.0, step=10.0, format="%.2f")
                
                # 4. 币种
                sale_currency = r1_c4.selectbox("币种", ["CNY", "JPY"])
                
                # 5. 备注
                sale_remark = st.text_input("备注", placeholder="选填，将记录在流水备注中")
                
            else:
                # === 内部消耗逻辑 ===
                is_sale_mode = False
                lc1, lc2, lc3 = st.columns([0.8, 1.6, 1.6])
                is_link_product = lc1.checkbox("🔗 计入商品成本", help="勾选后，消耗金额将分摊到指定商品的成本中")
                # 内部消耗也需要备注
                sale_remark = st.text_input("消耗备注", placeholder="如：打包使用") 
                
                if is_link_product:
                    products = db.query(Product).all()
                    prod_opts = {p.id: p.name for p in products}
                    if prod_opts:
                        target_product_id = lc2.selectbox("归属商品", options=list(prod_opts.keys()), format_func=lambda x: prod_opts[x], label_visibility="collapsed")
                        target_cost_category = lc3.selectbox("成本分类", options=COST_CATEGORIES, index=3, label_visibility="collapsed")
        
        else:
            # === 入库/补货逻辑 ===
            sale_remark = st.text_input("补货备注", placeholder="如：淘宝补货")

        # --- 提交按钮 ---
        st.write("") 
        if st.button("🚀 提交更新", type="primary", use_container_width=True):
            if selected_name and selected_name != "暂无库存":
                item = db.query(ConsumableItem).filter(ConsumableItem.name == selected_name).first()
                if item:
                    # 确定库存变动方向
                    sign = -1 if "出库" in op_type else 1
                    qty_delta = op_qty * sign
                    
                    # 校验库存
                    if qty_delta < 0 and item.remaining_qty < op_qty:
                        st.error("库存不足！")
                        st.stop()
                    
                    # 1. 更新库存数量
                    item.remaining_qty += qty_delta
                    
                    # 2. 计算库存价值变动 (用于日志)
                    curr = getattr(item, "currency", "CNY")
                    rate = exchange_rate if curr == "JPY" else 1.0
                    val_change_cny = qty_delta * item.unit_price * rate
                    
                    link_msg = ""
                    log_note = "" # 初始化
                    
                    # =================================================
                    # === 分支 A: 销售模式 (完全对齐财务流水逻辑) ===
                    # =================================================
                    if is_sale_mode and "出库" in op_type:
                        if sale_amount > 0:
                            if not sale_content:
                                st.error("请输入收入内容")
                                st.stop()

                            # --- A1. 记录 FinanceRecord (生成流水) ---
                            # 拼凑备注: 来源 + 备注
                            note_detail = f"来源: {sale_source}" if sale_source else ""
                            if sale_remark: note_detail += f" | {sale_remark}"
                            
                            # 使用 op_date (顶部选择器的时间)
                            fin_rec = FinanceRecord(
                                date=op_date,
                                amount=sale_amount,      # 收入为正
                                currency=sale_currency,
                                category="销售收入",      # 对齐财务界面的收入分类
                                description=f"{sale_content} [{note_detail}]" # 格式对齐：内容 [详情]
                            )
                            db.add(fin_rec)
                            db.flush() # 获取ID以供关联
                            
                            # --- A2. 增加流动资金 ---
                            target_cash_asset = get_cash_asset_for_other(db, sale_currency)
                            
                            if not target_cash_asset:
                                target_cash_asset = CompanyBalanceItem(
                                    category="asset",
                                    name=f"流动资金({sale_currency})",
                                    amount=0.0,
                                    currency=sale_currency
                                )
                                db.add(target_cash_asset)
                            
                            target_cash_asset.amount += sale_amount
                            
                            link_msg = f" | 💰 已入账 {sale_amount}{sale_currency} 至流动资金"
                            
                            # 日志备注
                            log_note = f"对外销售: {sale_content} | 金额:{sale_amount}{sale_currency}"
                        else:
                            st.warning("⚠️ 销售金额为0，仅扣减库存，未生成流水")
                            log_note = f"对外销售 (无金额): {sale_content}"

                    # === 分支 B: 内部消耗/计入成本 ===
                    elif is_link_product and target_product_id and "出库" in op_type:
                        cost_amount = abs(val_change_cny)
                        new_cost = CostItem(
                            product_id=target_product_id,
                            item_name=f"资产分摊: {item.name}",
                            actual_cost=cost_amount,
                            supplier="自有库存",
                            category=target_cost_category,
                            unit_price=cost_amount / op_qty if op_qty else 0,
                            quantity=op_qty,
                            unit="个",
                            remarks=f"从资产库出库: {sale_remark}"
                        )
                        db.add(new_cost)
                        p_obj = db.query(Product).filter(Product.id == target_product_id).first()
                        p_name_str = p_obj.name if p_obj else "未知商品"
                        link_msg = f" | 📉 已计入【{p_name_str}】成本 ¥{cost_amount:.2f}"
                        log_note = f"内部消耗: {sale_remark}"
                    else:
                        log_note = f"库存操作: {sale_remark}"

                    # 3. 记录库存日志 (ConsumableLog)
                    new_log = ConsumableLog(
                        item_name=item.name,
                        change_qty=qty_delta,
                        value_cny=val_change_cny, 
                        note=log_note,
                        date=op_date
                    )
                    db.add(new_log)
                    
                    db.commit()
                    
                    msg_icon = "💰" if is_sale_mode else ("📉" if qty_delta < 0 else "📈")
                    st.toast(f"更新成功：{item.name} {qty_delta}{link_msg}", icon=msg_icon)
                    st.rerun()

    st.divider()

    # === 2. 资产列表展示 (DataEditor) ===
    items = db.query(ConsumableItem).all()
    
    if items:
        data_list = []
        # 初始化双币种总值 (互斥统计)
        total_remain_val_cny = 0.0
        total_remain_val_jpy = 0.0

        for i in items:
            curr = getattr(i, "currency", "CNY") 
            # 注意：此处不再需要 exchange_rate 进行列表内的折算逻辑，因为要分开显示
            
            # 基础数值
            qty = i.remaining_qty
            unit_price = i.unit_price
            
            # 价值计算
            val_origin = unit_price * qty
            
            # 【修改点】：严格互斥显示逻辑
            row_cny_display = None
            row_jpy_display = None
            
            if curr == "JPY":
                row_jpy_display = val_origin
                # 过滤 0 资产 (JPY)
                if qty <= 0.001 or row_jpy_display <= 0.001:
                    continue
                # 只计入 JPY 总计
                total_remain_val_jpy += val_origin
                
            else: # CNY
                row_cny_display = val_origin
                # 过滤 0 资产 (CNY)
                if qty <= 0.001 or row_cny_display <= 0.001:
                    continue
                # 只计入 CNY 总计
                total_remain_val_cny += val_origin
            
            data_list.append({
                "ID": i.id,
                "项目": i.name,
                "分类": i.category,
                "币种": curr,
                "单价 (原币)": unit_price,
                "剩余数量": qty,
                "剩余价值 (CNY)": row_cny_display, # JPY资产此列为空
                "剩余价值 (JPY)": row_jpy_display, # CNY资产此列为空
                "店铺": i.shop_name,
                "备注": i.remarks if i.remarks else ""
            })
            
        df = pd.DataFrame(data_list)
        
        # 计算综合总值
        grand_total_cny = total_remain_val_cny + (total_remain_val_jpy * exchange_rate)
        
        # 显示统计条 (增加折合总计)
        st.markdown(
            f"**当前资产总值:** "
            f"CNY <span style='color:green'>¥ {total_remain_val_cny:,.2f}</span> | "
            f"JPY <span style='color:red'>¥ {total_remain_val_jpy:,.0f}</span>"
            f" &nbsp;&nbsp;➡️&nbsp;&nbsp; **折算CNY总计: ¥ {grand_total_cny:,.2f}**", 
            unsafe_allow_html=True
        )
        if not df.empty:
            edited_df = st.data_editor(
                df, key="other_asset_editor", use_container_width=True, hide_index=True,
                disabled=["ID", "项目", "分类", "剩余价值 (CNY)", "剩余价值 (JPY)"],
                column_config={
                    "ID": None,
                    "币种": st.column_config.SelectboxColumn(options=["CNY", "JPY"], required=True),
                    "单价 (原币)": st.column_config.NumberColumn(format="%.2f", required=True),
                    "剩余价值 (CNY)": st.column_config.NumberColumn(format="¥ %.2f"),
                    "剩余价值 (JPY)": st.column_config.NumberColumn(format="¥ %.0f"),
                    "剩余数量": st.column_config.NumberColumn(format="%.2f")
                }
            )
            
            # 捕获修改
            if st.session_state.get("other_asset_editor") and st.session_state["other_asset_editor"].get("edited_rows"):
                changes = st.session_state["other_asset_editor"]["edited_rows"]
                has_change = False
                for index, diff in changes.items():
                    original_row = df.iloc[int(index)]
                    item_id = int(original_row["ID"])
                    item_obj = db.query(ConsumableItem).filter(ConsumableItem.id == item_id).first()
                    if item_obj:
                        # 支持修改币种和单价，以便用户修正历史数据
                        if "币种" in diff: item_obj.currency = diff["币种"]; has_change = True
                        if "单价 (原币)" in diff: item_obj.unit_price = float(diff["单价 (原币)"]); has_change = True
                        
                        if "店铺" in diff: item_obj.shop_name = diff["店铺"]; has_change = True
                        if "备注" in diff: item_obj.remarks = diff["备注"]; has_change = True
                        if "剩余数量" in diff: item_obj.remaining_qty = float(diff["剩余数量"]); has_change = True
                
                if has_change:
                    db.commit()
                    st.toast("信息已更新", icon="💾")
                    st.rerun()
        else:
            st.info("当前无有效库存资产 (数量或价值为0的项目已隐藏)。")

    else:
        st.info("暂无其他资产数据。")

    # === 3. 操作记录 (支持编辑日期) ===
    st.divider()
    st.subheader("📜 操作记录")
    
    logs = db.query(ConsumableLog).order_by(ConsumableLog.id.desc()).all()
    
    if logs:
        # 构造 DataFrame
        log_data = [{
            "_id": l.id,
            "日期": l.date, 
            "名称": l.item_name, 
            "变动": l.change_qty, 
            "详情": l.note
        } for l in logs]
        df_logs = pd.DataFrame(log_data)
        
        # 计算表格高度 (至少 300px，最多 800px)
        num_rows = len(df_logs)
        calc_height = (num_rows + 1) * 35 
        if calc_height > 800: calc_height = 800
        if calc_height < 300: calc_height = 300
        
        edited_logs = st.data_editor(
            df_logs, 
            use_container_width=True, 
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
        
        # 日期修改逻辑
        if st.session_state.get("cons_log_editor") and st.session_state["cons_log_editor"].get("edited_rows"):
            log_changes = st.session_state["cons_log_editor"]["edited_rows"]
            has_log_change = False
            
            for index, diff in log_changes.items():
                original_row = df_logs.iloc[int(index)]
                log_id = int(original_row["_id"])
                log_obj = db.query(ConsumableLog).filter(ConsumableLog.id == log_id).first()
                
                if log_obj:
                    # 检查是否修改了日期
                    if "日期" in diff:
                        new_date_str = diff["日期"]
                        if isinstance(new_date_str, str):
                            new_date = date.fromisoformat(new_date_str)
                        else:
                            new_date = new_date_str
                            
                        log_obj.date = new_date
                        has_log_change = True

            if has_log_change:
                db.commit()
                st.toast("日期已更新", icon="📅")
                st.rerun()
                
    else:
        st.caption("暂无操作记录")