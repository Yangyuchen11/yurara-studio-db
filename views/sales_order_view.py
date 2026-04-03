import streamlit as st
import pandas as pd
from datetime import date
from services.sales_order_service import SalesOrderService
from cache_manager import sync_all_caches
from models import Product, CompanyBalanceItem
from constants import OrderStatus, PLATFORM_CODES

# ------------------ 🚀 性能优化：独立数据层缓存 ------------------

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_order_stats(product_filter, test_mode_flag):
    db_cache = st.session_state.get_dynamic_session()
    try:
        service = SalesOrderService(db_cache)
        return service.get_order_statistics(product_name=product_filter)
    finally:
        db_cache.close()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_orders_df(status_filter, product_filter, test_mode_flag):
    db_cache = st.session_state.get_dynamic_session()
    try:
        service = SalesOrderService(db_cache)
        orders = service.get_all_orders(status=status_filter, product_name=product_filter, limit=100)

        data_list = []
        for o in orders:
            item_count = len(o.items)
            items_summary = ", ".join([f"{i.product_name}-{i.variant}×{i.quantity}" for i in o.items[:2]])
            if item_count > 2:
                items_summary += f" 等{item_count}项"

            total_refunded = sum([r.refund_amount for r in o.refunds])
            
            status_display = o.status
            if o.status == OrderStatus.PENDING: status_display = "📦 待发货"
            elif o.status == OrderStatus.SHIPPED: status_display = "🚚 已发货"
            elif o.status == OrderStatus.COMPLETED: status_display = "✅ 完成"
            elif o.status == OrderStatus.AFTER_SALES: status_display = "🔧 售后"

            data_list.append({
                "勾选": False,
                "ID": o.id,
                "订单号": o.order_no,
                "状态": status_display,
                "商品": items_summary,
                "金额": float(o.total_amount),
                "已退款": float(total_refunded),
                "币种": o.currency,
                "平台": o.platform,
                "日期": str(o.created_date)
            })
        return pd.DataFrame(data_list)
    finally:
        db_cache.close()

# ------------------ 主页面逻辑 ------------------

