# views/finance_view.py
import streamlit as st
import pandas as pd
import math  
from datetime import date
from services.finance_service import FinanceService
from cache_manager import sync_all_caches
from constants import PRODUCT_COST_CATEGORIES

# ================= 🚀 性能优化 1：局部刷新装饰器兼容 =================
def fragment_if_available(func):
    """
    兼容性封装：将 UI 拆分为局部组件。
    当组件内的输入框改变时，只刷新组件本身，绝不重新渲染外部的大表格！
    """
    if hasattr(st, "fragment"):
        return st.fragment()(func)
    elif hasattr(st, "experimental_fragment"):
        return st.experimental_fragment()(func)
    return func

# ================= 🚀 性能优化 2：数据与表格渲染缓存 =================
@st.cache_data(ttl=300, show_spinner=False)
def get_cached_finance_data(test_mode_flag, page, cache_version):
    """
    增加了 cache_version 参数。
    只要发生增删改，cache_version 会变化，Streamlit 就会自动重新执行此函数。
    """
    db_cache = st.session_state.get_dynamic_session()
    try:
        # 调用新的真分页方法 (已内置窗口函数计算行余额)
        df_display, total_count = FinanceService.get_finance_records_page(db_cache, page=page, page_size=100)
        
        if not df_display.empty:
            df_display['收支'] = df_display['收支'].map({"收入": "🟢 收入", "支出": "🔴 支出"}).fillna(df_display['收支'])
            
        cur_cny, cur_jpy = FinanceService.get_current_balances(db_cache)
        return df_display, total_count, cur_cny, cur_jpy
    finally:
        db_cache.close()

