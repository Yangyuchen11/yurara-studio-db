import streamlit as st
import pandas as pd
from datetime import date
from services.sales_order_service import SalesOrderService
from cache_manager import sync_all_caches
from models import Product
from constants import OrderStatus, PLATFORM_CODES

# ------------------ 🚀 性能优化：独立数据层缓存 ------------------

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_order_stats(product_filter, test_mode_flag): # 增加参数
    db_cache = st.session_state.get_dynamic_session() # 动态获取
    try:
        service = SalesOrderService(db_cache)
        return service.get_order_statistics(product_name=product_filter)
    finally:
        db_cache.close()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_orders_df(status_filter, product_filter, test_mode_flag): # 增加参数
    db_cache = st.session_state.get_dynamic_session() # 动态获取
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

    # ================= 0. 商品选择 =================
    all_products = db.query(Product).all()
    product_options = ["全部商品"] + [p.name for p in all_products]

    selected_product = st.selectbox(
        "📦 选择商品",
        product_options,
        key="sales_order_product_filter",
        help="选择商品后，下方所有统计和订单都将筛选该商品"
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

    # ================= 2. 创建订单 =================
    with st.expander("➕ 创建新订单", expanded=False):
        if not product_filter:
            st.warning("⚠️ 请先在顶部选择具体商品后再创建订单")
        else:
            st.subheader("订单信息")
            products = db.query(Product).all()
            product_dict = {p.name: p for p in products}

            if product_filter not in product_dict:
                st.error("选择的商品不存在")
            else:
                selected_product_obj = product_dict[product_filter]
                color_options = [c.color_name for c in selected_product_obj.colors]

                col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                order_no = col_p1.text_input("订单号", placeholder="输入订单号（必填）", key="order_no_input")
                platform = col_p2.selectbox("销售平台", list(PLATFORM_CODES.values()))
                currency = col_p3.selectbox("币种", ["CNY", "JPY"])
                order_date = col_p4.date_input("订单日期", value=date.today())

                col_price, col_fee, col_notes = st.columns([1, 1, 2], vertical_alignment="bottom")
                total_price = col_price.number_input("订单总价", min_value=0.0, step=10.0, value=0.0, format="%.2f", key="order_total_price")
                deduct_fee = col_fee.checkbox("扣除平台手续费", value=False, help="微店(0.6%), Booth(5.6%+22 JPY/笔)")
                notes = col_notes.text_input("订单备注", placeholder="如：客户名称、特殊要求等", key="order_notes_input")
                st.divider()

                st.markdown("**商品款式明细（请输入每个款式的数量）:**")
                if not color_options:
                    st.warning("该商品没有可用的款式")
                else:
                    variant_quantities = {}
                    for idx, color in enumerate(color_options):
                        col_variant, col_qty, col_spacer = st.columns([1, 1, 3])
                        col_variant.write(f"**{color}**")
                        qty = col_qty.number_input("数量", min_value=0, step=1, value=0, key=f"variant_qty_{idx}_{color}", label_visibility="collapsed")
                        variant_quantities[color] = qty

                    st.divider()
                    
                    # === 计算逻辑：处理手续费 ===
                    total_quantity = sum(variant_quantities.values())
                    gross_price = total_price
                    fee = 0.0
                    
                    if deduct_fee:
                        if platform == "微店":
                            fee = gross_price * 0.006
                        elif platform == "Booth":
                            # Booth 计算：仅在选择日元时严格+22JPY；如错选了CNY暂以近1 CNY替代
                            base_fixed_fee = 22 if currency == "JPY" else 1.0 
                            fee = gross_price * 0.056 + base_fixed_fee
                            
                    net_price = gross_price - fee
                    
                    # === 显示数据 ===
                    col_qty_display, col_price_display, col_spacer = st.columns([1, 1.8, 1.2])
                    col_qty_display.markdown(f"**总数量: {total_quantity} 件**")

                    if total_quantity > 0 and gross_price > 0:
                        unit_price = net_price / total_quantity
                        fee_str = f" (已扣除预估手续费: {fee:.2f})" if fee > 0 else ""
                        col_price_display.markdown(f"**实际净收: {net_price:.2f} {currency} | 平均单价: {unit_price:.2f} {currency}/件**{fee_str}")
                    else:
                        col_price_display.markdown(f"**平均单价: - {currency}/件**")

                    if st.button("✅ 提交订单", type="primary", width="stretch"):
                        if not order_no or not order_no.strip(): st.error("❌ 请输入订单号")
                        elif total_quantity == 0: st.error("❌ 请至少输入一个款式的数量")
                        elif gross_price <= 0: st.error("❌ 请输入订单总价")
                        elif net_price <= 0: st.error("❌ 扣除手续费后的净金额小于等于 0，请检查")
                        else:
                            items_data = []
                            # 注意：保存至数据库的是扣除过手续费之后的净额(net_price)
                            final_unit_price = net_price / total_quantity
                            for color, qty in variant_quantities.items():
                                if qty > 0:
                                    items_data.append({"product_name": product_filter, "variant": color, "quantity": qty, "unit_price": final_unit_price, "subtotal": qty * final_unit_price})
                            
                            order, error = service.create_order(items_data=items_data, platform=platform, currency=currency, notes=notes, order_date=order_date, order_no=order_no.strip())
                            if error:
                                st.error(f"创建失败: {error}")
                            else:
                                st.success(f"✅ 订单 {order.order_no} 创建成功！(记账金额: {net_price:.2f} {currency})")
                                sync_all_caches() # <--- 数据库发生变化，清空缓存
                                st.rerun()

    # ================= 2.5 批量导入订单 =================
    with st.expander("📥 批量导入订单 (Excel)", expanded=False):
        st.markdown("""
        **表格格式要求**：请上传包含以下 7 列的 Excel 文件（列名必须完全一致）：
        `订单号` | `商品名` | `商品型号` | `数量` | `销售平台` | `订单总额` | `币种`
        
        💡 **多款式说明**：**一个订单只能占一行，严禁出现重复订单号**。如果同一个订单内有多个不同颜色/型号，请在`商品型号`和`数量`列用**英文分号 (;)** 隔开。
        例如：型号填 `粉色;蓝色`，数量填 `1;2`，代表买了一件粉色和两件蓝色。
        """)
        
        # 初始化一个动态的版本号 key
        if "uploader_key" not in st.session_state:
            st.session_state.uploader_key = 0
            
        # 把版本号拼接到 key 里面
        uploaded_file = st.file_uploader(
            "上传 Excel 文件", 
            type=["xlsx", "xls"], 
            key=f"order_excel_uploader_{st.session_state.uploader_key}"
        )
        
        if uploaded_file is not None:
            try:
                # 读取 Excel
                df_import = pd.read_excel(uploaded_file)
                
                # 调用 Service 进行解析和校验
                parsed_orders, errors = service.validate_and_parse_import_data(df_import)
                
                if errors:
                    st.error("❌ 数据校验失败，请修复 Excel 中的以下问题后重新上传：")
                    for err in errors:
                        st.write(f"- {err}")
                elif parsed_orders:
                    st.success(f"✅ 数据校验通过！共识别出 {len(parsed_orders)} 个有效订单。预览如下：")
                    
                    # 准备预览数据
                    preview_data = []
                    for po in parsed_orders:
                        # 拼接合并后的明细字符串
                        items_str = ", ".join([f"{i['product_name']}-{i['variant']} ×{i['quantity']}" for i in po["items"]])
                        preview_data.append({
                            "订单号": po["order_no"],
                            "平台": po["platform"],
                            "币种": po["currency"],
                            "总数量": po["total_qty"],
                            "原总价": po["gross_price"],
                            "预估手续费": po["fee"],
                            "实际净入账": po["net_price"],
                            "商品明细": items_str
                        })
                        
                    # 渲染预览表格
                    st.dataframe(
                        pd.DataFrame(preview_data), 
                        width="stretch",
                        column_config={
                            "原总价": st.column_config.NumberColumn(format="%.2f"),
                            "预估手续费": st.column_config.NumberColumn(format="%.2f"),
                            "实际净入账": st.column_config.NumberColumn(format="%.2f")
                        }
                    )
                    
                    # 确认导入按钮
                    if st.button("🚀 确认无误，开始导入订单", type="primary"):
                        with st.spinner("正在逐个生成订单并入账..."):
                            count = service.batch_create_orders(parsed_orders)
                            st.toast(f"导入完成！成功生成 {count} 个订单。", icon="✅")
                            sync_all_caches() # 清除缓存，刷新列表
                            
                            # 让上传组件的版本号 +1，强制它变成一个全新的空组件
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

        # 初始化全局全选状态
        if select_all_key not in st.session_state:
            st.session_state[select_all_key] = False

        # ⚡ 极速加载：从缓存获取 DataFrame
        with st.spinner("加载数据中..."):
            df = get_cached_orders_df(status_filter, product_filter, test_mode).copy()

        if df.empty:
            st.info("暂无订单")
            return

        # ================= 3.1 状态安全的全选/取消逻辑 =================
        c_sel1, c_sel2, _ = st.columns([1, 1, 6])
        
        if c_sel1.button("☑️ 全选", key=f"btn_sel_all_{status_key_suffix}", width="stretch"):
            st.session_state[select_all_key] = True
            # 【修复点2】Streamlit 不允许直接赋值 data_editor 的状态，但允许通过 del 清空状态
            # 这样表格就会重新读取下方 df["勾选"] 的默认值
            if editor_key in st.session_state: 
                del st.session_state[editor_key]
            st.rerun()
            
        if c_sel2.button("☐ 取消全选", key=f"btn_desel_all_{status_key_suffix}", width="stretch"):
            st.session_state[select_all_key] = False
            if editor_key in st.session_state: 
                del st.session_state[editor_key]
            st.rerun()

        # 根据全局状态覆盖 DataFrame 的默认勾选状态
        is_all_selected = st.session_state[select_all_key]
        df["勾选"] = is_all_selected

        st.markdown("**👇 勾选下方订单，点击操作栏按钮执行相应操作**")

        # ================= 3.2 渲染数据表格 =================
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

        # ================= 3.3 按钮状态推导 =================
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

        # ================= 3.4 全局操作栏 =================
        st.divider()
        
        # 👇 核心修复：使用带有 status_key_suffix 的独立 key，防止被其他 Tab 提前删掉
        err_key = f"order_op_errors_{status_key_suffix}"
        if err_key in st.session_state:
            for err in st.session_state[err_key]:
                st.error(err, icon="🚨")
            # 展示完就删掉缓存，这样它会一直挂在屏幕上，直到下一次交互才会消失
            del st.session_state[err_key]

        action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)
        
        # 📦 发货按钮
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
                # 把报错存入属于当前 Tab 的专属变量中
                st.session_state[err_key] = err_list
                
            if success_count > 0 or err_list:
                st.rerun()

        # ✅ 完成按钮
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
                # 把报错存入属于当前 Tab 的专属变量中
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

        # ================== 3.5 单选展开面板 ==================
        if target_order_id:
            # 单笔查询速度极快，不影响全局性能
            o = service.get_order_by_id(target_order_id)
            
            # --- 展开：删除确认 ---
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

            # --- 展开：订单详情 ---
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

                    st.write(f"**备注:** {o.notes or '无'}")

                    st.divider()
                    st.markdown("**商品明细:**")
                    items_detail = [{"商品": i.product_name, "款式": i.variant, "数量": i.quantity, "单价": i.unit_price, "小计": i.subtotal} for i in o.items]
                    st.dataframe(pd.DataFrame(items_detail), width="stretch", hide_index=True, column_config={"单价": st.column_config.NumberColumn(format="%.2f"), "小计": st.column_config.NumberColumn(format="%.2f")})
                    
                    st.write(f"**订单总额: {o.total_amount:.2f} {o.currency}**")

            # --- 展开：售后管理 ---
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
                                    # 恢复修改按钮
                                    if btn_c1.button("✏️", key=f"edit_refund_{r.id}", help="修改", width="stretch"):
                                        st.session_state[f"is_editing_refund_{r.id}"] = True
                                        st.rerun()
                                    # 恢复删除按钮
                                    if btn_c2.button("🗑️", key=f"del_refund_{r.id}", help="删除", width="stretch"):
                                        try:
                                            msg = service.delete_refund(r.id)
                                            st.toast(msg, icon="✅")
                                            sync_all_caches()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(str(e))

                                # 恢复修改表单
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

                    # 恢复申请新售后表单 (带精确退货商品选择)
                    with st.form(f"new_refund_form_{o.id}"):
                        st.markdown("**添加新售后:**")
                        refund_amount = st.number_input("售后金额", min_value=0.0, step=10.0, format="%.2f")
                        refund_reason = st.text_input("售后原因", placeholder="如：尺寸不合适、质量问题等")
                        is_returned = st.checkbox("是否退货")

                        # 恢复具体的退货商品选择逻辑
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