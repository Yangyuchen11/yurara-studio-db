# views/offline_sales_view.py
import streamlit as st
import pandas as pd
import re
from sqlalchemy import func
from models import InventoryLog
from services.offline_sales_service import OfflineSalesService
from services.product_service import ProductService
from services.finance_service import FinanceService
from services.inventory_service import InventoryService
from constants import PLATFORM_CODES
from cache_manager import sync_all_caches
import streamlit.components.v1 as components

if hasattr(st, "fragment"):
    fragment_decorator = st.fragment
else:
    fragment_decorator = st.experimental_fragment

def get_warehouse_stock_map(db, warehouse_id):
    """辅助函数：获取特定仓库下所有商品的现货库存字典"""
    valid_reasons = ["入库", "出库", "退货入库", "发货撤销", "验收完成入库", "其他入库", "库存移动"]
    query = db.query(
        InventoryLog.product_name, 
        InventoryLog.variant, 
        func.sum(InventoryLog.change_amount).label('total')
    ).filter(InventoryLog.reason.in_(valid_reasons))
    
    if warehouse_id is not None:
        query = query.filter(InventoryLog.warehouse_id == warehouse_id)
    else:
        query = query.filter(InventoryLog.warehouse_id == None)
        
    res = query.group_by(InventoryLog.product_name, InventoryLog.variant).all()
    return {f"{r.product_name}_{r.variant}": (r.total or 0) for r in res}

