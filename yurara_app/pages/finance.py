# yurara_app/pages/finance.py
"""
财务流水录入与流水明细页面。
提供完整的收支记账表单（表单驱动物品明细表替代 st.data_editor），支持真分页流水展示、高亮余额卡片、编辑/删除流水模块。
"""
import reflex as rx
from constants import PRODUCT_COST_CATEGORIES
from ..state.finance_state import FinanceState, FinanceRecordItem, TempBatchItem
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state, confirm_dialog


def stat_indicator_card(label: str, value: rx.Var, unit: str = "CNY", color_scheme: str = "violet", icon: str = "circle") -> rx.Component:
    """顶部高亮现金余额卡片"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon(icon, size=16, color=rx.color(color_scheme, 9)),
                rx.text(label, size="1", color=rx.color("slate", 10)),
                spacing="1",
                align="center",
            ),
            rx.hstack(
                rx.text(value, size="5", weight="bold"),
                rx.text(unit, size="1", color=rx.color("slate", 10), margin_top="auto"),
                spacing="1",
                align="end",
            ),
            spacing="1",
            align_items="start",
        ),
        padding="0.75rem",
        width="100%",
    )

CATS_INCOME = ["销售收入", "退款", "投资", "现有资产增加", "其他资产增加", "新资产增加", "其他现金收入"]
CATS_EXPENSE = ["商品成本", "固定资产购入", "其他资产购入", "撤资", "分红", "现有资产减少", "其他"]


# ===================== 表单场景子组件 =====================

def common_single_form() -> rx.Component:
    """场景 A: 普通收入与普通支出（单项）"""
    return rx.vstack(
        rx.grid(
            custom_form_field(
                "收支细分类型",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.cond(
                            FinanceState.rec_type == "收入",
                            rx.foreach(CATS_INCOME, lambda c: rx.select.item(c, value=c)),
                            rx.foreach(CATS_EXPENSE, lambda c: rx.select.item(c, value=c))
                        )
                    ),
                    value=FinanceState.f_category,
                    on_change=FinanceState.set_f_category,
                    size="2", width="100%"
                )
            ),
            custom_form_field(
                "金额",
                rx.input(
                    type="number",
                    placeholder="请输入金额",
                    value=FinanceState.f_amount.to_string(),
                    on_change=lambda v: FinanceState.set_f_amount(rx.cond(v != "", v.to(float), 0.0)),
                    size="2", width="100%"
                )
            ),
            custom_form_field(
                "币种",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.select.item("CNY", value="CNY"),
                        rx.select.item("JPY", value="JPY")
                    ),
                    value=FinanceState.f_currency,
                    on_change=FinanceState.set_f_currency,
                    size="2", width="100%"
                )
            ),
            columns="3", spacing="4", width="100%"
        ),
        
        # 如果不是非现金操作，展现操作账户
        rx.cond(
            ~FinanceState.is_non_cash,
            custom_form_field(
                rx.cond(FinanceState.rec_type == "收入", "入账账户", "操作账户"),
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            FinanceState.cash_accounts,
                            lambda acc: rx.select.item(acc.label, value=acc.id)
                        )
                    ),
                    placeholder="选择账户",
                    value=FinanceState.f_account_id,
                    on_change=FinanceState.set_f_account_id,
                    size="2", width="100%"
                )
            ),
            rx.callout("💡 此操作为纯资产账面价值核销或增加，不影响流动资金账户。", icon="info", size="1", color_scheme="blue", width="100%")
        ),
        
        rx.grid(
            custom_form_field(
                rx.cond(FinanceState.rec_type == "收入", "付款方/资金来源", "收款方/店铺名称"),
                rx.input(
                    placeholder="如：某淘宝店、公司A (选填)",
                    value=FinanceState.f_shop,
                    on_change=FinanceState.set_f_shop,
                    size="2", width="100%"
                )
            ),
            custom_form_field(
                "相关页面网址 (选填)",
                rx.input(
                    placeholder="如：淘宝或Booth宝贝链接",
                    value=FinanceState.f_url,
                    on_change=FinanceState.set_f_url,
                    size="2", width="100%"
                )
            ),
            columns="2", spacing="4", width="100%"
        ),
        custom_form_field(
            "业务明细描述/其他备注",
            rx.input(
                placeholder="如：顺丰快递费、购买打包纸箱等 (必填)",
                value=FinanceState.f_desc,
                on_change=FinanceState.set_f_desc,
                size="2", width="100%"
            )
        ),
        spacing="3", width="100%"
    )


def batch_editor_table() -> rx.Component:
    """批量录入物品明细表（替代 st.data_editor）"""
    return rx.vstack(
        rx.text("物品明细表", size="2", weight="bold"),
        # 明细表
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("内容/名称", size="1", style={"width": "16.66%"}),
                    rx.table.column_header_cell("金额", size="1", style={"width": "16.66%"}),
                    rx.table.column_header_cell("数量", size="1", style={"width": "16.66%"}),
                    rx.table.column_header_cell("具体备注", size="1", style={"width": "16.66%"}),
                    rx.table.column_header_cell("网址", size="1", style={"width": "16.66%"}),
                    rx.table.column_header_cell("", size="1", style={"width": "16.66%"}),
                )
            ),
            rx.table.body(
                rx.foreach(
                    FinanceState.batch_items,
                    lambda item: rx.table.row(
                        rx.table.cell(rx.text(item.name, size="1"), style={"width": "16.66%"}),
                        rx.table.cell(rx.text(item.amount.to_string(), size="1"), style={"width": "16.66%"}),
                        rx.table.cell(rx.text(item.qty.to_string(), size="1"), style={"width": "16.66%"}),
                        rx.table.cell(rx.text(item.desc, size="1"), style={"width": "16.66%"}),
                        rx.table.cell(rx.text(item.url, size="1", line_clamp=1), style={"width": "16.66%"}),
                        rx.table.cell(
                            rx.icon_button(
                                rx.icon("trash_2", size=12),
                                on_click=lambda: FinanceState.remove_batch_item(item.key),
                                size="1", variant="ghost", color_scheme="red"
                            ),
                            style={"width": "16.66%"}
                        )
                    )
                )
            ),
            size="1", width="100%"
        ),
        
        # 录入新明细条目的行表单
        rx.box(
            rx.grid(
                custom_form_field("明细物品名称", rx.input(placeholder="物品名称 (必填)", value=FinanceState.temp_name, on_change=FinanceState.set_temp_name, size="1")),
                custom_form_field("金额", rx.input(type="number", placeholder="金额 (必填)", value=FinanceState.temp_amount.to_string(), on_change=lambda v: FinanceState.set_temp_amount(rx.cond(v != "", v.to(float), 0.0)), size="1")),
                custom_form_field("数量", rx.input(type="number", placeholder="数量", value=FinanceState.temp_qty.to_string(), on_change=lambda v: FinanceState.set_temp_qty(rx.cond(v != "", v.to(float), 1.0)), size="1")),
                custom_form_field("具体备注 (选填)", rx.input(placeholder="如：款式规格", value=FinanceState.temp_desc, on_change=FinanceState.set_temp_desc, size="1")),
                custom_form_field("网址 (选填)", rx.input(placeholder="商品链接", value=FinanceState.temp_url, on_change=FinanceState.set_temp_url, size="1")),
                rx.center(
                    rx.button(
                        rx.icon("plus", size=13), "添加物品",
                        on_click=FinanceState.add_batch_item,
                        size="1",
                        style={"background": "#10b981", "color": "white", "font-weight": "bold"}
                    ),
                    margin_top="1rem"
                ),
                columns="6", spacing="3", width="100%"
            ),
            padding="0.75rem 0",
            width="100%",
        ),
        
        # 结算面板
        rx.hstack(
            rx.spacer(),
            rx.vstack(
                rx.hstack(rx.text("物品小计:", size="1", color="white"), rx.text(FinanceState.batch_items_subtotal_str, weight="bold", size="1", color="white"), spacing="1"),
                rx.hstack(rx.text("共同邮费:", size="1", color="white"), rx.text(FinanceState.batch_shipping_fee.to_string(), weight="bold", size="1", color="white"), spacing="1"),
                rx.hstack(
                    rx.text("订单扣款总计:", size="2", weight="bold", color="white"),
                    rx.text(FinanceState.batch_total_with_shipping_str, size="3", weight="bold", color="#d8b4fe"),
                    spacing="1"
                ),
                align_items="end", spacing="1"
            ),
            width="100%", padding="0.5rem"
        ),
        
        spacing="3", width="100%"
    )


def batch_expense_form() -> rx.Component:
    """场景 B: 批量购入（成本、固定资产、其他资产）表单驱动的明细追加组件"""
    return rx.vstack(
        rx.grid(
            custom_form_field(
                "操作大类",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(CATS_EXPENSE, lambda c: rx.select.item(c, value=c))
                    ),
                    value=FinanceState.f_category,
                    on_change=FinanceState.set_f_category,
                    size="2", width="100%"
                )
            ),
            # 商品成本特有归属商品和分类
            rx.cond(
                FinanceState.f_category == "商品成本",
                custom_form_field(
                    "归属商品",
                    rx.select.root(
                        rx.select.trigger(width="400px"),
                        rx.select.content(
                            rx.foreach(
                                FinanceState.products_list,
                                lambda p: rx.select.item(p.label, value=p.id)
                            )
                        ),
                        value=FinanceState.batch_product_id,
                        on_change=FinanceState.set_batch_product_id,
                        size="2", width="100%"
                    )
                ),
                rx.cond(
                    FinanceState.f_category == "其他资产购入",
                    custom_form_field(
                        "资产子分类",
                        rx.select.root(
                            rx.select.trigger(),
                            rx.select.content(
                                rx.select.item("包装材", value="包装材"),
                                rx.select.item("无实体", value="无实体"),
                                rx.select.item("备用素材", value="备用素材"),
                                rx.select.item("其他", value="其他"),
                                rx.select.item("商品周边", value="商品周边"),
                                rx.select.item("办公用品", value="办公用品")
                            ),
                            value=FinanceState.batch_asset_cat,
                            on_change=FinanceState.set_batch_asset_cat,
                            size="2", width="100%"
                        )
                    ),
                    rx.fragment()
                )
            ),
            rx.cond(
                FinanceState.f_category == "商品成本",
                custom_form_field(
                    "共同成本分类",
                    rx.select.root(
                        rx.select.trigger(width="400px"),
                        rx.select.content(
                            rx.foreach(PRODUCT_COST_CATEGORIES, lambda cat: rx.select.item(cat, value=cat))
                        ),
                        value=FinanceState.batch_cost_cat,
                        on_change=FinanceState.set_batch_cost_cat,
                        size="2", width="100%"
                    )
                ),
                rx.fragment()
            ),
            columns="3", spacing="4", width="100%"
        ),
        
        # 联动加载预算匹配选择
        rx.cond(
            FinanceState.f_category == "商品成本",
            custom_form_field(
                "🎯 预算项目匹配",
                rx.select.root(
                    rx.select.trigger(width="400px"),
                    rx.select.content(
                        rx.foreach(
                            FinanceState.budgets_list,
                            lambda b: rx.select.item(b.label, value=b.id)
                        )
                    ),
                    placeholder="➕ 不匹配预算 (批量录入新成本)",
                    value=FinanceState.batch_selected_budget_id,
                    on_change=FinanceState.set_batch_selected_budget_id,
                    size="2", width="100%"
                )
            ),
            rx.fragment()
        ),
        
        # 匹配预算警告提示
        rx.cond(
            (FinanceState.batch_selected_budget_id != "") & (FinanceState.batch_selected_budget_id != "0"),
            rx.callout("✅ 当前已匹配特定预算项：此模式下仅支持添加一条物品明细用于累加实付成本，且共同邮费将设为0。", icon="info", size="1", color_scheme="blue", width="100%"),
            rx.fragment()
        ),
        
        # 共同店铺与操作账户
        rx.grid(
            custom_form_field(
                "付款现金账户",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            FinanceState.cash_accounts,
                            lambda acc: rx.select.item(acc.label, value=acc.id)
                        )
                    ),
                    value=FinanceState.f_account_id,
                    on_change=FinanceState.set_f_account_id,
                    size="2", width="100%"
                )
            ),
            custom_form_field(
                "付款店铺/收款方",
                rx.input(
                    placeholder="如：某工厂、淘宝商家",
                    value=FinanceState.f_shop,
                    on_change=FinanceState.set_f_shop,
                    size="2", width="100%"
                )
            ),
            custom_form_field(
                "交易币种",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.select.item("CNY", value="CNY"),
                        rx.select.item("JPY", value="JPY")
                    ),
                    value=FinanceState.f_currency,
                    on_change=FinanceState.set_f_currency,
                    size="2", width="100%"
                )
            ),
            columns="3", spacing="4", width="100%"
        ),
        
        # 共同邮费录入 (不匹配预算时显示)
        rx.cond(
            FinanceState.batch_selected_budget_id == "",
            custom_form_field(
                "订单共同邮费",
                rx.input(
                    type="number",
                    placeholder="请输入共同邮费",
                    value=FinanceState.batch_shipping_fee.to_string(),
                    on_change=lambda v: FinanceState.set_batch_shipping_fee(rx.cond(v != "", v.to(float), 0.0)),
                    size="2", width="100%"
                )
            ),
            rx.fragment()
        ),
        
        # 物品明细表格与输入行
        batch_editor_table(),
        spacing="3", width="100%"
    )


def exchange_form() -> rx.Component:
    """场景 C: 货币兑换"""
    return rx.vstack(
        rx.callout("💱 货币资金互转 (此操作不会改变总净资产，只调整账户余额分布)", icon="info", color_scheme="violet", size="1", width="100%"),
        rx.grid(
            custom_form_field(
                "扣款侧源币种",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.select.item("CNY", value="CNY"),
                        rx.select.item("JPY", value="JPY")
                    ),
                    value=FinanceState.ex_source_curr,
                    on_change=FinanceState.set_ex_source_curr,
                    size="2", width="100%"
                )
            ),
            custom_form_field(
                "扣款现金账户",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            FinanceState.cash_accounts,
                            lambda acc: rx.select.item(acc.label, value=acc.id)
                        )
                    ),
                    value=FinanceState.ex_source_acc_id,
                    on_change=FinanceState.set_ex_source_acc_id,
                    size="2", width="100%"
                )
            ),
            columns="2", spacing="4", width="100%"
        ),
        rx.grid(
            custom_form_field(
                "入账侧目标币种",
                rx.input(value=FinanceState.ex_target_curr, disabled=True, size="2", width="100%")
            ),
            custom_form_field(
                "入账现金账户",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            FinanceState.cash_accounts,
                            lambda acc: rx.select.item(acc.label, value=acc.id)
                        )
                    ),
                    value=FinanceState.ex_target_acc_id,
                    on_change=FinanceState.set_ex_target_acc_id,
                    size="2", width="100%"
                )
            ),
            columns="2", spacing="4", width="100%"
        ),
        rx.grid(
            custom_form_field(
                "转出/流出金额",
                rx.input(
                    type="number",
                    placeholder="流出金额",
                    value=FinanceState.ex_amount_out.to_string(),
                    on_change=lambda v: FinanceState.set_ex_amount_out(rx.cond(v != "", v.to(float), 0.0)),
                    size="2", width="100%"
                )
            ),
            custom_form_field(
                "转入/入账金额",
                rx.input(
                    type="number",
                    placeholder="入账金额",
                    value=FinanceState.ex_amount_in.to_string(),
                    on_change=lambda v: FinanceState.set_ex_amount_in(rx.cond(v != "", v.to(float), 0.0)),
                    size="2", width="100%",
                    helper="自动按当前系统汇率进行推算估值"
                )
            ),
            columns="2", spacing="4", width="100%"
        ),
        custom_form_field(
            "兑换备注说明",
            rx.input(
                placeholder="如：购汇、信用卡日元结算扣款等 (选填)",
                value=FinanceState.ex_desc,
                on_change=FinanceState.set_ex_desc,
                size="2", width="100%"
            )
        ),
        spacing="3", width="100%"
    )


def debt_form() -> rx.Component:
    """场景 D: 债务管理"""
    return rx.vstack(
        custom_form_field(
            "债务操作类型",
            rx.select.root(
                rx.select.trigger(),
                rx.select.content(
                    rx.select.item("➕ 新增债务", value="➕ 新增债务"),
                    rx.select.item("💸 偿还债务", value="💸 偿还债务")
                ),
                value=FinanceState.debt_op,
                on_change=FinanceState.set_debt_op,
                size="2", width="100%"
            )
        ),
        rx.divider(),
        rx.cond(
            FinanceState.debt_op == "➕ 新增债务",
            # 新增债务子表单
            rx.vstack(
                rx.grid(
                    custom_form_field("债务名称/欠款事由", rx.input(placeholder="如：工厂挂账货款、借款 (必填)", value=FinanceState.debt_name, on_change=FinanceState.set_debt_name, size="2")),
                    custom_form_field("借入价值去向", rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.select.item("存入流动资金 (拿到现金)", value="存入流动资金 (拿到现金)"),
                            rx.select.item("新增资产项 (形成实物/挂账资产)", value="新增资产项 (形成实物/挂账资产)")
                        ),
                        value=FinanceState.debt_dest, on_change=FinanceState.set_debt_dest, size="2"
                    )),
                    columns="2", spacing="4", width="100%"
                ),
                rx.cond(
                    FinanceState.debt_dest != "存入流动资金 (拿到现金)",
                    custom_form_field("新增挂账资产名称", rx.input(placeholder="如：未付款的打包机 (必填)", value=FinanceState.debt_rel_content, on_change=FinanceState.set_debt_rel_content, size="2")),
                    rx.fragment()
                ),
                rx.grid(
                    custom_form_field("债务金额", rx.input(type="number", placeholder="金额", value=FinanceState.debt_amount.to_string(), on_change=lambda v: FinanceState.set_debt_amount(rx.cond(v != "", v.to(float), 0.0)), size="2")),
                    custom_form_field("币种", rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.select.item("CNY", value="CNY"),
                            rx.select.item("JPY", value="JPY")
                        ),
                        value=FinanceState.debt_curr, on_change=FinanceState.set_debt_curr, size="2"
                    )),
                    columns="2", spacing="4", width="100%"
                ),
                rx.cond(
                    FinanceState.debt_dest == "存入流动资金 (拿到现金)",
                    custom_form_field("收款现金账户", rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.foreach(
                                FinanceState.cash_accounts,
                                lambda acc: rx.select.item(acc.label, value=acc.id)
                            )
                        ),
                        value=FinanceState.debt_target_acc_id, on_change=FinanceState.set_debt_target_acc_id, size="2"
                    )),
                    rx.fragment()
                ),
                rx.grid(
                    custom_form_field("债权方/资金来源", rx.input(placeholder="如：工商银行、加工厂A", value=FinanceState.debt_source, on_change=FinanceState.set_debt_source, size="2")),
                    custom_form_field("备注说明", rx.input(placeholder="其他说明", value=FinanceState.debt_remark, on_change=FinanceState.set_debt_remark, size="2")),
                    columns="2", spacing="4", width="100%"
                ),
                spacing="3", width="100%"
            ),
            # 偿还债务子表单
            rx.vstack(
                rx.cond(
                    FinanceState.unsettled_debts.length() == 0,
                    rx.callout("✅ 当前无未结负债记录，债务清结完毕！", icon="check_check", color_scheme="green", size="1", width="100%"),
                    rx.vstack(
                        custom_form_field(
                            "选择目标债务",
                            rx.select.root(
                                rx.select.trigger(),
                                rx.select.content(
                                    rx.foreach(
                                        FinanceState.unsettled_debts,
                                        lambda d: rx.select.item(d.label, value=d.id)
                                    )
                                ),
                                placeholder="请选择债务",
                                value=FinanceState.debt_selected_id,
                                on_change=FinanceState.set_debt_selected_id,
                                size="2", width="100%"
                            )
                        ),
                        custom_form_field(
                            "偿还方式",
                            rx.select.root(
                                rx.select.trigger(),
                                rx.select.content(
                                    rx.select.item("💸 资金还款", value="💸 资金还款"),
                                    rx.select.item("🔄 资产抵消", value="🔄 资产抵消")
                                ),
                                value=FinanceState.debt_repay_type,
                                on_change=FinanceState.set_debt_repay_type,
                                size="2", width="100%"
                            )
                        ),
                        rx.cond(
                            FinanceState.debt_repay_type == "💸 资金还款",
                            # 资金偿还
                            rx.vstack(
                                rx.grid(
                                    custom_form_field("偿还金额", rx.input(type="number", placeholder="金额", value=FinanceState.debt_repay_amount.to_string(), on_change=lambda v: FinanceState.set_debt_repay_amount(rx.cond(v != "", v.to(float), 0.0)), size="2")),
                                    custom_form_field("付款现金账户", rx.select.root(
                                        rx.select.trigger(),
                                        rx.select.content(
                                            rx.foreach(
                                                FinanceState.cash_accounts,
                                                lambda acc: rx.select.item(acc.label, value=acc.id)
                                            )
                                        ),
                                        value=FinanceState.debt_repay_source_acc_id, on_change=FinanceState.set_debt_repay_source_acc_id, size="2"
                                    )),
                                    columns="2", spacing="4", width="100%"
                                ),
                                spacing="3", width="100%"
                            ),
                            # 资产抵消
                            rx.grid(
                                custom_form_field("抵消账面资产项", rx.select.root(
                                    rx.select.trigger(),
                                    rx.select.content(
                                        rx.foreach(
                                            FinanceState.offset_assets,
                                            lambda a: rx.select.item(a.label, value=a.id)
                                        )
                                    ),
                                    value=FinanceState.debt_repay_offset_asset_id, on_change=FinanceState.set_debt_repay_offset_asset_id, size="2"
                                )),
                                custom_form_field("抵消挂账金额", rx.input(type="number", placeholder="金额", value=FinanceState.debt_repay_amount.to_string(), on_change=lambda v: FinanceState.set_debt_repay_amount(rx.cond(v != "", v.to(float), 0.0)), size="2")),
                                columns="2", spacing="4", width="100%"
                            )
                        ),
                        custom_form_field("偿还备注", rx.input(placeholder="其他还款说明 (选填)", value=FinanceState.debt_repay_remark, on_change=FinanceState.set_debt_repay_remark, size="2")),
                        spacing="3", width="100%"
                    )
                ),
                spacing="3", width="100%"
            )
        ),
        spacing="3", width="100%"
    )


def fund_transfer_form() -> rx.Component:
    """场景 E: 资金移动"""
    return rx.vstack(
        rx.callout("🔄 内部现金划转（此操作不会改变总净资产，仅在不同账户之间调配流动性）", icon="info", color_scheme="blue", size="1", width="100%"),
        rx.cond(
            FinanceState.cash_accounts.length() < 2,
            rx.callout("⚠️ 当前系统中的现金账户不足 2 个，无法执行内部划拨。", icon="triangle_alert", color_scheme="orange", size="1", width="100%"),
            rx.vstack(
                rx.grid(
                    custom_form_field("转出账户 (From)", rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.foreach(
                                FinanceState.cash_accounts,
                                lambda acc: rx.select.item(acc.label, value=acc.id)
                            )
                        ),
                        value=FinanceState.move_from_asset_id, on_change=FinanceState.set_move_from_asset_id, size="2"
                    )),
                    custom_form_field("转入账户 (To)", rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.foreach(
                                FinanceState.cash_accounts,
                                lambda acc: rx.select.item(acc.label, value=acc.id)
                            )
                        ),
                        value=FinanceState.move_to_asset_id, on_change=FinanceState.set_move_to_asset_id, size="2"
                    )),
                    columns="2", spacing="4", width="100%"
                ),
                custom_form_field(
                    "划拨金额",
                    rx.input(
                        type="number",
                        placeholder="请输入划转金额",
                        value=FinanceState.move_amount.to_string(),
                        on_change=lambda v: FinanceState.set_move_amount(rx.cond(v != "", v.to(float), 0.0)),
                        size="2"
                    )
                ),
                custom_form_field("划转备注", rx.input(placeholder="如：转入日常备用金账户 (选填)", value=FinanceState.move_desc, on_change=FinanceState.set_move_desc, size="2")),
                spacing="3", width="100%"
            )
        ),
        spacing="3", width="100%"
    )


def add_transaction_accordion() -> rx.Component:
    """总收支记账折叠卡片（内含业务大类联动）"""
    return rx.accordion.root(
        rx.accordion.item(
            header=rx.hstack(
                rx.icon("circle_plus", size=14),
                rx.text("新增财务收支 / 兑换 / 债务 / 内部划拨记录", size="2"),
                spacing="1",
                align="center",
            ),
            content=rx.vstack(
                rx.hstack(
                    custom_form_field("流水录入日期", rx.input(type="date", value=FinanceState.f_date, on_change=FinanceState.set_f_date, size="2"), width="auto"),
                    custom_form_field(
                        "业务大类",
                        rx.select.root(
                            rx.select.trigger(width="220px"),
                            rx.select.content(
                                rx.select.item("支出", value="支出"),
                                rx.select.item("收入", value="收入"),
                                rx.select.item("货币兑换", value="货币兑换"),
                                rx.select.item("债务", value="债务"),
                                rx.select.item("资金移动", value="资金移动")
                            ),
                            value=FinanceState.rec_type,
                            on_change=FinanceState.set_rec_type,
                            size="2"
                        ),
                        width="auto"
                    ),
                    spacing="3",
                    align="end",
                    padding_bottom="0.5rem"
                ),
                rx.divider(),
                
                # 联动渲染子表单
                rx.cond(
                    FinanceState.rec_type == "货币兑换",
                    exchange_form(),
                    rx.cond(
                        FinanceState.rec_type == "债务",
                        debt_form(),
                        rx.cond(
                            FinanceState.rec_type == "资金移动",
                            fund_transfer_form(),
                            # 判定普通支出如果是商品成本或资产等，使用批量分割表单
                            rx.cond(
                                rx.Var.create((FinanceState.rec_type == "支出") & (FinanceState.f_category.contains("商品成本") | FinanceState.f_category.contains("资产购入"))),
                                batch_expense_form(),
                                common_single_form()
                            )
                        )
                    )
                ),
                
                rx.divider(),
                rx.button(
                    rx.icon("save", size=14), "确认保存记账",
                    on_click=FinanceState.submit_add_form,
                    size="3",
                    style={"background": "linear-gradient(135deg, #6366f1, #8b5cf6)", "color": "white"},
                    width="100%",
                ),
                spacing="4",
                padding="1.5rem 0",
                width="100%",
                align_items="start"
            ),
            value="add-transaction"
        ),
        collapsible=True,
        width="100%"
    )


# ===================== 表格渲染子组件 =====================

def render_table_row(rec: FinanceRecordItem) -> rx.Component:
    """只读明细列表表格单行"""
    return rx.table.row(
        rx.table.cell(rx.text(rec.date, size="1")),
        rx.table.cell(
            rx.cond(
                rec.type == "收入",
                rx.badge(rec.type, color_scheme="green", variant="soft", size="1"),
                rx.badge(rec.type, color_scheme="red", variant="soft", size="1")
            )
        ),
        rx.table.cell(rx.text(rec.category, size="1", weight="medium")),
        rx.table.cell(
            rx.text(
                rx.fragment(rx.cond(rec.type == "收入", "+", "-"), rec.amount.to_string(), " ", rec.currency),
                size="1",
                weight="bold",
                color=rx.cond(rec.type == "收入", "var(--green-11)", "var(--red-11)")
            )
        ),
        rx.table.cell(rx.text(rec.desc, size="1")),
        rx.table.cell(
            rx.cond(
                rec.url != "",
                rx.link(
                    rx.icon_button(rx.icon("link", size=11), size="1", variant="ghost"),
                    href=rec.url, is_external=True
                ),
                rx.text("-", size="1", color=rx.color("slate", 7))
            )
        ),
        rx.table.cell(rx.text(rec.cny_bal.to_string(), size="1")),
        rx.table.cell(rx.text(rec.jpy_bal.to_string(), size="1")),
    )


def records_table_area() -> rx.Component:
    """真分页流水表格组件"""
    return rx.vstack(
        rx.cond(
            FinanceState.records.length() == 0,
            empty_state("暂无相关财务流水明细数据", "inbox"),
            rx.vstack(
                rx.scroll_area(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("日期", size="1"),
                                rx.table.column_header_cell("类型", size="1"),
                                rx.table.column_header_cell("分类", size="1"),
                                rx.table.column_header_cell("交易金额", size="1"),
                                rx.table.column_header_cell("说明备注", size="1"),
                                rx.table.column_header_cell("链接", size="1"),
                                rx.table.column_header_cell("CNY账户余额", size="1"),
                                rx.table.column_header_cell("JPY账户余额", size="1"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(FinanceState.records, render_table_row)
                        ),
                        size="1", width="100%"
                    ),
                    overflow_x="auto", width="100%", height="500px"
                ),
                
                # 真分页翻页按钮
                rx.cond(
                    FinanceState.total_pages > 1,
                    rx.hstack(
                        rx.spacer(),
                        rx.hstack(
                            rx.button(
                                "⬅️ 上一页",
                                on_click=lambda: FinanceState.change_page(-1),
                                disabled=(FinanceState.page == 1),
                                size="1", variant="soft"
                            ),
                            rx.text(
                                rx.fragment("第 ", FinanceState.page.to_string(), " / ", FinanceState.total_pages.to_string(), " 页"),
                                size="1", color=rx.color("slate", 10), align="center", padding="0.25rem 0.5rem"
                            ),
                            rx.button(
                                "下一页 ➡️",
                                on_click=lambda: FinanceState.change_page(1),
                                disabled=(FinanceState.page == FinanceState.total_pages),
                                size="1", variant="soft"
                            ),
                            spacing="2", align="center"
                        ),
                        rx.spacer(),
                        width="100%", padding_top="0.5rem"
                    ),
                    rx.fragment()
                ),
                width="100%"
            )
        ),
        width="100%"
    )


# ===================== 修改/删除操作子组件 =====================

def edit_transaction_accordion() -> rx.Component:
    """编辑流水记录的折叠选项面板"""
    return rx.accordion.root(
        rx.accordion.item(
            header=rx.hstack(
                rx.icon("pencil", size=14),
                rx.text("修改流水记录 (仅限当页明细)", size="2"),
                spacing="1",
                align="center",
            ),
            content=rx.vstack(
                custom_form_field(
                    "选择要修改的当页记录",
                    rx.select.root(
                        rx.select.trigger(width="400px"),
                        rx.select.content(
                            rx.foreach(
                                FinanceState.records,
                                lambda r: rx.select.item(
                                    rx.fragment(r.date, " | ", r.type, " ", r.amount.to_string(), " | ", r.desc),
                                    value=r.id.to_string()
                                )
                            )
                        ),
                        placeholder="请选择一条记录",
                        value=FinanceState.edit_selected_id,
                        on_change=FinanceState.set_edit_selected_id,
                        size="2", width="100%"
                    )
                ),
                rx.cond(
                    FinanceState.edit_selected_id != "",
                    rx.vstack(
                        rx.hstack(
                            custom_form_field("日期", rx.input(type="date", value=FinanceState.edit_date, on_change=FinanceState.set_edit_date, size="2"), width="auto"),
                            custom_form_field("收支大类", rx.select.root(
                                rx.select.trigger(width="220px"),
                                rx.select.content(
                                    rx.select.item("收入", value="收入"),
                                    rx.select.item("支出", value="支出")
                                ),
                                value=FinanceState.edit_type, on_change=FinanceState.set_edit_type, size="2"
                            ), width="auto"),
                            spacing="3",
                            align="end"
                        ),
                        rx.hstack(
                            custom_form_field("金额", rx.input(type="number", value=FinanceState.edit_amount.to_string(), on_change=lambda v: FinanceState.set_edit_amount(rx.cond(v != "", v.to(float), 0.0)), size="2"), width="auto"),
                            custom_form_field("具体分类", rx.input(value=FinanceState.edit_category, on_change=FinanceState.set_edit_category, size="2"), width="auto"),
                            spacing="3",
                            align="end"
                        ),
                        custom_form_field("操作关联现金账户", rx.select.root(
                            rx.select.trigger(width="220px"),
                            rx.select.content(
                                rx.foreach(
                                    FinanceState.cash_accounts,
                                    lambda acc: rx.select.item(acc.label, value=acc.id)
                                )
                            ),
                            value=FinanceState.edit_acc_id, on_change=FinanceState.set_edit_acc_id, size="2"
                        ), width="auto"),
                        custom_form_field("相关页面网址", rx.input(value=FinanceState.edit_url, on_change=FinanceState.set_edit_url, size="2")),
                        custom_form_field("具体备注/明细说明", rx.input(value=FinanceState.edit_desc, on_change=FinanceState.set_edit_desc, size="2")),
                        rx.button(
                            rx.icon("save", size=13), "保存修改内容",
                            on_click=FinanceState.submit_edit_record,
                            size="2", color_scheme="violet"
                        ),
                        spacing="3", width="100%", padding_top="0.5rem"
                    ),
                    rx.fragment()
                ),
                spacing="3",
                padding="1.5rem 0",
                width="100%",
                align_items="start"
            ),
            value="edit-transaction"
        ),
        collapsible=True,
        width="100%"
    )


def delete_transaction_accordion() -> rx.Component:
    """删除流水记录的折叠选项面板"""
    return rx.accordion.root(
        rx.accordion.item(
            header=rx.hstack(
                rx.icon("trash_2", size=14),
                rx.text("删除流水记录 (仅限当页明细)", size="2"),
                spacing="1",
                align="center",
            ),
            content=rx.vstack(
                custom_form_field(
                    "选择要删除的流水记录",
                    rx.select.root(
                        rx.select.trigger(width="400px"),
                        rx.select.content(
                            rx.foreach(
                                FinanceState.records,
                                lambda r: rx.select.item(
                                    rx.fragment(r.date, " | ", r.amount.to_string(), " | ", r.desc),
                                    value=r.id.to_string()
                                )
                            )
                        ),
                        placeholder="请选择要删除的记录",
                        value=FinanceState.delete_selected_id,
                        on_change=FinanceState.set_delete_selected_id,
                        size="2", width="100%"
                    )
                ),
                rx.cond(
                    FinanceState.delete_selected_id != "",
                    rx.vstack(
                        rx.cond(
                            FinanceState.is_selected_delete_budget_related,
                            rx.hstack(
                                rx.checkbox(
                                    checked=FinanceState.delete_include_budget,
                                    on_change=FinanceState.set_delete_include_budget,
                                ),
                                rx.text("一并物理删除绑定的预算项目记录 (Cascade Delete)", size="2", color=rx.color("orange", 11)),
                                spacing="2",
                                align="center",
                                margin_bottom="0.5rem"
                            ),
                            rx.fragment()
                        ),
                        confirm_dialog(
                            trigger=rx.button(
                                rx.icon("trash_2", size=13), "执行删除流水记录",
                                size="2", color_scheme="red", width="100%"
                            ),
                            title="确认删除该流水？",
                            description="警告：删除流水会将关联的资产、负债、或库存成本明细一并安全级联撤回！如果是【销售收入】流水请必须去线上订单列表删除，严禁在此直接删除核心流水。",
                            confirm_label="确认安全回滚删除",
                            on_confirm=FinanceState.submit_delete_record,
                            confirm_color="red"
                        ),
                        spacing="2",
                        width="100%"
                    ),
                    rx.fragment()
                ),
                spacing="3",
                padding="1.5rem 0",
                width="100%",
                align_items="start"
            ),
            value="delete-transaction"
        ),
        collapsible=True,
        width="100%"
    )


# ===================== 主页面入口 =====================

def finance_page() -> rx.Component:
    """财务流水管理主页面"""
    return page_layout(
        rx.vstack(
            # 1. 独立渲染的记账表单
            add_transaction_accordion(),
            
            # 2. 四大核心当前账户总现金余额指标
            rx.grid(
                stat_indicator_card("CNY 现金当前余额", FinanceState.cur_cny_str, "CNY", "green", "circle_dollar_sign"),
                stat_indicator_card("JPY 现金当前余额", FinanceState.cur_jpy_str, "JPY", "blue", "circle_dollar_sign"),
                stat_indicator_card("JPY 现金折合 CNY", FinanceState.jpy_to_cny_str, "CNY", "purple", "refresh_cw"),
                stat_indicator_card("流动现金总计 (CNY)", FinanceState.total_balance_str, "CNY", "orange", "trending_up"),
                columns="4",
                spacing="3",
                width="100%"
            ),
            
            # 3. 核心流水只读明细表格 (真分页)
            rx.cond(
                FinanceState.is_loading,
                rx.center(rx.spinner(size="3"), padding="4rem", width="100%"),
                data_card(
                    "📜 流水历史明细",
                    records_table_area()
                )
            ),
            
            rx.divider(),
            
            # 4. 独立运行的修改与删除级联回退区
            rx.grid(
                edit_transaction_accordion(),
                delete_transaction_accordion(),
                columns="2",
                spacing="4",
                width="100%",
                align_items="start"
            ),
            
            spacing="4",
            width="100%"
        ),
        title="财务流水"
    )