# ================= 局部组件：新增表单 =================
@fragment_if_available
def render_add_transaction_form(exchange_rate):
    # 局部组件内使用动态分配的 session
    db_frag = st.session_state.get_dynamic_session()
    try:
        # ✨ 新增：引入动态表单版本号，用于提交成功后一键清空所有输入框和表格
        if "fin_form_ver" not in st.session_state:
            st.session_state.fin_form_ver = 0
        fv = st.session_state.fin_form_ver
        
        # 获取所有的现金账户资源
        all_cash_assets = [a for a in FinanceService.get_transferable_assets(db_frag) if getattr(a, 'asset_type', '') == "现金"]
        
        with st.expander("➕ 新增收支 / 兑换 / 债务记录", expanded=True):
            
            c_top1, c_top2 = st.columns([1, 1])
            f_date = c_top1.date_input("日期", date.today())
            rec_type = c_top2.selectbox("业务大类", ["支出", "收入", "货币兑换", "债务", "资金移动"])
            
            st.divider()

            # 初始化通用变量 (Base Data)
            base_data = {
                "date": f_date, "type": rec_type, "currency": "CNY", 
                "amount": 0.0, "category": "", "shop": "", "desc": "", "url": ""
            }
            
            # 联动配置 (Link Config)
            link_config = {
                "link_type": None, "is_new": False, "target_id": None, 
                "name": "", "qty": 1.0, "unit_price": 0.0, "product_id": None, "cat": ""
            }

            # >>>>> 场景 A: 货币兑换 <<<<<
            if rec_type == "货币兑换":
                st.markdown("##### 1. 业务分类")
                st.info("💱 货币资金互转 (不影响净资产，只改变账户余额分布)")
                
                st.markdown("##### 2. 兑换账户与方向")
                c_ex_dir1, c_ex_dir2 = st.columns([1, 1])
                
                source_curr = c_ex_dir1.selectbox("源币种 (扣款侧)", ["CNY", "JPY"])
                valid_src = [a for a in all_cash_assets if a.currency == source_curr]
                src_opts = {f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})": a.id for a in valid_src}
                if not src_opts:
                    st.warning(f"缺少 {source_curr} 现金账户，将自动创建默认账户。")
                    source_acc_id = None
                else:
                    src_acc_label = c_ex_dir1.selectbox("扣款账户", list(src_opts.keys()))
                    source_acc_id = src_opts.get(src_acc_label)

                target_curr = "JPY" if source_curr == "CNY" else "CNY"
                with c_ex_dir2:
                    st.selectbox("目标币种 (入账侧)", [target_curr], disabled=True)
                    valid_tgt = [a for a in all_cash_assets if a.currency == target_curr]
                    tgt_opts = {f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})": a.id for a in valid_tgt}
                    if not tgt_opts:
                        st.warning(f"缺少 {target_curr} 现金账户，将自动创建默认账户。")
                        target_acc_id = None
                    else:
                        tgt_acc_label = st.selectbox("入账账户", list(tgt_opts.keys()))
                        target_acc_id = tgt_opts.get(tgt_acc_label)
                
                st.markdown("##### 3. 交易金额")
                c_ex1, c_ex2 = st.columns(2)
                # ✨ 绑定 fv
                amount_out = c_ex1.number_input(f"流出金额 ({source_curr})", min_value=0.0, step=100.0, format="%.2f", key=f"ex_out_{fv}")
                est_val = amount_out / exchange_rate if source_curr == "CNY" else amount_out * exchange_rate
                amount_in = c_ex2.number_input(f"入账金额 ({target_curr})", value=est_val, min_value=0.0, step=100.0, format="%.2f", help="自动按系统汇率估算", key=f"ex_in_{fv}")
                
                st.markdown("##### 4. 附加信息")
                desc = st.text_input("备注说明", placeholder="如：支付宝购汇、信用卡日元结算账单等", key=f"ex_desc_{fv}")
                
                st.write("")
                if st.button("💾 确认兑换", type="primary", width="stretch"):
                    if amount_out <= 0 or amount_in <= 0:
                        st.warning("金额必须大于0")
                    else:
                        try:
                            FinanceService.execute_exchange(db_frag, f_date, source_curr, target_curr, amount_out, amount_in, desc, source_acc_id, target_acc_id)
                            st.toast(f"兑换成功：-{amount_out}{source_curr}, +{amount_in}{target_curr}", icon="💱")
                            st.session_state.fin_form_ver += 1 # ✨ 成功后版本号+1，一键清空输入框
                            sync_all_caches()
                            st.rerun()
                        except Exception as e:
                            st.error(f"兑换失败: {e}")

            # >>>>> 场景 B: 债务管理 <<<<<
            elif rec_type == "债务":
                st.markdown("##### 1. 业务分类")
                debt_op = st.radio("操作类型", ["➕ 新增债务 (借入资金/形成欠款)", "💸 偿还/核销债务 (还清欠款)"], horizontal=True)

                if "新增" in debt_op:
                    st.markdown("##### 2. 债务内容")
                    c_t1, c_t2 = st.columns(2)
                    d_name = c_t1.text_input("债务名称", placeholder="如：银行经营贷、欠某加工厂货款 (必填)", key=f"debt_n_{fv}")
                    
                    dest_options = ["存入流动资金 (拿到现金)", "新增资产项 (形成实物/账面资产)"]
                    dest = c_t2.selectbox("借入价值去向", dest_options)
                    is_to_cash = (dest == dest_options[0])
                    
                    if is_to_cash:
                        rel_content = ""
                    else:
                        rel_content = st.text_input("新增挂账资产名称", placeholder="如：未付款的打印机 (必填)", key=f"debt_rel_{fv}")

                    st.markdown("##### 3. 交易金额、币种与账户")
                    c_d1, c_curr = st.columns([1.5, 1])
                    d_amount = c_d1.number_input("金额", min_value=0.0, step=100.0, key=f"debt_amt_{fv}")
                    curr = c_curr.selectbox("币种", ["CNY", "JPY"])

                    target_acc_id = None
                    if is_to_cash:
                        valid_tgt = [a for a in all_cash_assets if a.currency == curr]
                        tgt_opts = {f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})": a.id for a in valid_tgt}
                        if tgt_opts:
                            acc_sel = st.selectbox("收款现金账户", list(tgt_opts.keys()))
                            target_acc_id = tgt_opts.get(acc_sel)
                        else:
                            st.warning(f"该币种 ({curr}) 暂无现金账户，系统将自动创建默认账户。")

                    st.markdown("##### 4. 附加信息")
                    c_add1, c_add2 = st.columns(2)
                    d_source = c_add1.text_input("债权人/资金来源", placeholder="如：工商银行、加工厂A", key=f"debt_src_{fv}")
                    d_remark = c_add2.text_input("备注说明", key=f"debt_rem_{fv}")

                    st.write("")
                    if st.button("💾 确认新增债务", type="primary", width="stretch"):
                        if not d_name or d_amount <= 0 or (not is_to_cash and not rel_content):
                            st.error("请填写完整必填项（债务名称、资产名称）并确保金额大于0")
                        else:
                            try:
                                FinanceService.create_debt(
                                    db_frag, f_date, curr, d_name, d_amount, d_source, d_remark, 
                                    is_to_cash=is_to_cash, related_content=rel_content, target_acc_id=target_acc_id
                                )
                                st.toast("债务记录成功", icon="📝")
                                st.session_state.fin_form_ver += 1
                                sync_all_caches()
                                st.rerun()
                            except Exception as e:
                                st.error(f"保存失败: {e}")
                else:
                    st.markdown("##### 2. 债务内容")
                    liabs = FinanceService.get_balance_items(db_frag, "liability")
                    if not liabs:
                        st.warning("✅ 当前无记录在案的未结债务。")
                    else:
                        liab_map = {f"{l.name} (待还余额: {l.amount})" : l.id for l in liabs}
                        sel_label = st.selectbox("选择要处理的债务", list(liab_map.keys()))
                        sel_id = liab_map[sel_label]
                        
                        target_liab = next((l for l in liabs if l.id == sel_id), None)
                        curr = target_liab.currency if target_liab else "CNY"
                        max_repay = float(target_liab.amount) if target_liab else None
                        
                        st.markdown("##### 3. 交易金额与方式")
                        repay_type = st.radio("偿还方式", ["💸 资金还款 (扣除账户现金)", "🔄 资产抵消 (划扣其他资产抵债)"], horizontal=True)
                        
                        if "资金" in repay_type:
                            c_r1, c_curr = st.columns([1.5, 1])
                            amt = c_r1.number_input("偿还金额", min_value=0.0, step=100.0, max_value=max_repay, value=max_repay, key=f"repay_amt_{fv}")
                            c_curr.info(f"结算币种: **{curr}**")
                            
                            source_acc_id = None
                            valid_src = [a for a in all_cash_assets if a.currency == curr]
                            src_opts = {f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})": a.id for a in valid_src}
                            if src_opts:
                                acc_sel = st.selectbox("扣款现金账户", list(src_opts.keys()))
                                source_acc_id = src_opts.get(acc_sel)
                            else:
                                st.warning(f"该币种 ({curr}) 暂无现金账户，系统将自动扣减默认账户。")
                            
                            st.markdown("##### 4. 附加信息")
                            rem = st.text_input("备注说明", placeholder="选填", key=f"repay_rem_{fv}")
                            
                            st.write("")
                            if st.button("💾 确认资金还款", type="primary", width="stretch"):
                                try:
                                    FinanceService.repay_debt(db_frag, f_date, sel_id, amt, rem, source_acc_id)
                                    st.toast("还款成功", icon="💸")
                                    st.session_state.fin_form_ver += 1
                                    sync_all_caches()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"失败: {e}")
                        else:
                            assets = FinanceService.get_balance_items(db_frag, "asset")
                            asset_map = {f"{a.name} (余:{a.amount})" : a.id for a in assets}
                            
                            c_a1, c_a2 = st.columns([2, 1.5])
                            asset_label = c_a1.selectbox("选择用于抵消的资产", list(asset_map.keys()))
                            amt = c_a2.number_input("用于抵消的账面金额", min_value=0.0, max_value=max_repay, value=max_repay, key=f"off_amt_{fv}")
                            
                            st.markdown("##### 4. 附加信息")
                            rem = st.text_input("备注说明", placeholder="选填", key=f"off_rem_{fv}")
                            
                            st.write("")
                            if st.button("💾 确认资产抵消", type="primary", width="stretch"):
                                try:
                                    FinanceService.offset_debt(db_frag, f_date, sel_id, asset_map[asset_label], amt, rem)
                                    st.toast("抵消成功", icon="🔄")
                                    st.session_state.fin_form_ver += 1
                                    sync_all_caches()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"失败: {e}")

            # >>>>> 场景 C: 普通收入 / 支出 <<<<<
            elif rec_type == "收入" or rec_type == "支出" :
                # --- 1. 业务分类 ---
                st.markdown("##### 1. 业务分类")
                c_cat1, _ = st.columns(2)
                if rec_type == "收入":
                    cats = ["销售收入", "退款", "投资", "现有资产增加", "其他资产增加", "新资产增加", "其他现金收入"]
                    base_data["category"] = c_cat1.selectbox("收入细分类型", cats)
                else:
                    cats = ["商品成本", "固定资产购入", "其他资产购入", "撤资", "现有资产减少", "其他"]
                    base_data["category"] = c_cat1.selectbox("支出细分类型", cats)

                cat = base_data["category"]

                # ================= 专属：批量录入 / 匹配预算 交互区域 =================
                if rec_type == "支出" and cat in ["商品成本", "固定资产购入", "其他资产购入"]:
                    st.markdown("##### 2. 共同设置 (共用信息)")
                    batch_config = {}
                    c_share1, c_share2 = st.columns(2)
                    
                    budget_options = {"➕ 不匹配预算 (批量录入新成本)": None}
                    
                    if cat == "商品成本":
                        products = FinanceService.get_all_products(db_frag)
                        p_opts = {p.id: p.name for p in products}
                        batch_config["product_id"] = c_share1.selectbox("归属商品", list(p_opts.keys()), format_func=lambda x: p_opts[x])
                        batch_config["cost_cat"] = c_share2.selectbox("共同成本分类", PRODUCT_COST_CATEGORIES)
                        
                        # 动态获取当前选定商品及分类下的预算项
                        budgets = FinanceService.get_budget_items(db_frag, batch_config["product_id"], batch_config["cost_cat"])
                        for b in budgets:
                            budget_options[f"匹配预算: {b.item_name}"] = b.id
                            
                    elif cat == "其他资产购入":
                        batch_config["asset_cat"] = c_share1.selectbox("资产子分类", ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"], index=0)
                        
                    c_share3, c_share4 = st.columns(2)
                    batch_config["shop"] = c_share3.text_input("收款方/店铺名称", placeholder="如：某淘宝店", key=f"b_shop_{fv}")
                    batch_config["currency"] = c_share4.selectbox("币种", ["CNY", "JPY"])
                    
                    valid_accs = [a for a in all_cash_assets if a.currency == batch_config["currency"]]
                    acc_opts = {f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})": a.id for a in valid_accs}
                    
                    if not acc_opts:
                        st.warning(f"该币种 ({batch_config['currency']}) 暂无现金账户。")
                        batch_config["account_id"] = None
                    else:
                        acc_names = list(acc_opts.keys())
                        default_idx = 0
                        
                        # 批量录入肯定是支出，直接根据币种匹配关键词
                        for i, name in enumerate(acc_names):
                            if batch_config["currency"] == "CNY" and "支付宝" in name:
                                default_idx = i
                                break
                            elif batch_config["currency"] == "JPY" and "日元银行" in name:
                                default_idx = i
                                break
                                
                        sel_acc = st.selectbox("操作账户", acc_names, index=default_idx)
                        batch_config["account_id"] = acc_opts.get(sel_acc)

                    # ================= 逻辑分流：是否匹配了预算？ =================
                    selected_budget_id = None
                    if cat == "商品成本":
                        sel_budget_label = st.selectbox("🎯 预算项目匹配", list(budget_options.keys()))
                        selected_budget_id = budget_options[sel_budget_label]

                    if selected_budget_id is not None:
                        # ---------------- 模式 A: 单条记录匹配预算 ----------------
                        st.info(f"✅ 当前模式：将实付金额累加至预算 **{sel_budget_label.replace('匹配预算: ', '')}**。此模式下不支持批量拆单和单独列出邮费。")
                        st.markdown("##### 3. 实付金额与明细")
                        c_s1, c_s2 = st.columns(2)
                        single_amount = c_s1.number_input("实付总额", min_value=0.0, step=10.0, format="%.2f", key=f"s_amt_{fv}")
                        single_qty = c_s2.number_input("数量", min_value=0.01, value=1.0, key=f"s_qty_{fv}")
                        
                        c_s3, c_s4 = st.columns(2)
                        single_desc = c_s3.text_input("具体成本内容/备注", placeholder="选填，将追加至原备注后", key=f"s_desc_{fv}")
                        single_url = c_s4.text_input("购入页面网址", placeholder="选填", key=f"s_url_{fv}")
                        
                        st.write("")
                        if st.button("💾 确认记账 (匹配预算)", type="primary", width="stretch"):
                            if single_amount <= 0:
                                st.warning("⚠️ 金额必须大于0")
                            elif batch_config["account_id"] is None:
                                st.warning("⚠️ 请先建立并选择账户。")
                            else:
                                base_data = {
                                    "date": f_date, "type": "支出", "currency": batch_config["currency"], 
                                    "amount": single_amount, "category": cat, "shop": batch_config["shop"], 
                                    "desc": single_desc, "url": single_url, "account_id": batch_config["account_id"]
                                }
                                link_config = {
                                    "link_type": "cost", "target_cost_id": selected_budget_id,
                                    "name": sel_budget_label.replace("匹配预算: ", ""), 
                                    "qty": single_qty, "unit_price": single_amount / single_qty if single_qty else 0, 
                                    "product_id": batch_config["product_id"], "cat": batch_config["cost_cat"]
                                }
                                try:
                                    msg = FinanceService.create_general_transaction(db_frag, base_data, link_config, exchange_rate)
                                    st.toast(f"记账成功！{msg}", icon="✅")
                                    st.session_state.fin_form_ver += 1
                                    sync_all_caches()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"写入失败: {e}")

                    else:
                        # ---------------- 模式 B: 批量录入模式 ----------------
                        batch_config["shipping_fee"] = st.number_input("共同邮费金额", min_value=0.0, step=10.0, format="%.2f", key=f"b_ship_{fv}")
                        
                        st.markdown("##### 3. 购入物品明细 (可批量录入)")
                        st.caption("您可以新增多行，每行代表一个独立的物品记录。")
                        
                        # ✨ 使用带有版本的 key 初始化 DataFrame，这样版本号一旦 +1，旧的表自动被丢弃并重置！
                        editor_state_key = f"batch_editor_state_{cat}_{fv}"
                        if editor_state_key not in st.session_state:
                            st.session_state[editor_state_key] = pd.DataFrame([{
                                "内容/名称": "", "实付金额": 0.0, "数量": 1.0, "备注": "", "网址": ""
                            }])
                            
                        edited_items = st.data_editor(
                            st.session_state[editor_state_key], 
                            num_rows="dynamic", 
                            width="stretch", 
                            key=f"de_{editor_state_key}", # 绑定对应的 key
                            column_config={
                                "内容/名称": st.column_config.TextColumn(required=True),
                                "实付金额": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                                "数量": st.column_config.NumberColumn(min_value=0.01),
                            }
                        )
                        
                        # 过滤掉空行，安全地计算实付金额列的总和
                        valid_calc_rows = edited_items[edited_items["内容/名称"].str.strip() != ""]
                        items_sum = pd.to_numeric(valid_calc_rows["实付金额"], errors='coerce').fillna(0.0).sum()
                        shipping_fee = batch_config["shipping_fee"]
                        total_with_shipping = items_sum + shipping_fee
                        
                        # 使用 HTML 渲染一个醒目的总结算面板
                        st.markdown(
                            f"<div style='padding: 12px; background-color: rgba(33, 150, 243, 0.1); "
                            f"border-radius: 8px; border-left: 5px solid #2196F3; margin-top: 10px; margin-bottom: 15px;'>"
                            f"<div style='font-size: 14px; color: #aaa; margin-bottom: 5px;'>"
                            f"🧾 物品小计: <b>{items_sum:,.2f}</b> {batch_config['currency']} &nbsp;&nbsp;|&nbsp;&nbsp; "
                            f"📦 共同邮费: <b>{shipping_fee:,.2f}</b> {batch_config['currency']}</div>"
                            f"<div style='font-size: 18px; font-weight: bold; color: #4fc3f7;'>"
                            f"💰 订单扣款总计: {total_with_shipping:,.2f} {batch_config['currency']}</div>"
                            f"</div>", 
                            unsafe_allow_html=True
                        )

                        st.write("")
                        if st.button("💾 保存/记账", type="primary", width="stretch"):
                            valid_rows = edited_items[edited_items["内容/名称"].str.strip() != ""]
                            if valid_rows.empty and batch_config["shipping_fee"] <= 0:
                                st.warning("⚠️ 请至少填写一项购入明细，或输入邮费。")
                            elif batch_config["account_id"] is None:
                                st.warning("⚠️ 请先建立并选择账户。")
                            else:
                                try:
                                    items_data = []
                                    for _, row in valid_rows.iterrows():
                                        items_data.append({
                                            "name": str(row["内容/名称"]).strip(),
                                            "amount": float(row["实付金额"]),
                                            "qty": float(row["数量"]),
                                            "desc": str(row["备注"]).strip() if pd.notna(row["备注"]) else "",
                                            "url": str(row["网址"]).strip() if pd.notna(row["网址"]) else ""
                                        })
                                        
                                    base_data = {
                                        "date": f_date,
                                        "currency": batch_config["currency"],
                                        "account_id": batch_config["account_id"],
                                        "shop": batch_config["shop"],
                                        "category": cat
                                    }
                                    
                                    msg = FinanceService.create_batch_expense_transaction(
                                        db_frag, base_data, batch_config, items_data, exchange_rate
                                    )
                                    st.toast(f"{msg}", icon="✅")
                                    st.session_state.fin_form_ver += 1 # ✨ 一键重置清空
                                    sync_all_caches()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"写入失败: {e}")

                # ================= 普通单项录入区域 (其他类型，如：投资、其他支出) =================
                else:
                    # --- 2. 业务内容 ---
                    st.markdown("##### 2. 业务内容")
                    needs_qty = False
                    
                    if cat == "投资":
                        equities = FinanceService.get_balance_items(db_frag, "equity")
                        eq_opts = ["➕ 新增资本项目"] + [e.name for e in equities]
                        c_eq1, c_eq2 = st.columns([1.5, 2])
                        sel_eq = c_eq1.selectbox("投资归属项目", eq_opts)
                        
                        link_config["link_type"] = "equity"
                        if sel_eq == "➕ 新增资本项目":
                            link_config["is_new"] = True
                            link_config["name"] = c_eq2.text_input("新资本项目名称", placeholder="如：股东A注资 (必填)", key=f"inv_n_{fv}")
                        else:
                            target = next(e for e in equities if e.name == sel_eq)
                            link_config["target_id"] = target.id
                            link_config["name"] = target.name
                            
                    elif cat == "撤资":
                        link_config["link_type"] = "equity"
                        equities = FinanceService.get_balance_items(db_frag, "equity")
                        if not equities:
                            st.warning("当前无资本项目可撤资")
                            st.stop()
                        sel_eq = st.selectbox("选择撤资项目", [e.name for e in equities])
                        target = next(e for e in equities if e.name == sel_eq)
                        link_config["target_id"] = target.id
                        link_config["name"] = target.name

                    elif cat == "其他资产增加":
                        needs_qty = True
                        link_config["link_type"] = "consumable"
                        link_config["name"] = st.text_input("新增资产名称", placeholder="如：纸箱、不干胶 (必填)", key=f"oa_n_{fv}")

                    elif cat == "现有资产增加":
                        link_config["link_type"] = "manual_asset"
                        assets = FinanceService.get_balance_items(db_frag, "asset")
                        valid_assets = [a for a in assets if not a.name.startswith(("在制", "预入库", "流动资金"))]
                        if not valid_assets:
                            st.warning("暂无有效的手动资产项目")
                            st.stop()
                        sel_asset = st.selectbox("选择现有资产", [a.name for a in valid_assets])
                        target = next(a for a in valid_assets if a.name == sel_asset)
                        link_config["target_id"] = target.id
                        link_config["name"] = target.name

                    elif cat == "新资产增加":
                        link_config["link_type"] = "manual_asset"
                        link_config["is_new"] = True
                        c_na1, c_na2 = st.columns(2)
                        link_config["name"] = c_na1.text_input("新资产名称", placeholder="如：支付宝备用金 (必填)", key=f"na_n_{fv}")
                        link_config["asset_type"] = c_na2.selectbox("资产属性", ["现金", "资产"], help="只有标为'现金'的资产才能进行资金移动")

                    elif cat == "现有资产减少":
                        link_config["link_type"] = "manual_asset"
                        assets = FinanceService.get_balance_items(db_frag, "asset")
                        valid_assets = [a for a in assets if not a.name.startswith(("在制", "预入库", "流动资金"))]
                        if not valid_assets:
                            st.warning("暂无有效的手动资产项目")
                            st.stop()
                        sel_asset = st.selectbox("选择要减少的资产", [a.name for a in valid_assets])
                        target = next(a for a in valid_assets if a.name == sel_asset)
                        link_config["target_id"] = target.id
                        link_config["name"] = target.name

                    else:
                        link_config["name"] = st.text_input("收支明细描述", placeholder="如：顺丰快递费、工作餐补 (必填)", key=f"gen_n_{fv}")

                    # --- 3. 交易金额、数量与账户 ---
                    st.markdown("##### 3. 交易金额、数量与账户")
                    
                    if needs_qty:
                        c_amt1, c_curr, c_qty = st.columns([1.5, 1, 1.5])
                        amt_label = "收入总额" if rec_type == "收入" else "实付总额"
                        base_data["amount"] = c_amt1.number_input(amt_label, min_value=0.0, step=10.0, format="%.2f", key=f"gen_amt_{fv}")
                        base_data["currency"] = c_curr.selectbox("币种", ["CNY", "JPY"])
                        link_config["qty"] = c_qty.number_input("数量", min_value=0.01, value=1.0, key=f"gen_qty_{fv}")
                        link_config["unit_price"] = base_data["amount"] / link_config["qty"] if link_config["qty"] else 0
                    else:
                        c_amt1, c_curr, _ = st.columns([1.5, 1, 1.5])
                        amt_label = "收入金额" if rec_type == "收入" else "支出金额"
                        base_data["amount"] = c_amt1.number_input(amt_label, min_value=0.0, step=10.0, format="%.2f", key=f"gen_amt_noq_{fv}")
                        base_data["currency"] = c_curr.selectbox("币种", ["CNY", "JPY"])

                    valid_accs = [a for a in all_cash_assets if a.currency == base_data["currency"]]
                    acc_opts = {f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})": a.id for a in valid_accs}
                    
                    if not acc_opts:
                        st.warning(f"该币种 ({base_data['currency']}) 暂无现金账户，系统将自动创建默认账户。")
                        base_data["account_id"] = None
                    else:
                        acc_names = list(acc_opts.keys())
                        default_idx = 0
                        
                        # 判断如果是支出，再去匹配关键词
                        if rec_type == "支出":
                            for i, name in enumerate(acc_names):
                                if base_data["currency"] == "CNY" and "支付宝" in name:
                                    default_idx = i
                                    break
                                elif base_data["currency"] == "JPY" and "日元银行" in name:
                                    default_idx = i
                                    break
                                    
                        sel_acc = st.selectbox("入账账户" if rec_type == "收入" else "操作账户", acc_names, index=default_idx)
                        base_data["account_id"] = acc_opts.get(sel_acc)

                    # --- 4. 附加信息 ---
                    st.markdown("##### 4. 附加信息")
                    c_add1, c_add2 = st.columns(2)
                    shop_label = "付款人/资金来源" if rec_type == "收入" else "收款方/店铺名称"
                    base_data["shop"] = c_add1.text_input(shop_label, placeholder="选填", key=f"gen_shop_{fv}")
                    base_data["desc"] = c_add2.text_input("其他备注", placeholder="选填，如：型号颜色详情等", key=f"gen_desc_{fv}")
                    base_data["url"] = st.text_input("相关页面网址", placeholder="选填", key=f"gen_url_{fv}")
                    
                    # 防空容错处理
                    if not link_config.get("name") and cat in ["销售收入", "退款", "其他现金收入", "其他"]:
                        link_config["name"] = base_data["desc"] or cat 
                        
                    st.write("")
                    if st.button("💾 确认记账", type="primary", width="stretch"):
                        if base_data["amount"] <= 0:
                            st.warning("⚠️ 金额必须大于0")
                        elif not link_config.get("name") and not base_data.get("desc"):
                            st.warning("⚠️ 请填写具体的业务内容或备注")
                        else:
                            try:
                                msg = FinanceService.create_general_transaction(db_frag, base_data, link_config, exchange_rate)
                                st.toast(f"记账成功！{msg}", icon="✅")
                                st.session_state.fin_form_ver += 1
                                sync_all_caches()
                                st.rerun()
                            except Exception as e:
                                st.error(f"写入失败: {e}")
            
            # >>>>> 场景 D: 资金移动 <<<<<
            elif rec_type == "资金移动":
                st.markdown("##### 1. 业务分类")
                st.info("🔄 资金移动 (将同币种资金从一项资产转移到另一项，内部划转不影响总净资产)")
                
                if len(all_cash_assets) < 2:
                    st.warning("⚠️ 当前现金账户不足 2 个，无法进行移动操作。")
                else:
                    st.markdown("##### 2. 资金移动方向")
                    
                    def format_asset(a):
                        return f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})"
                        
                    from_options = {format_asset(a): a for a in all_cash_assets}
                    from_label = st.selectbox("转出账户 (移动前项目)", list(from_options.keys()), key="fund_from")
                    from_asset = from_options[from_label]
                    
                    to_assets = [a for a in all_cash_assets if a.currency == from_asset.currency and a.id != from_asset.id]
                    
                    if not to_assets:
                        st.warning(f"⚠️ 找不到其他 {from_asset.currency} 账户，无法完成该币种的移动。")
                    else:
                        to_options = {format_asset(a): a for a in to_assets}
                        to_label = st.selectbox("转入账户 (移动后项目)", list(to_options.keys()), key="fund_to")
                        to_asset = to_options[to_label]
                        
                        st.markdown("##### 3. 移动金额与余额预览")
                        amount = st.number_input(
                            f"移动金额 ({from_asset.currency})", 
                            min_value=0.0, 
                            max_value=float(from_asset.amount),
                            step=100.0 if from_asset.currency == "CNY" else 1000.0, 
                            format="%.2f",
                            key=f"trans_amt_{fv}"
                        )
                        
                        if amount > 0:
                            c_prev1, c_prev2 = st.columns(2)
                            c_prev1.success(f"📉 **{from_asset.name}** 移动后预览: {(from_asset.amount - amount):,.2f} {from_asset.currency}")
                            c_prev2.success(f"📈 **{to_asset.name}** 移动后预览: {(to_asset.amount + amount):,.2f} {to_asset.currency}")
                            
                        st.markdown("##### 4. 附加信息")
                        desc = st.text_input("备注说明", placeholder="如：将流动资金投入到某项目储备金中", key=f"trans_rem_{fv}")
                        
                        st.write("")
                        if st.button("💾 确认移动", type="primary", use_container_width=True):
                            if amount <= 0:
                                st.error("移动金额必须大于 0！")
                            else:
                                try:
                                    FinanceService.execute_fund_transfer(
                                        db_frag, f_date, from_asset.id, to_asset.id, amount, desc
                                    )
                                    st.toast(f"资金移动成功：{amount} {from_asset.currency}", icon="🔄")
                                    st.session_state.fin_form_ver += 1
                                    sync_all_caches()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"移动失败: {e}")
    finally:
        db_frag.close()

