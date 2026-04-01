# views/finance_view.py
import streamlit as st
import pandas as pd
import math  # 新增用于分页计算
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
def get_cached_finance_data(test_mode_flag):
    """缓存流水明细和余额，避免每次刷新重算全表。传入_test_mode_flag隔离真假环境的缓存"""
    db_cache = st.session_state.get_dynamic_session()
    try:
        df_display = FinanceService.get_finance_records_with_balance(db_cache)
        
        # 🚀 性能优化 3：使用向量化的 map 替代低效的 apply，速度飙升
        if not df_display.empty:
            df_display['收支'] = df_display['收支'].map({"收入": "🟢 收入", "支出": "🔴 支出"}).fillna(df_display['收支'])
            
        cur_cny, cur_jpy = FinanceService.get_current_balances(db_cache)
        return df_display, cur_cny, cur_jpy
    finally:
        db_cache.close()

# ================= 局部组件：新增表单 =================
@fragment_if_available
def render_add_transaction_form(exchange_rate):
    # 局部组件内使用动态分配的 session
    db_frag = st.session_state.get_dynamic_session()
    try:
        with st.expander("➕ 新增收支 / 兑换 / 债务记录", expanded=True):
            
            c_top1, c_top2 = st.columns(2)
            f_date = c_top1.date_input("日期", date.today())
            rec_type = c_top2.selectbox("业务大类", ["支出", "收入", "货币兑换", "债务", "资金移动"])
            
            st.divider()

            # 初始化通用变量 (Base Data)
            base_data = {
                "date": f_date, "type": rec_type, "currency": "CNY", 
                "amount": 0.0, "category": "", "shop": "", "desc": ""
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
                
                st.markdown("##### 2. 兑换方向")
                c_ex_dir1, c_ex_dir2 = st.columns(2)
                source_curr = c_ex_dir1.selectbox("源币种 (扣款账户)", ["CNY", "JPY"])
                target_curr = "JPY" if source_curr == "CNY" else "CNY"
                c_ex_dir2.info(f"➡️ 目标币种 (入账账户): **{target_curr}**")
                
                st.markdown("##### 3. 交易金额")
                c_ex1, c_ex2 = st.columns(2)
                amount_out = c_ex1.number_input(f"流出金额 ({source_curr})", min_value=0.0, step=100.0, format="%.2f")
                
                est_val = amount_out / exchange_rate if source_curr == "CNY" else amount_out * exchange_rate
                amount_in = c_ex2.number_input(f"入账金额 ({target_curr})", value=est_val, min_value=0.0, step=100.0, format="%.2f", help="自动按系统汇率估算，可手动修正实收金额")
                
                st.markdown("##### 4. 附加信息")
                desc = st.text_input("备注说明", placeholder="如：支付宝购汇、信用卡日元结算账单等")
                
                st.write("")
                if st.button("💾 确认兑换", type="primary", width="stretch"):
                    if amount_out <= 0 or amount_in <= 0:
                        st.warning("金额必须大于0")
                    else:
                        try:
                            FinanceService.execute_exchange(db_frag, f_date, source_curr, target_curr, amount_out, amount_in, desc)
                            st.toast(f"兑换成功：-{amount_out}{source_curr}, +{amount_in}{target_curr}", icon="💱")
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
                    d_name = c_t1.text_input("债务名称", placeholder="如：银行经营贷、欠某加工厂货款 (必填)")
                    
                    # 【核心修复 1】精准匹配选项，解决一直走“新增资产”分支的 Bug
                    dest_options = ["存入流动资金 (拿到现金)", "新增资产项 (形成实物/账面资产)"]
                    dest = c_t2.selectbox("借入价值去向", dest_options)
                    is_to_cash = (dest == dest_options[0])
                    
                    # 【核心修复 2】如果是现金，隐藏挂账资产名称；如果是资产，则要求必填
                    if is_to_cash:
                        rel_content = "" # 不需要填资产名
                    else:
                        rel_content = st.text_input("新增挂账资产名称", placeholder="如：未付款的打印机 (必填)")

                    st.markdown("##### 3. 交易金额与币种")
                    c_d1, c_curr, c_d2 = st.columns([1.5, 1, 1.5])
                    d_amount = c_d1.number_input("金额", min_value=0.0, step=100.0)
                    curr = c_curr.selectbox("币种", ["CNY", "JPY"])

                    st.markdown("##### 4. 附加信息")
                    c_add1, c_add2 = st.columns(2)
                    d_source = c_add1.text_input("债权人/资金来源", placeholder="如：工商银行、加工厂A")
                    d_remark = c_add2.text_input("备注说明")

                    st.write("")
                    if st.button("💾 确认新增债务", type="primary", width="stretch"):
                        # 【核心修复 3】按需校验：如果是资产，必须有资产名；如果是现金，只校验债务名和金额
                        if not d_name or d_amount <= 0 or (not is_to_cash and not rel_content):
                            st.error("请填写完整必填项（债务名称、资产名称）并确保金额大于0")
                        else:
                            try:
                                FinanceService.create_debt(
                                    db_frag, f_date, curr, d_name, d_amount, d_source, d_remark, 
                                    is_to_cash=is_to_cash, related_content=rel_content
                                )
                                st.toast("债务记录成功", icon="📝")
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
                            c_r1, c_curr, c_r2 = st.columns([1.5, 1, 1.5])
                            amt = c_r1.number_input("偿还金额", min_value=0.0, step=100.0, max_value=max_repay, value=max_repay)
                            c_curr.info(f"结算币种: **{curr}**")
                            
                            st.markdown("##### 4. 附加信息")
                            rem = st.text_input("备注说明", placeholder="选填")
                            
                            st.write("")
                            if st.button("💾 确认资金还款", type="primary", width="stretch"):
                                try:
                                    FinanceService.repay_debt(db_frag, f_date, sel_id, amt, rem)
                                    st.toast("还款成功", icon="💸")
                                    sync_all_caches()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"失败: {e}")
                        else:
                            assets = FinanceService.get_balance_items(db_frag, "asset")
                            asset_map = {f"{a.name} (余:{a.amount})" : a.id for a in assets}
                            
                            c_a1, c_a2 = st.columns([2, 1.5])
                            asset_label = c_a1.selectbox("选择用于抵消的资产", list(asset_map.keys()))
                            amt = c_a2.number_input("用于抵消的账面金额", min_value=0.0, max_value=max_repay, value=max_repay)
                            
                            st.markdown("##### 4. 附加信息")
                            rem = st.text_input("备注说明", placeholder="选填")
                            
                            st.write("")
                            if st.button("💾 确认资产抵消", type="primary", width="stretch"):
                                try:
                                    FinanceService.offset_debt(db_frag, f_date, sel_id, asset_map[asset_label], amt, rem)
                                    st.toast("抵消成功", icon="🔄")
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

                # --- 2. 业务内容 ---
                st.markdown("##### 2. 业务内容")
                needs_qty = False
                cat = base_data["category"]
                
                if cat == "投资":
                    equities = FinanceService.get_balance_items(db_frag, "equity")
                    eq_opts = ["➕ 新增资本项目"] + [e.name for e in equities]
                    c_eq1, c_eq2 = st.columns([1.5, 2])
                    sel_eq = c_eq1.selectbox("投资归属项目", eq_opts)
                    
                    link_config["link_type"] = "equity"
                    if sel_eq == "➕ 新增资本项目":
                        link_config["is_new"] = True
                        link_config["name"] = c_eq2.text_input("新资本项目名称", placeholder="如：股东A注资 (必填)")
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
                    link_config["name"] = st.text_input("新增资产名称", placeholder="如：纸箱、不干胶 (必填)")

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
                    link_config["name"] = c_na1.text_input("新资产名称", placeholder="如：支付宝备用金 (必填)")
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

                elif cat == "商品成本":
                    needs_qty = True
                    link_config["link_type"] = "cost"
                    c_c1, c_c2 = st.columns(2)
                    products = FinanceService.get_all_products(db_frag)
                    p_opts = {p.id: p.name for p in products}
                    pid = c_c1.selectbox("归属商品", list(p_opts.keys()), format_func=lambda x: p_opts[x])
                    link_config["product_id"] = pid
                    
                    final_cat = c_c2.selectbox("成本分类", PRODUCT_COST_CATEGORIES)
                    link_config["cat"] = final_cat
                    
                    budgets = FinanceService.get_budget_items(db_frag, pid, final_cat)
                    b_opts = ["➕ 手动输入新项目"] + [b.item_name for b in budgets]
                    
                    c_c3, c_c4 = st.columns([1.5, 2], vertical_alignment="bottom")
                    sel_item = c_c3.selectbox("预算项目匹配", b_opts)
                    
                    if sel_item == "➕ 手动输入新项目":
                        link_config["name"] = c_c4.text_input("具体成本内容", placeholder="如：蕾丝边打样费 (必填)")
                    else:
                        link_config["name"] = sel_item
                        c_c4.info(f"✅ 自动挂载至预算项: {sel_item}")

                elif cat == "其他资产购入":
                    needs_qty = True
                    link_config["link_type"] = "consumable"
                    all_cons = FinanceService.get_consumable_items(db_frag)
                    c_opts = ["➕ 登记新资产种类"] + [c.name for c in all_cons]
                    
                    c_oa1, c_oa2 = st.columns([1.5, 1])
                    sel_name = c_oa1.selectbox("资产名称", c_opts)
                    
                    if sel_name == "➕ 登记新资产种类":
                        link_config["name"] = c_oa1.text_input("填写新资产名称", placeholder="如：飞机盒 (必填)")
                        link_config["cat"] = c_oa2.selectbox("资产子分类", ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"], index=0)
                    else:
                        link_config["name"] = sel_name
                        target = next((c for c in all_cons if c.name == sel_name), None)
                        default_idx = 0
                        if target: 
                            valid_cats = ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"]
                            default_idx = valid_cats.index(target.category) if target.category in valid_cats else 0
                        link_config["cat"] = c_oa2.selectbox("资产子分类", ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"], index=default_idx)

                elif cat == "固定资产购入":
                    needs_qty = True
                    link_config["link_type"] = "fixed_asset"
                    link_config["name"] = st.text_input("固定资产名称", placeholder="如：缝纫机、相机 (必填)")

                else:
                    link_config["name"] = st.text_input("收支明细描述", placeholder="如：顺丰快递费、工作餐补 (必填)")

                # --- 3. 交易金额与数量 ---
                st.markdown("##### 3. 交易金额与数量")
                
                if needs_qty:
                    c_amt1, c_curr, c_qty = st.columns([1.5, 1, 1.5])
                    amt_label = "收入总额" if rec_type == "收入" else "实付总额"
                    base_data["amount"] = c_amt1.number_input(amt_label, min_value=0.0, step=10.0, format="%.2f")
                    base_data["currency"] = c_curr.selectbox("币种", ["CNY", "JPY"])
                    link_config["qty"] = c_qty.number_input("数量", min_value=0.01, value=1.0)
                    link_config["unit_price"] = base_data["amount"] / link_config["qty"] if link_config["qty"] else 0
                else:
                    c_amt1, c_curr, _ = st.columns([1.5, 1, 1.5])
                    amt_label = "收入金额" if rec_type == "收入" else "支出金额"
                    base_data["amount"] = c_amt1.number_input(amt_label, min_value=0.0, step=10.0, format="%.2f")
                    base_data["currency"] = c_curr.selectbox("币种", ["CNY", "JPY"])

                # --- 4. 附加信息 ---
                st.markdown("##### 4. 附加信息")
                c_add1, c_add2 = st.columns(2)
                shop_label = "付款人/资金来源" if rec_type == "收入" else "收款方/店铺名称"
                base_data["shop"] = c_add1.text_input(shop_label, placeholder="选填")
                base_data["desc"] = c_add2.text_input("其他备注", placeholder="选填，将展示在流水详情中")
                
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
                            sync_all_caches()
                            st.rerun()
                        except Exception as e:
                            st.error(f"写入失败: {e}")
            # >>>>> 场景 D: 资金移动 <<<<<
            elif rec_type == "资金移动":
                st.markdown("##### 1. 业务分类")
                st.info("🔄 资金移动 (将同币种资金从一项资产转移到另一项，内部划转不影响总净资产)")
                
                # 获取所有的资产项目 (CNY 和 JPY)
                all_assets = FinanceService.get_transferable_assets(db_frag)
                
                if len(all_assets) < 2:
                    st.warning("⚠️ 当前资产项目不足 2 个，无法进行移动操作。")
                else:
                    st.markdown("##### 2. 资金移动方向")
                    
                    def format_asset(a):
                        # 在选项里带上币种标签，方便肉眼区分
                        return f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})"
                        
                    # -- 构建转出账户下拉框 --
                    from_options = {format_asset(a): a for a in all_assets}
                    from_label = st.selectbox("转出账户 (移动前项目)", list(from_options.keys()), key="fund_from")
                    from_asset = from_options[from_label]
                    
                    # -- 动态构建转入账户下拉框 --
                    # 规则：币种必须与转出账户相同，且排除自己
                    to_assets = [a for a in all_assets if a.currency == from_asset.currency and a.id != from_asset.id]
                    
                    if not to_assets:
                        st.warning(f"⚠️ 找不到其他 {from_asset.currency} 资产，无法完成该币种的移动。")
                    else:
                        to_options = {format_asset(a): a for a in to_assets}
                        to_label = st.selectbox("转入账户 (移动后项目)", list(to_options.keys()), key="fund_to")
                        to_asset = to_options[to_label]
                        
                        st.markdown("##### 3. 移动金额与余额预览")
                        amount = st.number_input(
                            f"移动金额 ({from_asset.currency})", 
                            min_value=0.0, 
                            max_value=float(from_asset.amount), # 最大限制不能超过转出账户余额
                            step=100.0 if from_asset.currency == "CNY" else 1000.0, 
                            format="%.2f"
                        )
                        
                        # 动态渲染移动后的金额预览
                        if amount > 0:
                            c_prev1, c_prev2 = st.columns(2)
                            c_prev1.success(f"📉 **{from_asset.name}** 移动后预览: {(from_asset.amount - amount):,.2f} {from_asset.currency}")
                            c_prev2.success(f"📈 **{to_asset.name}** 移动后预览: {(to_asset.amount + amount):,.2f} {to_asset.currency}")
                            
                        st.markdown("##### 4. 附加信息")
                        desc = st.text_input("备注说明", placeholder="如：将流动资金投入到某项目储备金中")
                        
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
                            n_date = st.date_input("日期", value=sel['日期'])
                            c1, c2 = st.columns(2)
                            n_type = c1.selectbox("类型", ["收入", "支出"], index=0 if "收入" in sel['收支'] else 1)
                            n_curr = c2.selectbox("币种", ["CNY", "JPY"], index=0 if sel['币种']=="CNY" else 1)
                            n_amt = st.number_input("金额", value=float(sel['金额']), min_value=0.0)
                            n_cat = st.text_input("分类", value=sel['分类'])
                            n_desc = st.text_input("备注", value=sel['备注'])
                            
                            if st.form_submit_button("保存修改", type="primary"):
                                updates = {
                                    "date": n_date, "type": n_type, "currency": n_curr,
                                    "amount_abs": n_amt, "category": n_cat, "desc": n_desc
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
                            st.error("⚠️ 核心业务保护：【销售收入】类型的流水不可在此处直接删除。请前往【销售订单管理】界面撤销或删除对应的订单，系统会自动同步扣除此笔流水。")
                            st.button("确认删除", width="stretch", type="primary", disabled=True)
                        else:
                            if st.button("确认删除", width="stretch", type="primary"):
                                try:
                                    msg = FinanceService.delete_record(db_frag, sel['ID'])
                                    if msg is not False:
                                        st.toast(f"已删除，关联数据回滚: {msg}", icon="🗑️")
                                        sync_all_caches() # 确保这里用的是我们刚改好的全局缓存清理
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
    
    # --- 2. 获取缓存的表格数据 (秒开) ---
    test_mode = st.session_state.get("test_mode", False)
    with st.spinner("加载流水历史中..."):
        df_display, cur_cny, cur_jpy = get_cached_finance_data(test_mode)

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("CNY 当前余额", f"¥ {cur_cny:,.2f}")
    m2.metric("JPY 当前余额", f"¥ {cur_jpy:,.0f}")
    m3.metric("JPY 折合 CNY", f"¥ {cur_jpy * exchange_rate:,.2f}", help=f"实时汇率设置: {exchange_rate*100:.1f}")
    m4.metric("账户总余额 (CNY)", f"¥ {(cur_cny + cur_jpy * exchange_rate):,.2f}")

    # --- 3. 渲染原生表格 (附带分页功能) ---
    if not df_display.empty:
        st.subheader("📜 流水明细")
        
        # === 分页逻辑核心 ===
        if "finance_page" not in st.session_state:
            st.session_state.finance_page = 1

        PAGE_SIZE = 100
        total_rows = len(df_display)
        total_pages = math.ceil(total_rows / PAGE_SIZE)

        # 容错边界：如果数据被删除导致当前页超出总页数，自动跳回最后一页
        if st.session_state.finance_page > total_pages and total_pages > 0:
            st.session_state.finance_page = total_pages

        current_page = st.session_state.finance_page

        # 执行数据切片
        start_idx = (current_page - 1) * PAGE_SIZE
        end_idx = current_page * PAGE_SIZE
        df_render = df_display.iloc[start_idx:end_idx]

        st.caption(f"共计 **{total_rows}** 条记录，当前显示第 **{start_idx + 1}** 到 **{min(end_idx, total_rows)}** 条。")

        # 渲染截取后的当页表格
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
        # 传入当前页截取的 df_render，下拉框只显示当前这 100 条记录
        render_edit_delete_panel(df_render)
    else:
        st.info("暂无记录")