def show_sales_order_page(db):
    st.header("🛒 销售订单管理")

    test_mode = st.session_state.get("test_mode", False)
    service = SalesOrderService(db)
    all_products = db.query(Product).all()

    # ================= 0. 数据筛选 =================
    product_options = ["全部商品"] + [p.name for p in all_products]
    selected_product = st.selectbox(
        "🔍 选择商品以筛选下方表格与统计数据",
        product_options,
        key="sales_order_product_filter"
    )
    product_filter = None if selected_product == "全部商品" else selected_product
    st.divider()

    # ================= 1. 订单统计概览 (秒开) =================
    stats = get_cached_order_stats(product_filter, test_mode)
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("总订单数", stats["total"])
        c2.metric("待发货", stats["pending"], delta_color="off")
        c3.metric("已发货", stats["shipped"], delta_color="off")
        c4.metric("已完成", stats["completed"], delta_color="off")
        c5.metric("售后中", stats["after_sales"], delta_color="inverse")
    st.divider()

    # ================= 2. 创建订单 (购物车模式) =================
    # 初始化购物车
    if "order_cart" not in st.session_state:
        st.session_state.order_cart = []

    with st.expander("➕ 创建新订单", expanded=False):
        st.subheader("1. 订单基础信息")
        col_r1_1, col_r1_2 = st.columns(2)
        order_no = col_r1_1.text_input("订单号", placeholder="输入订单号（必填）", key="order_no_input")
        order_date = col_r1_2.date_input("订单日期", value=date.today())

        col_r2_1, col_r2_2, col_r2_3 = st.columns([1, 1, 2])
        platform = col_r2_1.selectbox("销售平台", list(PLATFORM_CODES.values()))
        currency = col_r2_2.selectbox("币种", ["CNY", "JPY"])
        
        # --- 获取并筛选现金账户 ---
        cash_items = db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.category == "asset",
            CompanyBalanceItem.asset_type == "现金",
            CompanyBalanceItem.currency == currency
        ).all()
        cash_account_names = [item.name for item in cash_items]

        if platform == "微店": default_acc_name = "流动资金-微店账户"
        elif platform == "Booth": default_acc_name = "流动资金-booth账户"
        elif currency == "JPY": default_acc_name = "流动资金-日元临时账户"
        else: default_acc_name = "流动资金-支付宝账户"

        if default_acc_name not in cash_account_names:
            cash_account_names.insert(0, default_acc_name) 
        default_idx = cash_account_names.index(default_acc_name)

        target_account_name = col_r2_3.selectbox("收款现金账户", cash_account_names, index=default_idx)

        st.divider()
        
        # --- 购物车操作区 ---
        st.subheader("2. 订单商品列表 (添加商品)")
        
        c_p, c_v, c_q, c_b = st.columns([2, 1.5, 1, 1], vertical_alignment="bottom")
        sel_p_name = c_p.selectbox("选择商品", [p.name for p in all_products], key="cart_p")
        
        # 联动获取款式
        sel_p_obj = next((p for p in all_products if p.name == sel_p_name), None) if sel_p_name else None
        v_options = [c.color_name for c in sel_p_obj.colors] if sel_p_obj else []
        
        sel_v_name = c_v.selectbox("选择款式", v_options, key="cart_v")
        sel_qty = c_q.number_input("数量", min_value=1, step=1, value=1, key="cart_q")
        
        if c_b.button("➕ 加入订单", type="primary", use_container_width=True):
            if sel_p_name and sel_v_name:
                # 检查订单购物车中是否已有该商品+款式组合，有则追加数量
                found = False
                for item in st.session_state.order_cart:
                    if item["product_name"] == sel_p_name and item["variant"] == sel_v_name:
                        item["quantity"] += sel_qty
                        found = True
                        break
                if not found:
                    st.session_state.order_cart.append({
                        "product_name": sel_p_name,
                        "variant": sel_v_name,
                        "quantity": sel_qty
                    })
                st.rerun()

        # --- 订单展示与编辑区 ---
        if st.session_state.order_cart:
            st.markdown("**当前已加入的商品 (支持直接修改数量或删除空行):**")
            cart_df = pd.DataFrame(st.session_state.order_cart)
            edited_cart = st.data_editor(
                cart_df,
                width="stretch",
                num_rows="dynamic", # 允许用户选中左侧复选框按 Delete 删除整行
                key="cart_editor",
                column_config={
                    "product_name": st.column_config.TextColumn("商品名称", disabled=True),
                    "variant": st.column_config.TextColumn("款式", disabled=True),
                    "quantity": st.column_config.NumberColumn("数量", min_value=1, step=1)
                }
            )
            
            # 数据清洗：过滤掉被用户删除空置的行
            cleaned_cart = []
            for record in edited_cart.to_dict('records'):
                if pd.notna(record.get("product_name")) and str(record.get("product_name")).strip() != "":
                    cleaned_cart.append(record)
            st.session_state.order_cart = cleaned_cart
        else:
            st.info("🛒 订单为空，请在上方选择商品并加入。")

        st.divider()

        # --- 结算区 ---
        st.subheader("3. 结算信息")
        col_r3_1, col_r3_2 = st.columns([1, 2], vertical_alignment="bottom")
        total_price = col_r3_1.number_input("订单总价 (含邮费)", min_value=0.0, step=10.0, value=0.0, format="%.2f", key="order_total_price")
        deduct_fee = col_r3_2.checkbox("扣除平台手续费", value=True)
        notes = st.text_input("订单备注", placeholder="如：客户名称、特殊要求等", key="order_notes_input")
        
        # 实时计算结算数据
        total_quantity = sum(item["quantity"] for item in st.session_state.order_cart) if st.session_state.order_cart else 0
        gross_price = total_price
        fee = 0.0
        shipping_and_other = 0.0
        
        # ✨ 针对 Booth 的精准计费与邮费剥离
        if platform == "Booth" and st.session_state.order_cart:
            preset_item_total = 0.0
            price_missing = False # ✨ 标记是否有商品未找到定价
            for item in st.session_state.order_cart:
                p_obj = next((p for p in all_products if p.name == item["product_name"]), None)
                unit_p = 0.0
                if p_obj:
                    target_c = next((c for c in p_obj.colors if c.color_name == item["variant"]), None)
                    if target_c:
                        # ✨ 修复点：统一转为小写进行匹配，防止大小写问题导致找不到金额
                        target_price = next((pr.price for pr in target_c.prices if pr.platform and pr.platform.lower() == "booth"), 0.0)
                        unit_p = target_price
                
                if unit_p <= 0:
                    price_missing = True
                preset_item_total += unit_p * item["quantity"]
            
            # ✨ 安全防御：如果没找到商品定价，禁止强行剥离邮费
            if price_missing or preset_item_total <= 0:
                st.warning("⚠️ 警告：购物车中包含未在【商品管理】中设置 Booth 定价的商品！系统无法剥离邮费，本次计算将暂不扣除邮费。")
                shipping_and_other = 0.0
            else:
                # 抽出包含的邮费和打赏（总价 - 设定的商品总价）
                shipping_and_other = max(0.0, gross_price - preset_item_total)

        if deduct_fee:
            if platform == "微店": 
                fee = gross_price * 0.006
            elif platform == "Booth": 
                # ✨ 根据 Booth 官方最新费率：5.6% + 45 JPY (总价为基数)
                exchange_rate = st.session_state.get("global_rate_input", 4.8) / 100.0
                base_fixed_fee = 45 if currency == "JPY" else (45 * exchange_rate)
                fee = gross_price * 0.056 + base_fixed_fee
            
        # 核心：真正的商品净收必须剥离邮费与手续费
        net_price = gross_price - fee - shipping_and_other

        col_qty_display, col_price_display, col_spacer = st.columns([1, 1.8, 1.2])
        col_qty_display.markdown(f"**总数量: {total_quantity} 件**")

        if total_quantity > 0 and gross_price > 0:
            unit_price = net_price / total_quantity
            fee_str = f" (预估手续费: {fee:.2f})" if fee > 0 else ""
            ship_str = f" (含邮费: {shipping_and_other:.2f})" if shipping_and_other > 0 else ""
            col_price_display.markdown(f"**商品净收: {net_price:.2f} {currency} | 净单价: {unit_price:.2f} {currency}/件**<br><span style='font-size: 0.85em; color: gray;'>{fee_str}{ship_str}</span>", unsafe_allow_html=True)
        else:
            col_price_display.markdown(f"**平均净单价: - {currency}/件**")

        if st.button("✅ 提交订单", type="primary", width="stretch"):
            if not order_no or not order_no.strip(): st.error("❌ 请输入订单号")
            elif not st.session_state.order_cart: st.error("❌ 请至少加入一件商品")
            elif total_quantity == 0: st.error("❌ 商品总数量不能为 0")
            elif gross_price <= 0: st.error("❌ 请输入订单总价")
            elif net_price < 0: st.error("❌ 扣除手续费和邮费后的商品净额小于 0，请检查总价或商品定价设置")
            else:
                items_data = []
                final_unit_price = net_price / total_quantity
                for item in st.session_state.order_cart:
                    if item["quantity"] > 0:
                        items_data.append({
                            "product_name": item["product_name"],
                            "variant": item["variant"],
                            "quantity": item["quantity"],
                            "unit_price": final_unit_price,
                            "subtotal": item["quantity"] * final_unit_price
                        })
                
                order, error = service.create_order(
                    items_data=items_data, platform=platform, currency=currency, 
                    notes=notes, order_date=order_date, order_no=order_no.strip(),
                    target_account_name=target_account_name
                )
                if error:
                    st.error(f"创建失败: {error}")
                else:
                    st.success(f"✅ 订单 {order.order_no} 创建成功！(商品入账金额: {net_price:.2f} {currency})")
                    st.session_state.order_cart = []
                    sync_all_caches() 
                    st.rerun()

    # ================= 2.5 批量导入订单 =================
    with st.expander("📥 批量导入订单 (Excel)", expanded=False):
        st.markdown("""
        **表格格式要求**：请上传包含以下 7 列的 Excel 文件（列名必须完全一致）：
        `订单号` | `商品名` | `商品型号` | `数量` | `销售平台` | `订单总额` | `币种`
        
        💡 **多款式说明**：**一个订单只能占一行，严禁出现重复订单号**。如果同一个订单内有多个不同颜色/型号，请在`商品型号`和`数量`列用**英文分号 (;)** 隔开。
        例如：型号填 `粉色;蓝色`，数量填 `1;2`，代表买了一件粉色和两件蓝色。
        """)
        
        if "uploader_key" not in st.session_state:
            st.session_state.uploader_key = 0
            
        uploaded_file = st.file_uploader(
            "上传 Excel 文件", 
            type=["xlsx", "xls"], 
            key=f"order_excel_uploader_{st.session_state.uploader_key}"
        )
        
        if uploaded_file is not None:
            try:
                df_import = pd.read_excel(uploaded_file)
                parsed_orders, errors = service.validate_and_parse_import_data(df_import)
                
                if errors:
                    st.error("❌ 数据校验失败，请修复 Excel 中的以下问题后重新上传：")
                    for err in errors:
                        st.write(f"- {err}")
                elif parsed_orders:
                    st.success(f"✅ 数据校验通过！共识别出 {len(parsed_orders)} 个有效订单。预览如下：")
                    
                    preview_data = []
                    for po in parsed_orders:
                        items_str = ", ".join([f"{i['product_name']}-{i['variant']} ×{i['quantity']}" for i in po["items"]])
                        preview_data.append({
                            "订单号": po["order_no"],
                            "平台": po["platform"],
                            "收款目标账户": po["target_account"], # ✨ 新增预览展示
                            "币种": po["currency"],
                            "总数量": po["total_qty"],
                            "原总价": po["gross_price"],
                            "预估手续费": po["fee"],
                            "实际净入账": po["net_price"],
                            "商品明细": items_str
                        })
                        
                    st.dataframe(
                        pd.DataFrame(preview_data), 
                        width="stretch",
                        column_config={
                            "原总价": st.column_config.NumberColumn(format="%.2f"),
                            "预估手续费": st.column_config.NumberColumn(format="%.2f"),
                            "实际净入账": st.column_config.NumberColumn(format="%.2f")
                        }
                    )
                    
                    if st.button("🚀 确认无误，开始导入订单", type="primary"):
                        with st.spinner("正在逐个生成订单并入账..."):
                            count = service.batch_create_orders(parsed_orders)
                            st.toast(f"导入完成！成功生成 {count} 个订单。", icon="✅")
                            sync_all_caches() 
                            st.session_state.uploader_key += 1
                            st.rerun()
                            
            except Exception as e:
                st.error(f"读取或处理 Excel 文件失败: {e}")
                st.caption("提示：请确保安装了 openpyxl 库。")

    st.divider()

    # ================= 3. 订单列表 =================
    st.subheader("📋 订单列表")

    tab_all, tab_pending, tab_shipped, tab_completed, tab_after = st.tabs([
        "全部", "待发货", "已发货", "已完成", "售后中"
    ])

    def render_order_list(status_filter=None):
        status_key_suffix = str(status_filter) if status_filter else "all"
        editor_key = f"editor_{status_key_suffix}"
        select_all_key = f"select_all_flag_{status_key_suffix}"

        if select_all_key not in st.session_state:
            st.session_state[select_all_key] = False

        with st.spinner("加载数据中..."):
            df = get_cached_orders_df(status_filter, product_filter, test_mode).copy()

        if df.empty:
            st.info("暂无订单")
            return

        c_sel1, c_sel2, _ = st.columns([1, 1, 6])
        
        if c_sel1.button("☑️ 全选", key=f"btn_sel_all_{status_key_suffix}", width="stretch"):
            st.session_state[select_all_key] = True
            if editor_key in st.session_state: 
                del st.session_state[editor_key]
            st.rerun()
            
        if c_sel2.button("☐ 取消全选", key=f"btn_desel_all_{status_key_suffix}", width="stretch"):
            st.session_state[select_all_key] = False
            if editor_key in st.session_state: 
                del st.session_state[editor_key]
            st.rerun()

        is_all_selected = st.session_state[select_all_key]
        df["勾选"] = is_all_selected

        st.markdown("**👇 勾选下方订单，点击操作栏按钮执行相应操作**")

        edited_df = st.data_editor(
            df,
            width="stretch",
            hide_index=True,
            disabled=["订单号", "状态", "商品", "金额", "已退款", "币种", "平台", "日期"], 
            column_config={
                "勾选": st.column_config.CheckboxColumn("选择", default=False),
                "ID": None,
                "金额": st.column_config.NumberColumn(format="%.2f"),
                "已退款": st.column_config.NumberColumn(format="%.2f")
            },
            key=editor_key
        )

        selected_rows = edited_df[edited_df["勾选"] == True]
        selected_ids = selected_rows["ID"].tolist()
        selected_count = len(selected_ids)

        all_pending = selected_count > 0 and all(s == "📦 待发货" for s in selected_rows["状态"])
        all_shipped = selected_count > 0 and all(s == "🚚 已发货" for s in selected_rows["状态"])
        
        is_single_select = (selected_count == 1)
        target_order_id = selected_ids[0] if is_single_select else None
        
        can_refund = False
        if is_single_select:
            target_status = selected_rows.iloc[0]["状态"]
            can_refund = target_status in ["🚚 已发货", "✅ 完成", "🔧 售后"]

        st.divider()
        
        err_key = f"order_op_errors_{status_key_suffix}"
        if err_key in st.session_state:
            for err in st.session_state[err_key]:
                st.error(err, icon="🚨")
            del st.session_state[err_key]

        action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)
        
        if action_col1.button(f"📦 发货 ({selected_count})", key=f"btn_ship_{status_key_suffix}", type="primary", width="stretch", disabled=not all_pending, help="仅当选中的所有订单均为【待发货】时可用"):
            success_count = 0
            err_list = [] 
            for o_id in selected_ids:
                try:
                    service.ship_order(o_id)
                    success_count += 1
                except Exception as e:
                    err_list.append(f"订单 {o_id} 发货失败: {e}")
                    
            if success_count > 0:
                st.toast(f"✅ 成功发货 {success_count} 个订单", icon="📦")
                if editor_key in st.session_state: del st.session_state[editor_key]
                st.session_state[select_all_key] = False
                sync_all_caches() 
                
            if err_list:
                st.session_state[err_key] = err_list
                
            if success_count > 0 or err_list:
                st.rerun()

        if action_col2.button(f"✅ 完成 ({selected_count})", key=f"btn_comp_{status_key_suffix}", type="primary", width="stretch", disabled=not all_shipped, help="仅当选中的所有订单均为【已发货】时可用"):
            success_count = 0
            err_list = [] 
            for o_id in selected_ids:
                try:
                    service.complete_order(o_id)
                    success_count += 1
                except Exception as e:
                    err_list.append(f"订单 {o_id} 完成失败: {e}")
                    
            if success_count > 0:
                st.toast(f"✅ 成功完成 {success_count} 个订单", icon="💰")
                if editor_key in st.session_state: del st.session_state[editor_key]
                st.session_state[select_all_key] = False
                sync_all_caches()
                
            if err_list:
                st.session_state[err_key] = err_list

            if success_count > 0 or err_list:
                st.rerun()

        if action_col3.button("🔧 售后处理", key=f"btn_after_{status_key_suffix}", width="stretch", disabled=not can_refund, help="仅限对单个【已发货/完成/售后】订单操作"):
            st.session_state[f"show_refund_form_{target_order_id}"] = True
            st.session_state.pop(f"show_detail_{target_order_id}", None)

        if action_col4.button("📄 查看详情", key=f"btn_det_{status_key_suffix}", width="stretch", disabled=not is_single_select, help="仅限单选时查看详情"):
            st.session_state[f"show_detail_{target_order_id}"] = True
            st.session_state.pop(f"show_refund_form_{target_order_id}", None)

        if action_col5.button("🗑️ 删除订单", key=f"btn_del_{status_key_suffix}", width="stretch", disabled=not is_single_select, help="仅限单选时删除订单"):
            st.session_state[f"show_delete_confirm_{target_order_id}"] = True

        if target_order_id:
            o = service.get_order_by_id(target_order_id)
            
            if st.session_state.get(f"show_delete_confirm_{target_order_id}"):
                with st.container(border=True):
                    st.warning(f"⚠️ 确认删除订单 **{o.order_no}** 吗？")
                    st.markdown("**此操作将：**\n- 完整回滚订单数据\n- 回滚库存、资产、财务流水\n- 删除所有售后记录\n- **此操作不可恢复！**")
                    cd1, cd2 = st.columns([1, 4])
                    if cd1.button("🔴 确认删除", key=f"btn_conf_del_{target_order_id}", type="primary"):
                        try:
                            msg = service.delete_order(target_order_id)
                            st.toast(msg, icon="✅")
                            st.session_state.pop(f"show_delete_confirm_{target_order_id}", None)
                            if editor_key in st.session_state: del st.session_state[editor_key]
                            st.session_state[select_all_key] = False
                            sync_all_caches()
                            st.rerun()
                        except Exception as e:
                            st.error(f"删除失败: {e}")
                    if cd2.button("取消", key=f"btn_cancel_del_{target_order_id}"):
                        st.session_state.pop(f"show_delete_confirm_{target_order_id}", None)
                        st.rerun()

            if st.session_state.get(f"show_detail_{target_order_id}"):
                with st.container(border=True):
                    st.markdown(f"**订单明细 - {o.order_no}**")
                    col_d1, col_d2, col_d3 = st.columns(3)
                    col_d1.write(f"**状态:** {o.status}")
                    col_d2.write(f"**平台:** {o.platform}")
                    col_d3.write(f"**币种:** {o.currency}")

                    col_d4, col_d5, col_d6 = st.columns(3)
                    col_d4.write(f"**创建日期:** {o.created_date}")
                    col_d5.write(f"**发货日期:** {o.shipped_date or '未发货'}")
                    col_d6.write(f"**完成日期:** {o.completed_date or '未完成'}")

                    # ✨ 详情页展示收款目标账户
                    st.write(f"**设定收款账户:** {o.target_account_name or '系统默认'}")
                    st.write(f"**备注:** {o.notes or '无'}")

                    st.divider()
                    st.markdown("**商品明细:**")
                    items_detail = [{"商品": i.product_name, "款式": i.variant, "数量": i.quantity, "单价": i.unit_price, "小计": i.subtotal} for i in o.items]
                    st.dataframe(pd.DataFrame(items_detail), width="stretch", hide_index=True, column_config={"单价": st.column_config.NumberColumn(format="%.2f"), "小计": st.column_config.NumberColumn(format="%.2f")})
                    
                    st.write(f"**订单总额: {o.total_amount:.2f} {o.currency}**")

            if st.session_state.get(f"show_refund_form_{target_order_id}"):
                with st.container(border=True):
                    st.markdown(f"**售后管理 - {o.order_no}**")

                    if o.refunds:
                        st.markdown("**已有售后记录:**")
                        for r in o.refunds:
                            with st.container(border=True):
                                col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns([1.5, 2, 1, 1, 1.5])
                                col_r1.write(f"**日期:** {r.refund_date}")
                                col_r2.write(f"**原因:** {r.refund_reason}")
                                col_r3.write(f"**金额:** {r.refund_amount:.2f}")
                                col_r4.write(f"**退货:** {'是' if r.is_returned else '否'}")

                                with col_r5:
                                    btn_c1, btn_c2 = st.columns(2)
                                    if btn_c1.button("✏️", key=f"edit_refund_{r.id}", help="修改", width="stretch"):
                                        st.session_state[f"is_editing_refund_{r.id}"] = True
                                        st.rerun()
                                    if btn_c2.button("🗑️", key=f"del_refund_{r.id}", help="删除", width="stretch"):
                                        try:
                                            msg = service.delete_refund(r.id)
                                            st.toast(msg, icon="✅")
                                            sync_all_caches()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(str(e))

                                if st.session_state.get(f"is_editing_refund_{r.id}"):
                                    with st.form(f"edit_refund_form_{r.id}"):
                                        st.markdown("**修改售后记录:**")
                                        new_amount = st.number_input("售后金额", value=float(r.refund_amount), min_value=0.0, step=10.0, format="%.2f")
                                        new_reason = st.text_input("售后原因", value=r.refund_reason)

                                        col_e1, col_e2 = st.columns(2)
                                        submit_edit = col_e1.form_submit_button("保存", type="primary", width="stretch")
                                        cancel_edit = col_e2.form_submit_button("取消", width="stretch")

                                        if submit_edit:
                                            try:
                                                msg = service.update_refund(refund_id=r.id, refund_amount=new_amount, refund_reason=new_reason)
                                                st.success(msg)
                                                del st.session_state[f"is_editing_refund_{r.id}"]
                                                sync_all_caches()
                                                st.rerun()
                                            except Exception as e:
                                                st.error(str(e))
                                        if cancel_edit:
                                            del st.session_state[f"is_editing_refund_{r.id}"]
                                            st.rerun()
                        st.divider()

                    with st.form(f"new_refund_form_{o.id}"):
                        st.markdown("**添加新售后:**")
                        refund_amount = st.number_input("售后金额", min_value=0.0, step=10.0, format="%.2f")
                        refund_reason = st.text_input("售后原因", placeholder="如：尺寸不合适、质量问题等")
                        is_returned = st.checkbox("是否退货")

                        returned_items = []
                        if is_returned:
                            st.markdown("**选择退货商品:**")
                            for item in o.items:
                                return_qty = st.number_input(
                                    f"{item.product_name}-{item.variant}",
                                    min_value=0,
                                    max_value=item.quantity,
                                    step=1,
                                    key=f"return_qty_{item.id}_{o.id}"
                                )
                                if return_qty > 0:
                                    returned_items.append({
                                        "product_name": item.product_name,
                                        "variant": item.variant,
                                        "quantity": return_qty
                                    })

                        col_rf1, col_rf2 = st.columns(2)
                        submit_refund = col_rf1.form_submit_button("添加售后", type="primary", width="stretch")
                        cancel_refund = col_rf2.form_submit_button("关闭", width="stretch")

                        if submit_refund:
                            try:
                                returned_quantity = sum(item["quantity"] for item in returned_items) if is_returned else 0
                                msg = service.add_refund(
                                    order_id=o.id,
                                    refund_amount=refund_amount,
                                    refund_reason=refund_reason,
                                    is_returned=is_returned,
                                    returned_quantity=returned_quantity,
                                    returned_items=returned_items if is_returned else None
                                )
                                st.success(msg)
                                st.session_state.pop(f"show_refund_form_{target_order_id}", None)
                                sync_all_caches()
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

                        if cancel_refund:
                            del st.session_state[f"show_refund_form_{target_order_id}"]
                            st.rerun()

    with tab_all: render_order_list()
    with tab_pending: render_order_list(OrderStatus.PENDING)
    with tab_shipped: render_order_list(OrderStatus.SHIPPED)
    with tab_completed: render_order_list(OrderStatus.COMPLETED)
    with tab_after: render_order_list(OrderStatus.AFTER_SALES)