@fragment_decorator
def render_pos_machine(db, template, all_cash_assets, image_lookup):
    """POS收银机：恢复购物车缩略图与非全屏底部历史记录，保持边框对齐与全屏优化"""
    
    # 1. 状态初始化
    if "offline_cart" not in st.session_state:
        st.session_state.offline_cart = {}
    if "pos_fullscreen" not in st.session_state:
        st.session_state.pos_fullscreen = False
    if "pos_pay_method" not in st.session_state:
        st.session_state.pos_pay_method = "现金"
    if "show_history_only" not in st.session_state:
        st.session_state.show_history_only = False

    def add_to_cart_cb(p_name, v_name, price, max_qty):
        cart_key = f"{p_name}_{v_name}"
        if cart_key in st.session_state.offline_cart:
            if st.session_state.offline_cart[cart_key]["qty"] < max_qty:
                st.session_state.offline_cart[cart_key]["qty"] += 1
            else:
                st.toast("已达模板最大分配限额！", icon="⚠️")
        else:
            st.session_state.offline_cart[cart_key] = {
                "product_name": p_name, "variant": v_name,
                "unit_price": price, "qty": 1
            }

    def remove_from_cart_cb(p_name, v_name):
        cart_key = f"{p_name}_{v_name}"
        if cart_key in st.session_state.offline_cart:
            st.session_state.offline_cart[cart_key]["qty"] -= 1
            if st.session_state.offline_cart[cart_key]["qty"] <= 0:
                del st.session_state.offline_cart[cart_key]

    def set_pay_method_cb(method):
        st.session_state.pos_pay_method = method

    # 2. 注入全屏与滚动控制脚本
    components.html(
        """
        <script>
        const parentDoc = window.parent.document;
        setInterval(() => {
            const markers = parentDoc.querySelectorAll('.pos-scroll-marker');
            markers.forEach(marker => {
                let col = marker.closest('div[data-testid="column"]');
                if (col && col.style.overflowY !== 'auto') {
                    col.style.height = 'calc(100vh - 2rem)';
                    col.style.overflowY = 'auto';
                    col.style.overscrollBehavior = 'contain';
                    col.style.WebkitOverflowScrolling = 'touch';
                }
            });
        }, 500);
        </script>
        """,
        height=0, width=0
    )

    # 3. 样式注入：【修改】使用 Flexbox 实现自适应高度布局
    fullscreen_style = ""
    if st.session_state.pos_fullscreen:
        fullscreen_style = """
        [data-testid="stSidebar"] {display: none !important;}
        header {display: none !important;}
        [data-testid="stTabs"] [data-baseweb="tab-list"] {display: none !important;}
        
        /* 核心修改：允许页面纵向滚动 */
        html, body, [data-testid="stAppViewContainer"], .main {
            overflow-y: auto !important; /* 允许滚动 */
            height: auto !important;     /* 高度根据内容自适应 */
            min-height: 100vh !important;
        }
        
        .block-container {
            padding: 0.5rem 1.5rem !important;
            max-width: 100% !important;
            height: auto !important;      /* 确保容器不会被截断 */
            overflow: visible !important;
        }
        
        /* 针对左侧商品列表和右侧购物车，如果内容过多，也可以保持内部滚动 */
        .pos-scroll-marker {
            display: block;
        }

        /* 强制对齐修正 */
        div[data-testid="column"]:nth-child(1) h3 {
            margin-top: 0 !important;
            padding-top: 5px !important;
        }
        """

    st.markdown(f"""
    <style>
    {fullscreen_style}
    ::-webkit-scrollbar {{ display: none !important; }}
    
    /* 结账按钮保持巨大化 */
    div[data-testid="stElementContainer"]:has(.checkout-btn-marker) + div[data-testid="stElementContainer"] button {{
        height: 70px !important;
        border-radius: 12px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    # 4. 界面渲染逻辑
    svc = OfflineSalesService(db)

    # ================= 情况 A: 专门的历史记录界面 (全屏模式下查看历史) =================
    if st.session_state.show_history_only:
        st.markdown('<div class="pos-scroll-marker"></div>', unsafe_allow_html=True)
        c_hist_head, c_hist_back = st.columns([5, 1])
        c_hist_head.subheader(f"📜 {template.name} - 历史交易全览")
        if c_hist_back.button("🔙 返回收银", use_container_width=True):
            st.session_state.show_history_only = False
            st.rerun()
            
        orders = svc.get_orders_by_template(template.code)
        if orders:
            order_data = []
            for o in orders:
                items_str = ", ".join([f"{i.product_name}-{i.variant} ×{i.quantity}" for i in o.items])
                import re
                fee = 0.0
                match = re.search(r"扣除手续费 ([\d\.]+)", o.notes or "")
                if match: fee = float(match.group(1))
                order_data.append({
                    "订单号": o.order_no, "日期": str(o.created_date), 
                    "明细": items_str, "原价": o.total_amount, "实收": o.total_amount - fee, "备注": o.notes
                })
            st.dataframe(pd.DataFrame(order_data), width="stretch", hide_index=True)
        else:
            st.info("暂无历史交易")
        return # 结束历史界面渲染

    # ================= 情况 B: 标准收银界面 =================
    c_goods, c_cart = st.columns([2.5, 1.3])
    
    with c_goods:
        st.markdown('<div class="pos-scroll-marker"></div>', unsafe_allow_html=True)
        # 顶部标题
        st.markdown(f"### 🛒 {template.name} <small>({template.platform})</small>", unsafe_allow_html=True)
        st.caption(f"出货仓库: {template.warehouse.name if template.warehouse else '未分配'}")
        
        # 商品矩阵
        if not template.items:
            st.info("模板为空")
        else:
            cols = st.columns(4)
            for idx, item in enumerate(template.items):
                is_out_of_stock = (item.remaining_quantity <= 0)
                cart_key = f"{item.product_name}_{item.variant}"
                
                with cols[idx % 4]:
                    with st.container(border=True):
                        # 1. 顶部渲染缩略图
                        img_data = image_lookup.get(f"{item.product_name}_{item.variant}")
                        if img_data:
                            st.image(img_data, use_container_width=True)
                        else:
                            st.markdown("<div style='height:70px; background:#f0f2f6; border-radius:5px; margin-bottom:5px;'></div>", unsafe_allow_html=True)
                        
                        # 2. 库存状态提示与按钮
                        if is_out_of_stock:
                            st.markdown("<div style='font-size:12px; color:red; text-align:center; margin-bottom:4px; font-weight:bold;'>🚫 已售罄</div>", unsafe_allow_html=True)
                            btn_label_out = f"{item.product_name}\n{item.variant}\n🚫 暂无库存"
                            st.button(btn_label_out, key=f"btn_off_{item.id}", disabled=True, use_container_width=True)
                        else:
                            st.markdown(f"<div style='font-size:12px; color:#4caf50; text-align:center; margin-bottom:4px; font-weight:bold;'>📦 余量: {item.remaining_quantity}</div>", unsafe_allow_html=True)
                            btn_label = f"{item.product_name}\n{item.variant}\n¥ {item.preset_price:.2f} ➕"
                            st.button(
                                btn_label, 
                                key=f"pos_btn_{item.id}", 
                                use_container_width=True,
                                on_click=add_to_cart_cb,  # 点击时去执行上面的函数
                                args=(item.product_name, item.variant, item.preset_price, item.remaining_quantity) # 把这四个变量传给函数
                            )

    with c_cart:
        # 1. 顶部控制按钮组
        btn_col1, btn_col2 = st.columns(2)
        if btn_col1.button("🔲 退出全屏" if st.session_state.pos_fullscreen else "🔲 全屏模式", use_container_width=True):
            st.session_state.pos_fullscreen = not st.session_state.pos_fullscreen
            st.rerun()
        if btn_col2.button("📜 历史交易", use_container_width=True):
            st.session_state.show_history_only = True
            st.rerun()

        # 2. 结账单容器
        st.markdown('<div class="pos-scroll-marker"></div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### 🧾 结账单")
            cart_items = list(st.session_state.offline_cart.values())
            total_amount = sum(ci["qty"] * ci["unit_price"] for ci in cart_items)
            
            st.markdown('<div class="cart-list-marker"></div>', unsafe_allow_html=True)
            
            with st.container():
                if not cart_items: 
                    st.caption("购物车为空")
                else:
                    # ================= 结账单内带缩略图的列表 =================
                    for idx, ci in enumerate(cart_items):
                        r_img, r_c1, r_c2, r_c3 = st.columns([1.5, 3, 1, 1], vertical_alignment="center")
                        
                        img_data = image_lookup.get(f"{ci['product_name']}_{ci['variant']}")
                        if img_data:
                            r_img.image(img_data, use_container_width=True)
                        else:
                            r_img.markdown("<div style='height:30px; background:#f0f2f6; border-radius:3px;'></div>", unsafe_allow_html=True)
                            
                        r_c1.markdown(f"<span style='font-size:13px; font-weight:bold;'>{ci['product_name']}</span><br><span style='font-size:11px; color:gray;'>{ci['variant']}</span>", unsafe_allow_html=True)
                        r_c2.markdown(f"**x {ci['qty']}**")
                        
                    st.button(
                        "❌", 
                        key=f"rem_{idx}", 
                        help="移除一项",
                        on_click=remove_from_cart_cb, # 绑定回调函数
                        args=(ci['product_name'], ci['variant']) # 传入参数
                    )
                    # ===============================================================

            st.divider()
            
            # 支付选择
            c_pay1, c_pay2 = st.columns(2)
            c_pay1.button(
                "💵 现金", 
                type="primary" if st.session_state.pos_pay_method == "现金" else "secondary", 
                use_container_width=True,
                on_click=set_pay_method_cb, args=("现金",)
            )
            c_pay2.button(
                "📱 PayPay", 
                type="primary" if st.session_state.pos_pay_method == "PayPay" else "secondary", 
                use_container_width=True,
                on_click=set_pay_method_cb, args=("PayPay",)
            )
                
            fee = total_amount * 0.0198 if st.session_state.pos_pay_method == "PayPay" else 0.0
            st.markdown(f"**总计: <span style='color:red; font-size:22px;'>{total_amount:,.2f}</span>**", unsafe_allow_html=True)
            if st.session_state.pos_pay_method == "PayPay":
                st.caption(f"手续费(1.98%): ¥ {fee:,.2f} | 预估实收: ¥ {total_amount - fee:,.2f}")
            # 收款账户
            valid_accs = [a for a in all_cash_assets if a.currency == template.currency]
            acc_opts = {a.name: a.id for a in valid_accs}
            target_acc_id = None
            if acc_opts:
                acc_names = list(acc_opts.keys())
                default_idx = 0
                
                # 【修复3】补回根据支付方式自动选择默认收款账户的逻辑
                pay_method = st.session_state.pos_pay_method
                for i, name in enumerate(acc_names):
                    if pay_method == "PayPay" and "paypay" in name.lower():
                        default_idx = i
                        break
                    elif pay_method == "现金" and ("现金" in name or "cash" in name.lower()):
                        default_idx = i
                        break

                sel_acc = st.selectbox("收款账户", acc_names, index=default_idx, label_visibility="collapsed")
                target_acc_id = acc_opts[sel_acc]

            # 巨大化结账按钮
            st.markdown('<div class="checkout-btn-marker"></div>', unsafe_allow_html=True)
            if st.button("✅ 完成交易", type="primary", use_container_width=True, disabled=(not cart_items or not target_acc_id)):
                try:
                    svc.checkout_offline_order(
                        template_id=template.id, cart_items=cart_items,
                        payment_method=st.session_state.pos_pay_method, fee_rate=0.0198,
                        account_id=target_acc_id
                    )
                    st.session_state.offline_cart = {}
                    sync_all_caches()
                    st.rerun()
                except Exception as e: st.error(f"失败: {e}")
    # ================= 恢复：非全屏模式下的原版底部历史记录 =================
    if not st.session_state.pos_fullscreen:
        st.divider()
        st.subheader(f"📜 [{template.name}] 历史交易")
        orders = svc.get_orders_by_template(template.code)
        if orders:
            order_data = []
            for o in orders:
                items_str = ", ".join([f"{i.product_name}-{i.variant} ×{i.quantity}" for i in o.items])
                
                import re
                fee = 0.0
                match = re.search(r"扣除手续费 ([\d\.]+)", o.notes or "")
                if match:
                    fee = float(match.group(1))
                net_income = o.total_amount - fee
                
                order_data.append({
                    "订单号": o.order_no, "日期": str(o.created_date), "平台": o.platform,
                    "商品明细": items_str, "原价小计": o.total_amount, "实收净额": net_income, "备注": o.notes
                })
                
            st.dataframe(
                pd.DataFrame(order_data), 
                width="stretch", 
                hide_index=True,
                column_config={
                    "原价小计": st.column_config.NumberColumn(format="%.2f"),
                    "实收净额": st.column_config.NumberColumn(format="%.2f")
                }
            )
        else:
            st.info("该模板暂无销售记录。")
                         
def show_offline_sales_page(db):
    if not st.session_state.get("pos_fullscreen", False):
        st.header("🏪 线下展会模式")
    svc = OfflineSalesService(db)
    templates = svc.get_all_templates()
    all_prods = ProductService(db).get_all_products()
    image_lookup = {f"{p.name}_{c.color_name}": c.image_data for p in all_prods for c in p.colors}
    
    warehouses = InventoryService(db).get_all_warehouses()
    wh_opts = {w.name: w.id for w in warehouses}
    platform_list = list(PLATFORM_CODES.values())

    tab_pos, tab_tpl = st.tabs(["💻 POS 收银台", "⚙️ 模板配置"])
    
    with tab_pos:
        if not templates: 
            st.warning("请先创建模板")
        else:
            tpl_map = {f"{t.name} ({t.code})": t for t in templates}
            tpl_names = list(tpl_map.keys())
            
            if "active_tpl_name" not in st.session_state or st.session_state.active_tpl_name not in tpl_names:
                st.session_state.active_tpl_name = tpl_names[0]
            
            # 全屏时隐藏选择框
            if not st.session_state.get("pos_fullscreen", False):
                sel_tpl = st.selectbox("当前活动模板", tpl_names, index=tpl_names.index(st.session_state.active_tpl_name))
                st.session_state.active_tpl_name = sel_tpl
                st.divider()
                
            active_tpl = tpl_map[st.session_state.active_tpl_name]
            all_cash = [a for a in FinanceService.get_transferable_assets(db) if getattr(a, 'asset_type', '') == "现金"]
            
            render_pos_machine(db, active_tpl, all_cash, image_lookup)
            
    with tab_tpl:
        # ----------------- A. 创建新模板 -----------------
        with st.expander("➕ 创建新场景模板", expanded=False):
            c1, c2, c3 = st.columns(3)
            n_name = c1.text_input("模板名称")
            n_code = c2.text_input("代号 (前缀)")
            n_curr = c3.selectbox("币种", ["CNY", "JPY"])
            
            c4, c5 = st.columns(2)
            n_wh = c4.selectbox("出货仓库 (指定线下库存来源)", ["未分配"] + list(wh_opts.keys()))
            n_plat = c5.selectbox("销售平台 (影响流水显示)", platform_list)
            plat_code = next((k for k, v in PLATFORM_CODES.items() if v == n_plat), None)
            
            wh_id_create = wh_opts.get(n_wh)
            stock_map_create = get_warehouse_stock_map(db, wh_id_create)
            
            st.markdown("**分配商品及线下限额：**")
            data_list = []
            for p in all_prods:
                for c in p.colors:
                    price = 0.0
                    if c.prices:
                        matched = next((pr.price for pr in c.prices if pr.platform == plat_code), None)
                        price = matched if matched is not None else next((pr.price for pr in c.prices if pr.currency == "CNY"), c.prices[0].price)
                        
                    key = f"{p.name}_{c.color_name}"
                    max_stock = int(stock_map_create.get(key, 0))
                        
                    data_list.append({
                        "加入": False, "商品名称": p.name, "款式": c.color_name, 
                        "售价": price, "分配数量": 0, "可分配最大数量": max_stock
                    })
            
            df_tpl = st.data_editor(
                pd.DataFrame(data_list), 
                hide_index=True, 
                key=f"create_tpl_de_{n_plat}_{n_wh}", 
                column_config={
                    "加入": st.column_config.CheckboxColumn(required=True),
                    "商品名称": st.column_config.TextColumn(disabled=True),
                    "款式": st.column_config.TextColumn(disabled=True),
                    "售价": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                    "分配数量": st.column_config.NumberColumn(min_value=0, step=1),
                    "可分配最大数量": st.column_config.NumberColumn(disabled=True)
                }
            )
            
            if st.button("💾 保存模板"):
                sel_rows = df_tpl[df_tpl["加入"] == True]
                if not n_name or sel_rows.empty: 
                    st.error("信息不完整或未选择商品")
                else:
                    has_error = False
                    for _, r in sel_rows.iterrows():
                        if r["分配数量"] > r["可分配最大数量"]:
                            st.error(f"商品 {r['商品名称']}-{r['款式']} 分配数量({r['分配数量']}) 超过库存({r['可分配最大数量']})！")
                            has_error = True
                            
                    if not has_error:
                        items = [{"product_name": r["商品名称"], "variant": r["款式"], "preset_price": r["售价"], "quantity": int(r["分配数量"])} for _, r in sel_rows.iterrows()]
                        try:
                            svc.create_template(n_name, n_code, n_curr, wh_id_create, n_plat, items)
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存失败: {e}")

        # ----------------- B. 编辑现有模板 -----------------
        with st.expander("✏️ 编辑现有模板", expanded=True):
            if templates:
                e_tpl_map = {f"{t.name} ({t.code})": t for t in templates}
                sel_e = st.selectbox("选择模板", list(e_tpl_map.keys()))
                t = e_tpl_map[sel_e]
                
                ec1, ec2, ec3 = st.columns(3)
                en = ec1.text_input("修改名称", value=t.name, key=f"en_{t.id}")
                ec = ec2.text_input("修改代号", value=t.code, key=f"ec_{t.id}")
                ecu = ec3.selectbox("币种", ["CNY", "JPY"], index=0 if t.currency=="CNY" else 1, key=f"ecu_{t.id}")
                
                ec4, ec5 = st.columns(2)
                ewh = ec4.selectbox("出货仓库", ["未分配"] + list(wh_opts.keys()), index=([None]+list(wh_opts.values())).index(t.warehouse_id), key=f"ewh_{t.id}")
                epl = ec5.selectbox("销售平台 (影响流水显示)", platform_list, index=platform_list.index(t.platform) if t.platform in platform_list else 0, key=f"epl_{t.id}")
                e_plat_code = next((k for k, v in PLATFORM_CODES.items() if v == epl), None)
                
                wh_id_edit = wh_opts.get(ewh)
                stock_map_edit = get_warehouse_stock_map(db, wh_id_edit)
                is_platform_changed = (epl != t.platform)
                
                exist_map = {f"{i.product_name}_{i.variant}": (i.preset_price, i.quantity) for i in t.items}
                e_data = []
                for p in all_prods:
                    for c in p.colors:
                        key = f"{p.name}_{c.color_name}"
                        max_stock = int(stock_map_edit.get(key, 0))
                        
                        if key in exist_map and not is_platform_changed:
                            price, qty = exist_map[key]
                            is_in = True
                        else:
                            price = 0.0
                            if c.prices:
                                matched = next((pr.price for pr in c.prices if pr.platform == e_plat_code), None)
                                price = matched if matched is not None else next((pr.price for pr in c.prices if pr.currency == "CNY"), c.prices[0].price)
                            
                            if key in exist_map:
                                _, qty = exist_map[key]
                                is_in = True
                            else:
                                qty = 0
                                is_in = False
                                
                        e_data.append({
                            "加入": is_in, "商品名称": p.name, "款式": c.color_name, 
                            "售价": price, "分配数量": qty, "可分配最大数量": max_stock
                        })
                
                df_e = st.data_editor(
                    pd.DataFrame(e_data), 
                    hide_index=True, 
                    key=f"ede_{t.id}_{epl}_{ewh}", 
                    column_config={
                        "加入": st.column_config.CheckboxColumn(required=True),
                        "商品名称": st.column_config.TextColumn(disabled=True),
                        "款式": st.column_config.TextColumn(disabled=True),
                        "售价": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                        "分配数量": st.column_config.NumberColumn(min_value=0, step=1),
                        "可分配最大数量": st.column_config.NumberColumn(disabled=True)
                    }
                )
                
                c_s, c_d = st.columns([3, 1])
                if c_s.button("💾 保存修改", key=f"esv_{t.id}"):
                    sel = df_e[df_e["加入"] == True]
                    has_error = False
                    for _, r in sel.iterrows():
                        if r["分配数量"] > r["可分配最大数量"]:
                            st.error(f"商品 {r['商品名称']}-{r['款式']} 分配数量({r['分配数量']}) 超过库存({r['可分配最大数量']})！")
                            has_error = True
                            
                    if not has_error:
                        items = [{"product_name": r["商品名称"], "variant": r["款式"], "preset_price": r["售价"], "quantity": int(r["分配数量"])} for _, r in sel.iterrows()]
                        try:
                            svc.update_template(t.id, en, ec, ecu, wh_id_edit, epl, items)
                            st.toast("模板修改成功！", icon="✅")
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存失败: {e}")
                            
                if c_d.button("🗑️ 删除模板", key=f"edel_{t.id}"):
                    svc.delete_template(t.id)
                    st.rerun()