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
    """POS收银机：真·浏览器全屏、巨型结账按钮、触屏优化"""
    
    # 状态初始化
    if "offline_cart" not in st.session_state:
        st.session_state.offline_cart = {}
    if "pos_fullscreen" not in st.session_state:
        st.session_state.pos_fullscreen = False
    if "pos_pay_method" not in st.session_state:
        st.session_state.pos_pay_method = "现金"

    # ================= 浏览器底层全屏 API 探针注入 (黑科技) =================
    components.html(
        """
        <script>
        // 获取父级(即Streamlit主页面)的document对象
        const parentDoc = window.parent.document;
        
        // 防止每次组件刷新时重复绑定事件
        if (!parentDoc.getElementById('pos-fs-listener')) {
            const script = parentDoc.createElement('script');
            script.id = 'pos-fs-listener';
            script.innerHTML = `
                document.addEventListener('click', function(e) {
                    let t = e.target;
                    // 向上冒泡查找，直到找到真实的 BUTTON 标签
                    while (t && t.tagName !== 'BUTTON') { t = t.parentElement; }
                    
                    if (t && t.tagName === 'BUTTON') {
                        if (t.innerText.includes('全屏模式')) {
                            let docElm = document.documentElement;
                            if (docElm.requestFullscreen) { 
                                docElm.requestFullscreen().catch(err => console.log('Fullscreen error:', err)); 
                            } else if (docElm.webkitRequestFullscreen) { 
                                docElm.webkitRequestFullscreen(); 
                            }
                        } else if (t.innerText.includes('退出全屏')) {
                            if (document.exitFullscreen) { 
                                document.exitFullscreen().catch(err => console.log('Exit error:', err)); 
                            } else if (document.webkitExitFullscreen) { 
                                document.webkitExitFullscreen(); 
                            }
                        }
                    }
                });
            `;
            parentDoc.head.appendChild(script);
        }
        </script>
        """,
        height=0,
        width=0
    )

    # ================= 沉浸式全屏与巨型按钮 CSS 注入 =================
    if st.session_state.pos_fullscreen:
        st.markdown("""
        <style>
        /* 全屏时隐藏侧边栏、顶部 Header、以及 Tab 栏 */
        [data-testid="stSidebar"] {display: none !important;}
        header {display: none !important;}
        [data-testid="stTabs"] [data-baseweb="tab-list"] {display: none !important;}
        /* 扩展主工作区宽度，消除所有多余边距 */
        .block-container {padding-top: 1rem !important; padding-bottom: 1rem !important; max-width: 100% !important;}
        </style>
        """, unsafe_allow_html=True)
        
    # 无论是否全屏，结账按钮都保持巨大
    st.markdown("""
    <style>
    /* 定位结账按钮并将其变得超大 */
    div[data-testid="stElementContainer"]:has(.checkout-btn-marker) + div[data-testid="stElementContainer"] button {
        height: 100px !important;
        min-height: 100px !important;
        border-radius: 12px !important;
    }
    div[data-testid="stElementContainer"]:has(.checkout-btn-marker) + div[data-testid="stElementContainer"] button p {
        font-size: 28px !important;
        font-weight: bold !important;
    }
    </style>
    """, unsafe_allow_html=True)
        
    c_goods, c_cart = st.columns([2.5, 1.3])
    
    # ================= 左侧：商品点击区 =================
    with c_goods:
        # 头部区域带全屏切换按钮
        c_title, c_fs_btn = st.columns([5, 1], vertical_alignment="bottom")
        c_title.markdown(f"### 🛒 {template.name} ({template.platform})")
        c_title.caption(f"出货仓库: {template.warehouse.name if template.warehouse else '未分配'}")
        
        if c_fs_btn.button("🔲 退出全屏" if st.session_state.pos_fullscreen else "🔲 全屏模式", use_container_width=True):
            st.session_state.pos_fullscreen = not st.session_state.pos_fullscreen
            st.rerun()
        
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
                        
                        # 2. 统一高度的库存状态提示
                        if is_out_of_stock:
                            st.markdown("<div style='font-size:12px; color:red; text-align:center; margin-bottom:4px; font-weight:bold;'>🚫 已售罄</div>", unsafe_allow_html=True)
                            btn_label_out = f"{item.product_name}\n{item.variant}\n🚫 暂无库存"
                            st.button(btn_label_out, key=f"btn_off_{item.id}", disabled=True, use_container_width=True)
                        else:
                            st.markdown(f"<div style='font-size:12px; color:#4caf50; text-align:center; margin-bottom:4px; font-weight:bold;'>📦 余量: {item.remaining_quantity}</div>", unsafe_allow_html=True)
                            btn_label = f"{item.product_name}\n{item.variant}\n¥ {item.preset_price:.2f} ➕"
                            if st.button(btn_label, key=f"pos_btn_{item.id}", use_container_width=True):
                                if cart_key in st.session_state.offline_cart:
                                    if st.session_state.offline_cart[cart_key]["qty"] < item.remaining_quantity:
                                        st.session_state.offline_cart[cart_key]["qty"] += 1
                                    else:
                                        st.toast("已达模板最大分配限额！", icon="⚠️")
                                else:
                                    st.session_state.offline_cart[cart_key] = {
                                        "product_name": item.product_name, "variant": item.variant,
                                        "unit_price": item.preset_price, "qty": 1
                                    }
                                st.rerun()

    # ================= 右侧：购物车与结算区 =================
    with c_cart:
        with st.container(border=True):
            st.markdown("### 🧾 结账单")
            cart_items = list(st.session_state.offline_cart.values())
            total_amount = sum(ci["qty"] * ci["unit_price"] for ci in cart_items)
            
            if not cart_items: 
                st.caption("购物车为空")
            else:
                # 渲染带微型缩略图的购物车列表
                for idx, ci in enumerate(cart_items):
                    r_img, r_c1, r_c2, r_c3 = st.columns([1.5, 3, 1, 1], vertical_alignment="center")
                    
                    img_data = image_lookup.get(f"{ci['product_name']}_{ci['variant']}")
                    if img_data:
                        r_img.image(img_data, use_container_width=True)
                    else:
                        r_img.markdown("<div style='height:30px; background:#f0f2f6; border-radius:3px;'></div>", unsafe_allow_html=True)
                        
                    r_c1.markdown(f"<span style='font-size:13px; font-weight:bold;'>{ci['product_name']}</span><br><span style='font-size:11px; color:gray;'>{ci['variant']}</span>", unsafe_allow_html=True)
                    r_c2.markdown(f"**x {ci['qty']}**")
                    
                    if r_c3.button("❌", key=f"rem_{idx}", help="移除一项"):
                        cart_key = f"{ci['product_name']}_{ci['variant']}"
                        st.session_state.offline_cart[cart_key]["qty"] -= 1
                        if st.session_state.offline_cart[cart_key]["qty"] <= 0:
                            del st.session_state.offline_cart[cart_key]
                        st.rerun()

            st.divider()
            
            # --- 触控版支付方式选择 ---
            st.markdown("**选择支付方式:**")
            c_pay1, c_pay2 = st.columns(2)
            if c_pay1.button("💵 现金", type="primary" if st.session_state.pos_pay_method == "现金" else "secondary", use_container_width=True):
                st.session_state.pos_pay_method = "现金"
                st.rerun()
            if c_pay2.button("📱 PayPay", type="primary" if st.session_state.pos_pay_method == "PayPay" else "secondary", use_container_width=True):
                st.session_state.pos_pay_method = "PayPay"
                st.rerun()
                
            pay_method = st.session_state.pos_pay_method
            fee = total_amount * 0.0198 if pay_method == "PayPay" else 0.0
            
            st.markdown(f"**小计: <span style='color:red; font-size:24px;'>{total_amount:,.2f} {template.currency}</span>**", unsafe_allow_html=True)
            if pay_method == "PayPay":
                st.markdown(
                    f"**PayPay手续费 (1.98%):** <span style='color:#4caf50;'>-{fee:,.2f} {template.currency}</span> &nbsp;➔&nbsp; "
                    f"**实收: <span style='color:red;'>{(total_amount - fee):,.2f} {template.currency}</span>**", 
                    unsafe_allow_html=True
                )
            
            # --- 收款账户智能匹配 ---
            valid_accs = [a for a in all_cash_assets if a.currency == template.currency]
            acc_opts = {a.name: a.id for a in valid_accs}
            acc_names = list(acc_opts.keys())
            target_acc_id = None
            
            if acc_names:
                default_idx = 0
                if pay_method == "现金":
                    for i, name in enumerate(acc_names):
                        if "日元临时" in name or "现金" in name:
                            default_idx = i
                            break
                elif pay_method == "PayPay":
                    for i, name in enumerate(acc_names):
                        if "paypay" in name.lower():
                            default_idx = i
                            break
                            
                sel_acc = st.selectbox("收款账户", acc_names, index=default_idx)
                target_acc_id = acc_opts[sel_acc]
            else:
                st.error(f"缺少 {template.currency} 现金账户！")
                
            st.write("") 
            # ✨ 插入隐形标记，由上方的 CSS 捕捉并放大紧随其后的按钮
            st.markdown('<div class="checkout-btn-marker"></div>', unsafe_allow_html=True)
            if st.button("✅ 完成交易", type="primary", use_container_width=True, disabled=(not cart_items or not target_acc_id)):
                try:
                    svc = OfflineSalesService(db)
                    order_no, net_in = svc.checkout_offline_order(
                        template_id=template.id, cart_items=cart_items,
                        payment_method=pay_method, fee_rate=0.0198,
                        account_id=target_acc_id
                    )
                    st.toast(f"交易成功: {net_in:.2f}", icon="💰")
                    st.session_state.offline_cart = {}
                    sync_all_caches()
                    st.rerun()
                except Exception as e:
                    st.error(f"失败: {e}")

    # ================= 底部：历史订单列表 =================
    st.divider()
    st.subheader(f"📜 [{template.name}] 历史交易")
    svc = OfflineSalesService(db)
    orders = svc.get_orders_by_template(template.code)
    if orders:
        order_data = []
        for o in orders:
            items_str = ", ".join([f"{i.product_name}-{i.variant} ×{i.quantity}" for i in o.items])
            
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