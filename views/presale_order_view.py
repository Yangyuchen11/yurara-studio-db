# views/presale_order_view.py
import streamlit as st
import pandas as pd
import math
from datetime import date
from services.sales_order_service import SalesOrderService
from cache_manager import sync_all_caches
from models import Product, CompanyBalanceItem, Warehouse
from constants import OrderStatus, PLATFORM_CODES

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_presale_order_stats(product_filter, test_mode_flag, cache_version):
    db_cache = st.session_state.get_dynamic_session()
    try:
        service = SalesOrderService(db_cache)
        return service.get_order_statistics(product_name=product_filter, order_type="预售")
    finally:
        db_cache.close()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_presale_orders_df(status_filter, product_filter, test_mode_flag, cache_version):
    db_cache = st.session_state.get_dynamic_session()
    try:
        service = SalesOrderService(db_cache)
        # 将 limit 改为 None，以支持全选 100 条以上的记录
        orders = service.get_all_orders(status=status_filter, product_name=product_filter, order_type="预售", limit=None)

        data_list = []
        for o in orders:
            items_summary = ", ".join([f"{i.product_name}-{i.variant}×{i.quantity}" for i in o.items[:2]])
            if len(o.items) > 2: items_summary += f" 等{len(o.items)}项"

            total_refunded = sum([r.refund_amount for r in o.refunds])
            status_display = o.status
            if o.status == OrderStatus.PRESALE_PENDING_DEPOSIT: status_display = "🕒 待完成定金"
            elif o.status == OrderStatus.PRESALE_PENDING_FINAL: status_display = "⏳ 待付尾款"
            elif o.status == OrderStatus.PENDING: status_display = "📦 待发货"
            elif o.status == OrderStatus.SHIPPED: status_display = "🚚 已发货"
            elif o.status == OrderStatus.COMPLETED: status_display = "✅ 完成"
            elif o.status == OrderStatus.AFTER_SALES: status_display = "🔧 售后"

            data_list.append({
                "勾选": False, "ID": o.id,
                "定金订单号": o.order_no, "尾款订单号": o.final_order_no if o.final_order_no else "-",
                "状态": status_display, "商品": items_summary,
                "定金金额": float(o.deposit_amount), "尾款金额": float(o.final_amount), "已退款": float(total_refunded),
                "优惠": o.discount_note if getattr(o, "discount_note", None) else "-",
                "币种": o.currency, "平台": o.platform, "日期": str(o.created_date)
            })
        return pd.DataFrame(data_list)
    finally:
        db_cache.close()