# ================= 局部组件：编辑与删除 =================
@fragment_if_available
def render_edit_delete_panel(df_render):
    db_frag = st.session_state.get_dynamic_session()
    try:
        c_edit, c_del = st.columns([1, 1])
        
        # 直接使用当前页展示的数据（最多100条），完美解决下拉框卡顿，且做到“所见即所改”
        record_options = df_render.to_dict('records')

        with c_edit:
            with st.popover("✏️ 编辑当前页记录", width="stretch"):
                if record_options:
                    sel = st.selectbox("选择要修改的记录", record_options, format_func=lambda x: f"{x['日期']} | {x['收支']} {x['金额']} | {x['备注']}")
                    if sel:
                        with st.form(key=f"edit_{sel['ID']}"):
                            
                            # ✨ 【补全代码】在这里实时查询所有的现金账户，生成 acc_opts 字典
                            all_cash_assets = [a for a in FinanceService.get_transferable_assets(db_frag) if getattr(a, 'asset_type', '') == "现金"]
                            acc_opts = {f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})": a.id for a in all_cash_assets}

                            # ✨ 提前查出这笔流水原本的账户，以便在下拉框中默认选中
                            rec_detail = FinanceService.get_record_by_id(db_frag, sel['ID'])
                            current_acc_id = rec_detail.account_id if rec_detail else None
                            
                            acc_list = list(acc_opts.keys())
                            default_idx = 0
                            for i, label in enumerate(acc_list):
                                if acc_opts[label] == current_acc_id:
                                    default_idx = i
                                    break

                            n_date = st.date_input("日期", value=sel['日期'])
                            
                            # ✨ 将下拉框改为：收支类型 + 选择具体账户（币种由账户决定，防止错乱）
                            c1, c2 = st.columns([1, 2])
                            n_type = c1.selectbox("类型", ["收入", "支出"], index=0 if "收入" in sel['收支'] else 1)
                            n_acc_label = c2.selectbox("操作账户", acc_list, index=default_idx)
                            
                            n_amt = st.number_input("金额", value=float(sel['金额']), min_value=0.0)
                            n_cat = st.text_input("分类", value=sel['分类'])
                            n_desc = st.text_input("备注", value=sel['备注'])
                            n_url = st.text_input("购入页面网址", value=sel.get('网址', ''))
                            
                            if st.form_submit_button("保存修改", type="primary"):
                                updates = {
                                    "date": n_date, "type": n_type, 
                                    "amount_abs": n_amt, "category": n_cat, "desc": n_desc,
                                    "url": n_url,
                                    "account_id": acc_opts.get(n_acc_label) # ✨ 传回指定的账户ID
                                }
                                try:
                                    if FinanceService.update_record(db_frag, sel['ID'], updates):
                                        st.toast("已修改", icon="💾")
                                        sync_all_caches()
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"修改失败: {e}")

        with c_del:
            with st.popover("🗑️ 删除当前页记录", width="stretch"):
                if record_options:
                    sel = st.selectbox("选择要删除的记录", record_options, format_func=lambda x: f"{x['日期']} | {x['金额']} | {x['备注']}")
                    
                    if sel:
                        # 如果是销售收入，则禁用删除按钮并给出提示
                        if sel.get('分类') == "销售收入":
                            st.error("⚠️ 核心业务保护：【销售收入】类型的流水不可在此处直接删除。请前往【线上销售管理】界面撤销或删除对应的订单，系统会自动同步扣除此笔流水。")
                            st.button("确认删除", width="stretch", type="primary", disabled=True)
                        else:
                            if st.button("确认删除", width="stretch", type="primary"):
                                try:
                                    msg = FinanceService.delete_record(db_frag, sel['ID'])
                                    if msg is not False:
                                        st.toast(f"已删除，关联数据回滚: {msg}", icon="🗑️")
                                        sync_all_caches() 
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"删除失败: {e}")
    finally:
        db_frag.close()

