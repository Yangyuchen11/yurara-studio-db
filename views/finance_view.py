# views/finance_view.py
import streamlit as st
import pandas as pd
from datetime import date
from services.finance_service import FinanceService

def show_finance_page(db, exchange_rate):
    # ================= 0. 全局样式优化 =================
    st.markdown("""
        <style>
            ::-webkit-scrollbar { width: 12px; height: 12px; }
            ::-webkit-scrollbar-track { background: #f0f2f6; border-radius: 6px; }
            ::-webkit-scrollbar-thumb { background: #888888; border-radius: 6px; }
            ::-webkit-scrollbar-thumb:hover { background: #555555; }
            * { scrollbar-width: thin; scrollbar-color: #888888 #f0f2f6; }
        </style>
    """, unsafe_allow_html=True)
    st.header("💰 财务流水")
    
    # ================= 1. 新增记录区域 =================
    with st.expander("➕ 新增收支/兑换/债务记录", expanded=True):
        r1_c1, r1_c2, r1_c3 = st.columns([1, 1, 1])
        f_date = r1_c1.date_input("日期", date.today())
        rec_type = r1_c2.selectbox("业务类型", ["支出", "收入", "货币兑换", "债务"])

        # 初始化通用变量 (Base Data)
        base_data = {
            "date": f_date,
            "type": rec_type,
            "currency": "CNY",
            "amount": 0.0,
            "category": "",
            "shop": "",
            "desc": ""
        }
        
        # 联动配置 (Link Config)
        link_config = {
            "link_type": None,
            "is_new": False,
            "target_id": None,
            "name": "",
            "qty": 1.0,
            "unit_price": 0.0,
            "product_id": None,
            "cat": ""
        }

        # >>>>> 场景 C: 货币兑换 <<<<<
        if rec_type == "货币兑换":
            with r1_c3:
                source_curr = st.selectbox("源币种 (支出)", ["CNY", "JPY"])
            target_curr = "JPY" if source_curr == "CNY" else "CNY"
            st.info(f"💱 兑换方向: {source_curr} ➡️ {target_curr}")
            
            c_ex1, c_ex2 = st.columns(2)
            amount_out = c_ex1.number_input(f"支出金额 ({source_curr})", min_value=0.0, step=100.0, format="%.2f")
            
            est_val = amount_out / exchange_rate if source_curr == "CNY" else amount_out * exchange_rate
            amount_in = c_ex2.number_input(f"入账金额 ({target_curr})", value=est_val, min_value=0.0, step=100.0, format="%.2f")
            desc = st.text_input("备注说明", placeholder="如：支付宝购汇")
            
            if st.button("💾 确认兑换", type="primary"):
                if amount_out <= 0 or amount_in <= 0:
                    st.warning("金额必须大于0")
                else:
                    try:
                        FinanceService.execute_exchange(db, f_date, source_curr, target_curr, amount_out, amount_in, desc)
                        st.toast(f"兑换成功：-{amount_out}{source_curr}, +{amount_in}{target_curr}", icon="💱")
                        st.rerun()
                    except Exception as e:
                        st.error(f"兑换失败: {e}")

        # >>>>> 场景 D: 债务管理 <<<<<
        elif rec_type == "债务":
            with r1_c3:
                curr = st.selectbox("币种", ["CNY", "JPY"])
            debt_op = st.radio("债务操作", ["➕ 新增债务 (借入)", "💸 偿还/核销债务"], horizontal=True)
            st.divider()

            if "新增" in debt_op:
                c_t1, c_t2 = st.columns([1, 2])
                dest = c_t1.selectbox("资金去向", ["存入流动资金", "新增资产项"])
                
                c_d1, c_d2 = st.columns(2)
                d_name = c_d1.text_input("债务名称", placeholder="如：银行贷款")
                
                if dest == "存入流动资金":
                    rel_content = c_d2.text_input("入账说明", placeholder="如：贷款现金入账")
                else:
                    rel_content = c_d2.text_input("新增资产名称", placeholder="如：未付款的设备")

                c_d3, c_d4 = st.columns(2)
                d_source = c_d3.text_input("债务来源", placeholder="债权人")
                d_amount = c_d4.number_input("金额", min_value=0.0, step=100.0)
                d_remark = st.text_input("备注说明")

                if st.button("💾 确认新增", type="primary"):
                    if not d_name or not rel_content or d_amount <= 0:
                        st.error("请填写完整信息")
                    else:
                        try:
                            FinanceService.create_debt(
                                db, f_date, curr, d_name, d_amount, d_source, d_remark, 
                                is_to_cash=(dest=="存入流动资金"), related_content=rel_content
                            )
                            st.toast("债务记录成功", icon="📝")
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存失败: {e}")
            else:
                # 偿还
                liabs = FinanceService.get_balance_items(db, "liability")
                if not liabs:
                    st.warning("暂无债务")
                else:
                    liab_map = {f"{l.name} (余:{l.amount})" : l.id for l in liabs}
                    sel_label = st.selectbox("选择债务", list(liab_map.keys()))
                    sel_id = liab_map[sel_label]
                    
                    st.divider()
                    repay_type = st.radio("方式", ["💸 资金还款", "🔄 资产抵消"])
                    
                    if "资金" in repay_type:
                        c_r1, c_r2 = st.columns(2)
                        amt = c_r1.number_input("金额", min_value=0.0, step=100.0)
                        rem = c_r2.text_input("备注")
                        if st.button("确认还款", type="primary"):
                            try:
                                FinanceService.repay_debt(db, f_date, sel_id, amt, rem)
                                st.toast("还款成功", icon="💸")
                                st.rerun()
                            except Exception as e:
                                st.error(f"失败: {e}")
                    else:
                        assets = FinanceService.get_balance_items(db, "asset")
                        asset_map = {f"{a.name} (余:{a.amount})" : a.id for a in assets}
                        c1, c2 = st.columns(2)
                        asset_label = c1.selectbox("选择资产", list(asset_map.keys()))
                        amt = c2.number_input("抵消金额", min_value=0.0)
                        rem = st.text_input("备注")
                        if st.button("确认抵消", type="primary"):
                            try:
                                FinanceService.offset_debt(db, f_date, sel_id, asset_map[asset_label], amt, rem)
                                st.toast("抵消成功", icon="🔄")
                                st.rerun()
                            except Exception as e:
                                st.error(f"失败: {e}")

        # >>>>> 场景 A & B: 普通收支 <<<<<
        else:
            with r1_c3:
                base_data["currency"] = st.selectbox("币种", ["CNY", "JPY"])

            # --- A. 收入 ---
            if rec_type == "收入":
                cats = ["销售收入", "退款", "投资", "现有资产增加", "其他资产增加", "新资产增加", "其他现金收入"]
                base_data["category"] = st.selectbox("收入分类", cats)
                
                if base_data["category"] == "投资":
                    equities = FinanceService.get_balance_items(db, "equity")
                    eq_opts = ["➕ 新增资本项目"] + [e.name for e in equities]
                    c_eq1, c_eq2 = st.columns([2, 1])
                    sel_eq = c_eq1.selectbox("选择项目", eq_opts)
                    
                    link_config["link_type"] = "equity"
                    if sel_eq == "➕ 新增资本项目":
                        link_config["is_new"] = True
                        link_config["name"] = c_eq2.text_input("新名称")
                    else:
                        target = next(e for e in equities if e.name == sel_eq)
                        link_config["target_id"] = target.id
                        link_config["name"] = target.name
                        
                    base_data["amount"] = st.number_input("金额", min_value=0.0)

                elif base_data["category"] == "其他资产增加":
                    link_config["link_type"] = "consumable"
                    c1, c2 = st.columns([1.5, 1])
                    link_config["name"] = c1.text_input("项目名")
                    base_data["shop"] = c2.text_input("来源")
                    c3, c4 = st.columns(2)
                    base_data["amount"] = c3.number_input("总价", min_value=0.0)
                    link_config["qty"] = c4.number_input("数量", min_value=0.01, value=1.0)
                    link_config["unit_price"] = base_data["amount"] / link_config["qty"] if link_config["qty"] else 0

                elif base_data["category"] == "现有资产增加":
                    link_config["link_type"] = "manual_asset"
                    assets = FinanceService.get_balance_items(db, "asset")
                    # 简单过滤
                    valid_assets = [a for a in assets if not a.name.startswith(("在制", "预入库", "流动资金"))]
                    if not valid_assets:
                        st.warning("无手动资产")
                        st.stop()
                    sel_asset = st.selectbox("选择资产", [a.name for a in valid_assets])
                    target = next(a for a in valid_assets if a.name == sel_asset)
                    link_config["target_id"] = target.id
                    link_config["name"] = target.name
                    base_data["amount"] = st.number_input("增加金额", min_value=0.0)

                elif base_data["category"] == "新资产增加":
                    link_config["link_type"] = "manual_asset"
                    link_config["is_new"] = True
                    link_config["name"] = st.text_input("新资产名称")
                    base_data["shop"] = st.text_input("来源")
                    base_data["amount"] = st.number_input("金额", min_value=0.0)

                else:
                    base_data["desc"] = st.text_input("收入内容")
                    base_data["shop"] = st.text_input("来源")
                    base_data["amount"] = st.number_input("金额", min_value=0.0)
                    link_config["name"] = base_data["desc"]

            # --- B. 支出 ---
            else:
                cats = ["商品成本", "固定资产购入", "其他资产购入", "撤资", "现有资产减少", "其他"]
                exp_type = st.selectbox("支出分类", cats)
                base_data["category"] = exp_type

                if exp_type == "撤资":
                    link_config["link_type"] = "equity"
                    equities = FinanceService.get_balance_items(db, "equity")
                    if not equities:
                        st.warning("无资本项")
                        st.stop()
                    sel_eq = st.selectbox("选择项目", [e.name for e in equities])
                    target = next(e for e in equities if e.name == sel_eq)
                    link_config["target_id"] = target.id
                    link_config["name"] = target.name
                    base_data["amount"] = st.number_input("金额", min_value=0.0)

                elif exp_type == "现有资产减少":
                    link_config["link_type"] = "manual_asset"
                    assets = FinanceService.get_balance_items(db, "asset")
                    valid_assets = [a for a in assets if not a.name.startswith(("在制", "预入库", "流动资金"))]
                    if not valid_assets: st.stop()
                    sel_asset = st.selectbox("选择资产", [a.name for a in valid_assets])
                    target = next(a for a in valid_assets if a.name == sel_asset)
                    link_config["target_id"] = target.id
                    base_data["amount"] = st.number_input("减少金额", min_value=0.0)

                elif exp_type == "商品成本":
                    link_config["link_type"] = "cost"
                    c1, c2 = st.columns(2)
                    products = FinanceService.get_all_products(db)
                    p_opts = {p.id: p.name for p in products}
                    pid = c1.selectbox("归属商品", list(p_opts.keys()), format_func=lambda x: p_opts[x])
                    link_config["product_id"] = pid
                    
                    cost_cats = ["大货材料费", "大货加工费", "物流邮费", "包装费", "设计开发费", "检品发货等人工费", "宣发费", "其他成本"]
                    final_cat = c2.selectbox("成本分类", cost_cats)
                    base_data["category"] = final_cat
                    
                    budgets = FinanceService.get_budget_items(db, pid, final_cat)
                    b_opts = ["➕ 手动输入"] + [b.item_name for b in budgets]
                    
                    c3, c4 = st.columns([2, 1])
                    sel_item = c3.selectbox("内容", b_opts)
                    base_data["shop"] = c4.text_input("店铺")
                    
                    if sel_item == "➕ 手动输入":
                        link_config["name"] = c3.text_input("具体内容")
                    else:
                        link_config["name"] = sel_item
                        
                    c5, c6 = st.columns(2)
                    base_data["amount"] = c5.number_input("实付", min_value=0.0)
                    link_config["qty"] = c6.number_input("数量", min_value=0.01, value=1.0)
                    link_config["unit_price"] = base_data["amount"] / link_config["qty"]

                elif exp_type == "其他资产购入":
                    link_config["link_type"] = "consumable"
                    all_cons = FinanceService.get_consumable_items(db)
                    c_opts = ["➕ 手动输入"] + [c.name for c in all_cons]
                    
                    c1, c2, c3 = st.columns([1.5, 1, 1])
                    sel_name = c1.selectbox("名称", c_opts)
                    if sel_name == "➕ 手动输入":
                        link_config["name"] = c1.text_input("新名称")
                    else:
                        link_config["name"] = sel_name
                        target = next((c for c in all_cons if c.name == sel_name), None)
                        if target: 
                            valid_cats = ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"]
                            default_idx = valid_cats.index(target.category) if target.category in valid_cats else 0
                    
                    link_config["cat"] = c2.selectbox("分类", ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"], index=0)
                    base_data["shop"] = c3.text_input("店铺")
                    
                    c4, c5 = st.columns(2)
                    base_data["amount"] = c4.number_input("总价", min_value=0.0)
                    link_config["qty"] = c5.number_input("数量", min_value=0.01, value=1.0)
                    link_config["unit_price"] = base_data["amount"] / link_config["qty"]

                elif exp_type == "固定资产购入":
                    link_config["link_type"] = "fixed_asset"
                    c1, c2 = st.columns([2, 1])
                    link_config["name"] = c1.text_input("内容")
                    base_data["shop"] = c2.text_input("店铺")
                    c3, c4 = st.columns(2)
                    base_data["amount"] = c3.number_input("总价", min_value=0.0)
                    link_config["qty"] = c4.number_input("数量", min_value=0.01, value=1.0)
                    link_config["unit_price"] = base_data["amount"] / link_config["qty"]

                else:
                    c1, c2 = st.columns([2, 1])
                    link_config["name"] = c1.text_input("内容")
                    base_data["shop"] = c2.text_input("店铺")
                    base_data["amount"] = st.number_input("金额", min_value=0.0)

            base_data["desc"] = st.text_input("备注", placeholder="选填")

            # 提交通用收支
            if st.button("💾 确认记账", type="primary"):
                if base_data["amount"] == 0:
                    st.warning("金额不能为0")
                elif not link_config["name"] and not base_data.get("desc") and not base_data.get("category"):
                     st.warning("请完善信息")
                else:
                    try:
                        msg = FinanceService.create_general_transaction(db, base_data, link_config, exchange_rate)
                        st.toast(f"记账成功！{msg}", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"写入失败: {e}")

    # ================= 2. 数据与余额 =================
    df_display = FinanceService.get_finance_records_with_balance(db)
    cur_cny, cur_jpy = FinanceService.get_current_balances(db)

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("CNY 当前余额", f"¥ {cur_cny:,.2f}")
    m2.metric("JPY 当前余额", f"¥ {cur_jpy:,.0f}")
    m3.metric("JPY折合CNY", f"¥ {cur_jpy * exchange_rate:,.2f}", help=f"汇率: {exchange_rate*100:.1f}")
    m4.metric("账户总余额 (CNY)", f"¥ {(cur_cny + cur_jpy * exchange_rate):,.2f}")

    # ================= 3. 流水明细 =================
    if not df_display.empty:
        st.subheader("📜 流水明细")
        
        def highlight_rows(row):
            styles = [''] * len(row)
            if row.get("收支") == "支出":
                return ['background-color: #ffebee; color: #b71c1c'] * len(row)
            elif row.get("收支") == "收入":
                return ['background-color: #e8f5e9; color: #1b5e20'] * len(row)
            return styles

        df_styled = df_display.copy()
        df_styled['日期'] = pd.to_datetime(df_styled['日期']).dt.strftime('%Y-%m-%d')
        styler = df_styled.style.apply(highlight_rows, axis=1)
        styler = styler.format({"金额": "¥ {:.2f}", "当前CNY余额": "¥ {:.2f}", "当前JPY余额": "¥ {:.0f}"})

        st.dataframe(styler, use_container_width=True, hide_index=True, height=600, column_config={"ID": None})

        # ================= 4. 编辑与删除 =================
        st.divider()
        c_edit, c_del = st.columns([1, 1])
        record_options = df_display.to_dict('records')

        with c_edit:
            with st.popover("✏️ 编辑记录", use_container_width=True):
                if record_options:
                    sel = st.selectbox("选择记录", record_options, format_func=lambda x: f"{x['日期']} | {x['收支']} {x['金额']} | {x['备注']}")
                    if sel:
                        with st.form(key=f"edit_{sel['ID']}"):
                            n_date = st.date_input("日期", value=sel['日期'])
                            c1, c2 = st.columns(2)
                            n_type = c1.selectbox("类型", ["收入", "支出"], index=0 if sel['收支']=="收入" else 1)
                            n_curr = c2.selectbox("币种", ["CNY", "JPY"], index=0 if sel['币种']=="CNY" else 1)
                            n_amt = st.number_input("金额", value=float(sel['金额']), min_value=0.0)
                            n_cat = st.text_input("分类", value=sel['分类'])
                            n_desc = st.text_input("备注", value=sel['备注'])
                            
                            if st.form_submit_button("保存修改"):
                                updates = {
                                    "date": n_date, "type": n_type, "currency": n_curr,
                                    "amount_abs": n_amt, "category": n_cat, "desc": n_desc
                                }
                                try:
                                    if FinanceService.update_record(db, sel['ID'], updates):
                                        st.toast("已修改", icon="💾")
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"修改失败: {e}")

        with c_del:
            with st.popover("🗑️ 删除记录", use_container_width=True):
                if record_options:
                    sel = st.selectbox("删除记录", record_options, format_func=lambda x: f"{x['日期']} | {x['金额']} | {x['备注']}")
                    if st.button("确认删除"):
                        try:
                            msg = FinanceService.delete_record(db, sel['ID'])
                            if msg:
                                st.toast(f"已删除: {msg}", icon="🗑️")
                                st.rerun()
                        except Exception as e:
                            st.error(f"删除失败: {e}")
    else:
        st.info("暂无记录")