def show_presale_order_page(db, exchange_rate):
    st.header("⏳ 预售销售管理")
    test_mode = st.session_state.get("test_mode", False)
    cache_version = st.session_state.get("global_cache_version", 0)
    service = SalesOrderService(db)
    all_products = db.query(Product).all()
    wh_map = {w.name: w.id for w in db.query(Warehouse).all()}

    if "pre_cart" not in st.session_state: st.session_state.pre_cart = []

    # ================= 预售单据创建专区 =================
    with st.expander("➕ 创建预售单据", expanded=False):
        create_mode = st.radio("👉 选择操作类型", ["1️⃣ 创建主定金订单", "2️⃣ 绑定尾款单 (按单号精确查找)"], horizontal=True)
        st.divider()

        if "1️⃣" in create_mode:
            c_o1, c_o2 = st.columns(2)
            order_no = c_o1.text_input("定金单号", placeholder="输入定金单号（必填）", key="pre_order_no")
            order_date = c_o2.date_input("日期", value=date.today(), key="pre_date")

            c_p1, c_p2, c_p3 = st.columns([1, 1, 2])
            platform = c_p1.selectbox("销售平台", list(PLATFORM_CODES.values()), key="pre_plat")
            currency = c_p2.selectbox("币种", ["CNY", "JPY"], index=0 if platform in ["微店","国内线下","其他(CNY)"] else 1, key="pre_curr")
            
            cash_items = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.category == "asset", CompanyBalanceItem.asset_type == "现金", CompanyBalanceItem.currency == currency).all()
            acc_names = [a.name for a in cash_items]
            def_acc = "流动资金-支付宝账户"
            if platform == "微店": def_acc = "流动资金-微店账户"
            elif platform == "Booth": def_acc = "流动资金-booth账户"
            elif currency == "JPY": def_acc = "流动资金-日元临时账户"
            if def_acc not in acc_names: acc_names.insert(0, def_acc)
            target_account = c_p3.selectbox("收款现金账户", acc_names, index=acc_names.index(def_acc))

            st.subheader("订单商品录入 (用于创建定金单)")
            c_p, c_v, c_q, c_w, c_b = st.columns([2, 1.5, 1, 1.5, 1], vertical_alignment="bottom")
            sel_p = c_p.selectbox("选择商品", [p.name for p in all_products], key="pre_p")
            sel_p_obj = next((p for p in all_products if p.name == sel_p), None)
            sel_v = c_v.selectbox("选择款式", [c.color_name for c in sel_p_obj.colors] if sel_p_obj else [], key="pre_v")
            sel_q = c_q.number_input("数量", min_value=1, step=1, value=1, key="pre_q")
            sel_w = c_w.selectbox("出货仓库", list(wh_map.keys()) + ["未分配"], key="pre_w")
            
            if c_b.button("➕ 录入商品", type="primary", use_container_width=True):
                if sel_p and sel_v:
                    found = False
                    for item in st.session_state.pre_cart:
                        if item["product_name"] == sel_p and item["variant"] == sel_v and item["warehouse_name"] == sel_w:
                            item["quantity"] += sel_q
                            found = True; break
                    if not found:
                        st.session_state.pre_cart.append({"product_name": sel_p, "variant": sel_v, "quantity": sel_q, "warehouse_id": wh_map.get(sel_w), "warehouse_name": sel_w})
                    st.rerun()

            if st.session_state.pre_cart:
                cleaned_cart = []
                for record in st.data_editor(pd.DataFrame(st.session_state.pre_cart), width="stretch", num_rows="dynamic", key="pre_cart_ed", column_config={"product_name": st.column_config.TextColumn("商品", disabled=True), "variant": st.column_config.TextColumn("款式", disabled=True), "warehouse_name": st.column_config.TextColumn("仓库", disabled=True), "quantity": st.column_config.NumberColumn("数量", min_value=1)}).to_dict('records'):
                    if str(record.get("product_name")).strip(): cleaned_cart.append(record)
                st.session_state.pre_cart = cleaned_cart
            else: st.info("请加入商品进行操作。")

            st.divider()
            st.subheader("结算与提交")
            c_t1, c_t2, c_t3 = st.columns([1, 1, 1], vertical_alignment="bottom")
            total_price = c_t1.number_input("定金总价", min_value=0.0, step=10.0, format="%.2f", key="pre_tp")
            deduct_fee = c_t2.checkbox("扣除手续费(推荐)", value=True, key="pre_fee")
            discount_input = c_t3.text_input("优惠 (选填)", placeholder="如：减5元/包邮", key="pre_discount")
            notes = st.text_input("备注", key="pre_not")

            fee = 0.0; ship = 0.0
            if deduct_fee:
                if platform == "微店": fee = total_price * 0.006
                elif platform == "Booth": fee = math.ceil(total_price * 0.056 + 45)
            net_price = total_price - fee - ship

            st.markdown(f"**预估实际定金收入: <span style='color:green;'>{net_price:.2f} {currency}</span>**", unsafe_allow_html=True)
            if st.button("🚀 创建定金主订单", type="primary", width="stretch"):
                if not order_no: st.error("请填入定金单号")
                elif not st.session_state.pre_cart: st.error("请录入定金对应的商品")
                else:
                    items = [{"product_name": i["product_name"], "variant": i["variant"], "quantity": i["quantity"], "unit_price": net_price/sum(x["quantity"] for x in st.session_state.pre_cart), "warehouse_id": i.get("warehouse_id")} for i in st.session_state.pre_cart]
                    order, err = service.create_presale_deposit_order(items, platform, currency, notes, order_date, order_no, target_account, discount_note=discount_input)
                    if err: st.error(err)
                    else:
                        st.success("定金订单创建成功！")
                        st.session_state.pre_cart = []
                        sync_all_caches(); st.rerun()

        else:
            # ================= 2️⃣ 绑定尾款新流程 =================
            st.subheader("🔗 查找并绑定定金单")
            
            c_find1, c_find2 = st.columns([3, 1], vertical_alignment="bottom")
            search_no = c_find1.text_input("请输入原始定金单号", placeholder="例如: YR20240501...", key="search_dep_no")
            
            if c_find2.button("🔍 查找单据", use_container_width=True):
                target_order = service.get_order_by_no(search_no)
                if not target_order:
                    st.error(f"❌ 未找到定金单号: {search_no}")
                    st.session_state.found_deposit_order = None
                elif target_order.status != OrderStatus.PRESALE_PENDING_FINAL:
                    st.warning(f"⚠️ 订单已找到，但当前状态为【{target_order.status}】，只有【待付尾款】阶段的订单可被绑定。")
                    st.session_state.found_deposit_order = None
                else:
                    st.session_state.found_deposit_order = target_order
            
            if st.session_state.get("found_deposit_order"):
                o = st.session_state.found_deposit_order
                with st.container(border=True):
                    st.success(f"✅ 已锁定定金单！下单日期: {o.created_date} | platform: {o.platform}")
                    items_df = pd.DataFrame([{"商品": i.product_name, "款式": i.variant, "数量": i.quantity} for i in o.items])
                    st.markdown("**原定金商品明细：**")
                    st.dataframe(items_df, width="stretch", hide_index=True)
                
                st.divider()
                st.subheader("录入尾款信息")
                c_f1, c_f2 = st.columns(2)
                f_order_no = c_f1.text_input("尾款订单号 (必填)", key="final_no_input")
                f_amount = c_f2.number_input(f"实收尾款金额 ({o.currency})", min_value=0.0, step=10.0, format="%.2f", key="final_amount_input")
                
                c_n1, c_n2 = st.columns([1, 2])
                deduct_fee = c_n1.checkbox("扣除手续费(推荐)", value=True, key="pre_fee_final")
                f_notes = c_n2.text_input("备注", placeholder="可选", key="f_notes")

                fee = 0.0; ship = 0.0
                if deduct_fee:
                    if o.platform == "微店": fee = f_amount * 0.006
                    elif o.platform == "Booth": fee = math.ceil(f_amount * 0.056 + 45) 
                net_price = f_amount - fee - ship

                st.markdown(f"**预估实际尾款收入: <span style='color:green;'>{net_price:.2f} {o.currency}</span>**", unsafe_allow_html=True)

                if st.button("🚀 立即绑定并激活发货", type="primary", width="stretch"):
                    if not f_order_no:
                        st.error("请输入尾款订单号")
                    else:
                        try:
                            msg = service.bind_presale_final_order(o.id, f_order_no, net_price, f_notes)
                            st.success(msg)
                            st.session_state.found_deposit_order = None 
                            sync_all_caches()
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

    # ================= 预售批量导入 =================
    with st.expander("📥 批量导入预售单 (Excel)", expanded=False):
        st.markdown("""
        **表格格式要求**：请根据导入阶段准备对应的列名。
        
        💡 **1. 批量导入定金阶段**：
        需包含以下 **9 列**：
        `订单号` | `商品名` | `商品型号` | `数量` | `销售平台` | `订单总额` | `币种` | `出货仓库` | **`优惠`**
        
        💡 **2. 批量匹配并绑定尾款阶段**：
        需包含以下 **9 列**：
        `订单号` | **`关联定金单号`** | `商品名` | `商品型号` | `数量` | `销售平台` | `订单总额` | `币种` | `出货仓库`
        """)
        b_mode = st.radio("批量导入阶段", ["🚀 批量导入定金", "🔗 批量匹配并绑定尾款"], horizontal=True)
        pm_mode = "定金" if "定金" in b_mode else "尾款"
        
        if "pre_uploader_key" not in st.session_state:
            st.session_state.pre_uploader_key = 0
            
        up_file = st.file_uploader(f"上传Excel", type=["xlsx", "xls"], key=f"pre_ex_up_{st.session_state.pre_uploader_key}")
        
        if up_file:
            try:
                df_imp = pd.read_excel(up_file)
                parsed, errors = service.validate_and_parse_import_data(df_imp, exchange_rate, presale_mode=pm_mode)
                if errors:
                    st.error("数据校验失败："); 
                    for err in errors: st.write(f"- {err}")
                elif parsed:
                    st.success(f"校验通过，可导入/处理 {len(parsed)} 个单据。")
                    if st.button(f"🚀 开始批量{'创建' if pm_mode=='定金' else '绑定'}", type="primary"):
                        with st.spinner("处理中..."):
                            c = service.batch_create_orders(parsed, presale_mode=pm_mode)
                            st.toast(f"成功处理 {c} 个单据！", icon="✅")
                            sync_all_caches()
                            st.session_state.pre_uploader_key += 1
                            st.rerun()
            except Exception as e: st.error(f"处理失败: {e}")

    st.divider()

    # ================= 数据展示区 =================
    product_options = ["全部商品"] + [p.name for p in all_products]
    product_filter = st.selectbox("🔍 选择商品筛选", product_options, key="pre_pf")
    p_f = None if product_filter == "全部商品" else product_filter

    stats = get_cached_presale_order_stats(p_f, test_mode, cache_version)
    with st.container(border=True):
        c1,c2,c3,c4,c5,c6 = st.columns(6)
        c1.metric("总预售单数", stats["total"])
        c2.metric("待完成定金", stats["pending_deposit"])
        c3.metric("待付尾款", stats["pending_final"])
        c4.metric("已绑尾/待发货", stats["pending"], delta_color="off")
        c5.metric("已发货", stats["shipped"], delta_color="off")
        c6.metric("已完成", stats["completed"], delta_color="off")
        
    st.subheader("📋 预售订单列表")
    tabs = st.tabs(["全部", "待确认定金", "待付尾款", "待发货(已绑尾)", "已发货", "已完成", "售后中"])
    status_list = [None, OrderStatus.PRESALE_PENDING_DEPOSIT, OrderStatus.PRESALE_PENDING_FINAL, OrderStatus.PENDING, OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]

    for i, tab in enumerate(tabs):
        with tab:
            sf = status_list[i]
            sk = str(sf) if sf else "all"
            df = get_cached_presale_orders_df(sf, p_f, test_mode, cache_version).copy()
            if df.empty: st.info("暂无记录"); continue

            sa_key = f"psa_{sk}"
            ed_key = f"ped_{sk}"
            if sa_key not in st.session_state: st.session_state[sa_key] = False
            
            cs1, cs2, cs_sum = st.columns([1,1,6])
            if cs1.button("☑️ 全选", key=f"ps1_{sk}", width="stretch"): 
                st.session_state[sa_key] = True
                st.rerun()
            if cs2.button("☐ 取消全选", key=f"ps2_{sk}", width="stretch"): 
                st.session_state[sa_key] = False
                st.rerun()
            
            df["勾选"] = st.session_state[sa_key]

            ed_df = st.data_editor(
                df, 
                width="stretch", 
                hide_index=True, 
                key=ed_key, 
                disabled=["ID","定金订单号","尾款订单号","状态","商品","定金金额","尾款金额","已退款","优惠","币种","平台","日期"], 
                column_config={
                    "ID": None, 
                    "勾选": st.column_config.CheckboxColumn("选择"), 
                    "定金金额": st.column_config.NumberColumn(format="%.2f"), 
                    "尾款金额": st.column_config.NumberColumn(format="%.2f"), 
                    "已退款": st.column_config.NumberColumn(format="%.2f")
                }
            )

            selected_df = ed_df[ed_df["勾选"] == True]
            total_selected_amt = selected_df["定金金额"].sum() + selected_df["尾款金额"].sum()

            cs_sum.markdown(
                f"<div style='text-align: right; padding-top: 5px;'>"
                f"已选 {len(selected_df)} 项合计: "
                f"<span style='color:#ff4b4b; font-weight:bold; font-size:1.2rem;'>¥ {total_selected_amt:,.2f}</span>"
                f"</div>", 
                unsafe_allow_html=True
            )

            selected_indices = ed_df.index[ed_df["勾选"] == True].tolist()
            sel_ids = df.iloc[selected_indices]["ID"].tolist()
            sc = len(sel_ids)

            err_key = f"order_op_errors_{sk}"
            if err_key in st.session_state:
                for err in st.session_state[err_key]:
                    st.error(err, icon="🚨")
                del st.session_state[err_key]

            ac1, ac2, ac3, ac4, ac5 = st.columns(5)
            is_all_dep = sc > 0 and all("待完成定金" in str(s) for s in ed_df.iloc[selected_indices]["状态"])
            is_all_pen = sc > 0 and all("待发货" in str(s) for s in ed_df.iloc[selected_indices]["状态"])
            is_all_ship = sc > 0 and all("已发货" in str(s) for s in ed_df.iloc[selected_indices]["状态"])

            if ac1.button(f"📥 完成定金 ({sc})", key=f"pb_d_{sk}", type="primary", disabled=not is_all_dep, use_container_width=True):
                err_list = []
                for o_id in sel_ids: 
                    try: service.complete_deposit_order(o_id)
                    except Exception as e: err_list.append(str(e))
                st.session_state[sa_key] = False
                sync_all_caches()
                if err_list: st.session_state[err_key] = err_list
                st.rerun()
                
            if ac2.button(f"📦 发货 ({sc})", key=f"pb_s_{sk}", type="primary", disabled=not is_all_pen, use_container_width=True):
                err_list = []
                for o_id in sel_ids: 
                    try: service.ship_order(o_id)
                    except Exception as e: err_list.append(str(e))
                st.session_state[sa_key] = False
                sync_all_caches()
                if err_list: st.session_state[err_key] = err_list
                st.rerun()
                
            if ac3.button(f"✅ 完成尾款 ({sc})", key=f"pb_c_{sk}", type="primary", disabled=not is_all_ship, use_container_width=True):
                err_list = []
                for o_id in sel_ids: 
                    try: service.complete_order(o_id)
                    except Exception as e: err_list.append(str(e))
                st.session_state[sa_key] = False
                sync_all_caches()
                if err_list: st.session_state[err_key] = err_list
                st.rerun()
                
            if ac4.button("🔧 售后处理", key=f"pb_a_{sk}", disabled=(sc!=1), use_container_width=True):
                st.session_state[f"pre_ref_{sel_ids[0]}"] = True
                st.session_state.pop(f"pre_det_{sel_ids[0]}", None)
                
            # ✨ 将按钮重命名为 "✏️ 编辑/详情/删除"
            if ac5.button("✏️ 编辑/详情/删除", key=f"pb_x_{sk}", disabled=(sc!=1), use_container_width=True):
                st.session_state[f"pre_det_{sel_ids[0]}"] = True
                st.session_state.pop(f"pre_ref_{sel_ids[0]}", None)

            if sc == 1:
                t_id = sel_ids[0]
                o = service.get_order_by_id(t_id)

                if st.session_state.get(f"pre_det_{t_id}"):
                    with st.container(border=True):
                        st.markdown(f"**📝 预售订单详情 | 定金: {o.order_no} | 尾款: {o.final_order_no or '-'}**")
                        st.write(f"状态: **{o.status}** | 定金: **{o.deposit_amount}** | 尾款: **{o.final_amount}** | platform: {o.platform}")
                        
                        # ✨ 新增：订单详情中可直接修改优惠信息和备注的表单
                        with st.expander("✏️ 修改订单基础信息 (优惠/备注)"):
                            with st.form(f"edit_pre_info_{t_id}"):
                                new_discount = st.text_input("修改优惠信息", value=o.discount_note or "")
                                new_notes = st.text_area("修改备注", value=o.notes or "")
                                if st.form_submit_button("确认修改保存", type="primary"):
                                    try:
                                        service.update_order_info(t_id, {"discount_note": new_discount, "notes": new_notes})
                                        st.success("订单信息已成功更新！")
                                        sync_all_caches()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"修改失败: {e}")
                        
                        st.divider()
                        items = [{"商品": i.product_name, "款式": i.variant, "出货仓库": i.warehouse.name if i.warehouse else "-", "数量": i.quantity, "分配金额": i.subtotal} for i in o.items]
                        st.dataframe(pd.DataFrame(items), width="stretch", hide_index=True)
                        
                        c_del1, c_del2 = st.columns(2)
                        if o.final_order_no:
                            if c_del1.button("🟠 仅解绑/撤销尾款 (保留定金)", key=f"pre_unbind_{t_id}", use_container_width=True):
                                try:
                                    msg = service.unbind_presale_final(t_id)
                                    st.toast(msg, icon="✅"); sync_all_caches(); st.rerun()
                                except Exception as e: st.error(f"解绑失败: {e}")
                        if c_del2.button("🔴 彻底删除整个订单 (全额回滚)", key=f"pre_del_conf_{t_id}", type="primary", use_container_width=True):
                            try:
                                msg = service.delete_order(t_id)
                                st.toast(msg, icon="✅"); sync_all_caches(); st.rerun()
                            except Exception as e: f"删除失败: {e}"

                if st.session_state.get(f"pre_ref_{t_id}"):
                    with st.container(border=True):
                        st.markdown(f"**🔧 预售订单售后 | {o.final_order_no or o.order_no}**")
                        if o.refunds:
                            st.markdown("**已有售后:**")
                            for r in o.refunds: st.write(f"- {r.refund_date} | {r.refund_reason} | ¥ {r.refund_amount}")
                        
                        with st.form(f"p_ref_f_{t_id}"):
                            ra = st.number_input("退款金额", min_value=0.0)
                            rr = st.text_input("退款原因")
                            isr = st.checkbox("是否退回实物库存")
                            if st.form_submit_button("确认提交售后", type="primary"):
                                try:
                                    msg = service.add_refund(t_id, ra, rr, is_returned=isr, returned_quantity=0, returned_items=None)
                                    st.success(msg); sync_all_caches(); st.rerun()
                                except Exception as e: st.error(str(e))