# ================= 主页面入口 =================
def show_finance_page(db, exchange_rate):
    st.header("💰 财务流水")
    
    # --- 1. 独立渲染的表单，隔离打字卡顿 ---
    render_add_transaction_form(exchange_rate)
    
    # 获取缓存版本号
    cache_version = st.session_state.get("global_cache_version", 0)
    test_mode = st.session_state.get("test_mode", False)

    # === 初始化当前页码 ===
    if "finance_page" not in st.session_state:
        st.session_state.finance_page = 1
    current_page = st.session_state.finance_page
    
    # --- 2. 获取缓存的当页表格数据 (秒开) ---
    with st.spinner("加载流水历史中..."):
        # 每次翻页，或者 cache_version 更新，这里都会秒级拉取
        df_render, total_rows, cur_cny, cur_jpy = get_cached_finance_data(test_mode, current_page, cache_version)

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("CNY 当前余额", f"¥ {cur_cny:,.2f}")
    m2.metric("JPY 当前余额", f"¥ {cur_jpy:,.0f}")
    m3.metric("JPY 折合 CNY", f"¥ {cur_jpy * exchange_rate:,.2f}", help=f"实时汇率设置: {exchange_rate*100:.1f}")
    m4.metric("账户总余额 (CNY)", f"¥ {(cur_cny + cur_jpy * exchange_rate):,.2f}")

    # --- 3. 渲染原生表格 ---
    if not df_render.empty:
        st.subheader("📜 流水明细")
        
        PAGE_SIZE = 100
        total_pages = math.ceil(total_rows / PAGE_SIZE)

        # 容错：如果删除了数据导致总页数变少，自动跳回
        if st.session_state.finance_page > total_pages and total_pages > 0:
            st.session_state.finance_page = total_pages
            st.rerun()

        st.caption(f"共计 **{total_rows}** 条记录。")

        # 渲染截取后的当页表格 (这里保留了“当前CNY余额”和“当前JPY余额”列)
        st.dataframe(
            df_render, 
            width="stretch", 
            hide_index=True, 
            height=600, 
            column_config={
                "ID": None,
                "日期": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "收支": st.column_config.TextColumn("收支类型"),
                "金额": st.column_config.NumberColumn(format="¥ %.2f"),
                "网址": st.column_config.LinkColumn("相关链接", display_text="🔗 URL"),
                "当前CNY余额": st.column_config.NumberColumn(format="¥ %.2f"),
                "当前JPY余额": st.column_config.NumberColumn(format="¥ %.0f")
            }
        )

        # === 渲染分页按钮 ===
        if total_pages > 1:
            col_btn1, col_btn2, col_page, col_btn3, col_btn4 = st.columns([1, 1, 2, 1, 1])
            with col_btn2:
                if st.button("⬅️ 上一页", disabled=(current_page == 1), use_container_width=True):
                    st.session_state.finance_page -= 1
                    st.rerun()
            with col_page:
                st.markdown(f"<div style='text-align: center; padding-top: 5px; color: #555;'>第 <b>{current_page}</b> / {total_pages} 页</div>", unsafe_allow_html=True)
            with col_btn3:
                if st.button("下一页 ➡️", disabled=(current_page == total_pages), use_container_width=True):
                    st.session_state.finance_page += 1
                    st.rerun()

        st.divider()
        # --- 4. 独立渲染的编辑删除模块 ---
        # df_render 已经是当页的数据了，直接传入即可
        render_edit_delete_panel(df_render)
    else:
        st.info("暂无记录")