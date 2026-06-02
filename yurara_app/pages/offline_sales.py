# yurara_app/pages/offline_sales.py
"""
线下展会 POS 收银台页面。
支持双列收银大屏模式、PayPay 1.98% 支付手续费自动清算、木桶原料上限配装校验、大货自动预扣减，
以及多收银模板创建/更新/注销配置。
"""
import reflex as rx
from ..state.auth_state import AuthState
from ..state.offline_sales_state import OfflineSalesState, POSTemplateModel, POSTemplateItemModel, CartItemModel, POSOrderRow
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state, confirm_dialog


def cashier_product_card(item: POSTemplateItemModel) -> rx.Component:
    """渲染收银台左侧的商品购买卡片"""
    is_out_of_stock = (item.remaining_quantity <= 0)
    
    return rx.card(
        rx.vstack(
            # 缩略图/渐变占位符
            rx.cond(
                item.image_data != "",
                rx.image(src=item.image_data, width="100%", height="90px", object_fit="cover", border_radius="4px"),
                rx.center(
                    rx.icon("shopping_bag", size=20, color=rx.color("violet", 8)),
                    width="100%",
                    height="90px",
                    background="linear-gradient(135deg, var(--violet-2) 0%, var(--violet-3) 100%)",
                    border_radius="4px"
                )
            ),
            
            # 商品信息
            rx.vstack(
                rx.text(item.product_name, size="1", weight="bold", line_clamp=1, width="100%"),
                rx.text(item.variant, size="1", color=rx.color("slate", 10), line_clamp=1, width="100%"),
                spacing="0",
                width="100%"
            ),
            
            # 库存与价格
            rx.cond(
                is_out_of_stock,
                rx.badge("🚫 已售罄", color_scheme="red", variant="solid", size="1", width="100%", justify="center"),
                rx.badge(rx.fragment("📦 余量: ", item.remaining_quantity.to_string()), color_scheme="green", variant="soft", size="1", width="100%", justify="center")
            ),
            
            rx.button(
                rx.cond(
                    is_out_of_stock,
                    "无库存",
                    rx.fragment("¥ ", item.preset_price.to_string(), " ➕")
                ),
                on_click=lambda: OfflineSalesState.add_to_cart(
                    item.product_name, item.variant, item.preset_price, item.max_limit, item.image_data
                ),
                disabled=is_out_of_stock,
                size="1",
                color_scheme="violet",
                width="100%"
            ),
            spacing="2",
            align_items="center",
            width="100%"
        ),
        padding="0.5rem",
        style={"minWidth": "110px"}
    )


def cashier_cart_item(ci: CartItemModel) -> rx.Component:
    """渲染购物车中的单项清单"""
    return rx.hstack(
        rx.cond(
            ci.image_data != "",
            rx.image(src=ci.image_data, width="32px", height="32px", object_fit="cover", border_radius="3px"),
            rx.center(
                rx.icon("shopping_bag", size=14, color=rx.color("violet", 8)),
                width="32px",
                height="32px",
                background=rx.color("slate", 3),
                border_radius="3px"
            )
        ),
        rx.vstack(
            rx.text(ci.product_name, size="1", weight="bold", line_clamp=1),
            rx.text(ci.variant, size="1", color=rx.color("slate", 10)),
            spacing="0",
            align_items="start",
            flex="1"
        ),
        rx.text(rx.fragment("x", ci.qty.to_string()), size="1", weight="bold"),
        rx.icon_button(
            rx.icon("minus", size=12),
            on_click=lambda: OfflineSalesState.remove_from_cart(ci.product_name, ci.variant),
            size="1",
            variant="ghost",
            color_scheme="red"
        ),
        spacing="2",
        align_items="center",
        width="100%",
        padding="0.25rem 0",
        border_bottom="1px dashed var(--slate-4)"
    )


def ledger_order_row(o: POSOrderRow) -> rx.Component:
    """渲染交易历史流水行"""
    return rx.table.row(
        rx.table.cell(rx.text(o.order_no, size="1", weight="bold")),
        rx.table.cell(rx.text(o.date, size="1")),
        rx.table.cell(rx.text(o.items_str, size="1", line_clamp=1)),
        rx.table.cell(rx.text(o.original_amount.to_string(), size="1")),
        rx.table.cell(rx.text(o.received_amount.to_string(), size="1", weight="bold", color="green")),
        rx.table.cell(rx.text(o.notes, size="1", line_clamp=1, color=rx.color("slate", 9))),
        rx.table.cell(
            confirm_dialog(
                trigger=rx.button(
                    rx.icon("trash-2", size=14),
                    "删除并回滚",
                    color_scheme="red",
                    size="1",
                    variant="soft",
                ),
                title="确定要删除此订单并回滚吗？",
                description=rx.fragment(
                    "此操作将永久删除展会订单 ",
                    o.order_no,
                    "，回滚已扣减的模板分配额度、还原出货仓库对应的实物库存，并全额扣减已记账的现金流水与资产！是否确定？"
                ),
                confirm_label="确定删除",
                on_confirm=OfflineSalesState.delete_offline_order(o.order_no),
            )
        ),
    )


def tpl_assign_product_card(r: dict) -> rx.Component:
    """模板配置中可分派商品的勾选卡片"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.checkbox(
                    checked=r["is_selected"],
                    on_change=lambda _: OfflineSalesState.toggle_item_assign(r["product_name"], r["variant"]),
                    size="1"
                ),
                rx.cond(
                    r["img_data"] != "",
                    rx.image(src=r["img_data"], width="24px", height="24px", object_fit="cover", border_radius="3px"),
                    rx.center(rx.icon("image", size=12), width="24px", height="24px", background=rx.color("slate", 3), border_radius="3px")
                ),
                rx.vstack(
                    rx.text(r["product_name"], size="1", weight="bold", line_clamp=1),
                    rx.text(rx.fragment(r["variant"], " (大货整套上限:", r["max_stock"].to_string(), ")"), size="1", color=rx.color("slate", 10)),
                    spacing="0",
                    align_items="start"
                ),
                spacing="2",
                align_items="center",
                width="100%"
            ),
            rx.cond(
                r["is_selected"],
                rx.grid(
                    custom_form_field(
                        "预设售价",
                        rx.input(
                            type="number",
                            value=r["preset_price"].to_string(),
                            on_change=lambda val: OfflineSalesState.update_item_assign_price(r["product_name"], r["variant"], val),
                            size="1",
                        )
                    ),
                    custom_form_field(
                        "分配余量",
                        rx.input(
                            type="number",
                            value=r["quantity"].to_string(),
                            on_change=lambda val: OfflineSalesState.update_item_assign_qty(r["product_name"], r["variant"], val),
                            size="1",
                        )
                    ),
                    columns="2",
                    spacing="2",
                    width="100%"
                ),
                rx.fragment()
            ),
            spacing="2",
            width="100%"
        ),
        padding="0.5rem"
    )


def cashier_pos_tab() -> rx.Component:
    """1. POS收银台大屏组件"""
    return rx.cond(
        ~OfflineSalesState.has_templates,
        rx.callout("⚠️ 线下展会收银模板为空！请先点击右侧“模板配置”Tab建立至少一个收银模板配置。", icon="triangle_alert", color_scheme="orange", size="2", width="100%"),
        
        # 收银场景主显示
        rx.vstack(
            # 顶部操作栏
            rx.hstack(
                rx.text("当前活动收银模板：", size="2", weight="medium", margin_top="0.5rem"),
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            OfflineSalesState.template_options,
                            lambda opt: rx.select.item(opt, value=opt)
                        )
                    ),
                    value=OfflineSalesState.template_selected_value,
                    on_change=OfflineSalesState.change_template_by_option,
                    size="2",
                    style={"maxWidth": "250px"},
                ),
                rx.spacer(),
                rx.button(
                    rx.cond(OfflineSalesState.show_history_only, "🔙 返回收银台", "📜 历史交易流水"),
                    on_click=OfflineSalesState.toggle_history_only,
                    size="2",
                    variant="soft",
                    color_scheme="violet"
                ),
                rx.button(
                    rx.cond(OfflineSalesState.is_fullscreen, "📴 退出专注全屏", "📺 开启收银全屏"),
                    on_click=OfflineSalesState.toggle_fullscreen,
                    size="2",
                    variant="soft",
                    color_scheme=rx.cond(OfflineSalesState.is_fullscreen, "orange", "blue")
                ),
                spacing="2",
                align="center",
                width="100%"
            ),
            
            rx.divider(),
            
            # 分支 A：历史记录列表
            rx.cond(
                OfflineSalesState.show_history_only,
                rx.vstack(
                    rx.heading(rx.fragment("📜 已结账历史交易全览"), size="3", weight="bold"),
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("交易单号", size="1"),
                                rx.table.column_header_cell("成交日期", size="1"),
                                rx.table.column_header_cell("购买商品明细", size="1"),
                                rx.table.column_header_cell("交易额", size="1"),
                                rx.table.column_header_cell("实收记账额", size="1"),
                                rx.table.column_header_cell("流向备注", size="1"),
                                rx.table.column_header_cell("操作", size="1"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(OfflineSalesState.pos_orders, ledger_order_row)
                        ),
                        size="1",
                        width="100%"
                    ),
                    spacing="2",
                    width="100%"
                ),
                
                # 分支 B：核心双列收银大屏
                rx.grid(
                    # 左侧：商品选购区 (矩阵)
                    rx.vstack(
                        rx.hstack(
                            rx.text("🛍️ 展会选购面板：", size="2", weight="bold"),
                            rx.badge(
                                rx.fragment("大货库存提取来源仓: ", OfflineSalesState.active_template.warehouse_name), 
                                color_scheme="orange", 
                                size="1"
                            ),
                        ),
                        rx.grid(
                            rx.foreach(
                                OfflineSalesState.active_template_items,
                                cashier_product_card
                            ),
                            columns="4",
                            spacing="3",
                            width="100%"
                        ),
                        
                        # 非全屏模式下：原版底部交易记录
                        rx.cond(
                            ~OfflineSalesState.is_fullscreen,
                            rx.fragment(
                                rx.divider(margin_top="1.5rem"),
                                rx.text("📋 近期本地模板成交流水 (快捷对账)", size="1", weight="bold", color="slate"),
                                rx.scroll_area(
                                    rx.table.root(
                                        rx.table.header(
                                            rx.table.row(
                                                rx.table.column_header_cell("交易单号", size="1"),
                                                rx.table.column_header_cell("成交日期", size="1"),
                                                rx.table.column_header_cell("商品明细", size="1"),
                                                rx.table.column_header_cell("原价小计", size="1"),
                                                rx.table.column_header_cell("实收净额", size="1"),
                                                rx.table.column_header_cell("备注", size="1"),
                                                rx.table.column_header_cell("操作", size="1"),
                                            )
                                        ),
                                        rx.table.body(
                                            rx.foreach(OfflineSalesState.pos_orders, ledger_order_row)
                                        ),
                                        size="1",
                                        width="100%"
                                    ),
                                    max_height="220px",
                                    width="100%"
                                ),
                            ),
                            rx.fragment()
                        ),
                        spacing="3",
                        width="100%"
                    ),
                    
                    # 右侧：POS 结账购物车
                    rx.card(
                        rx.vstack(
                            rx.heading("🧾 POS 结账清单", size="3", weight="bold"),
                            rx.divider(),
                            
                            # 购物车列表
                            rx.cond(
                                ~OfflineSalesState.is_cart_empty,
                                rx.vstack(
                                    rx.scroll_area(
                                        rx.vstack(
                                            rx.foreach(OfflineSalesState.cart, cashier_cart_item),
                                            spacing="1",
                                            width="100%"
                                        ),
                                        max_height="250px",
                                        width="100%"
                                    ),
                                    rx.button(
                                        "清空选购",
                                        on_click=OfflineSalesState.clear_cart,
                                        size="1",
                                        variant="soft",
                                        color_scheme="red",
                                        width="100%"
                                    ),
                                    spacing="2",
                                    width="100%"
                                ),
                                rx.center(
                                    rx.text("购物车为空", size="2", color=rx.color("slate", 9)),
                                    padding="2rem 0",
                                    width="100%"
                                )
                            ),
                            
                            rx.divider(),
                            
                            # 支付方式选择
                            rx.vstack(
                                rx.text("💵 选择支付媒介：", size="1", weight="bold"),
                                rx.grid(
                                    rx.button(
                                        "💵 现金支付",
                                        on_click=lambda: OfflineSalesState.set_pay_method("现金"),
                                        color_scheme="violet",
                                        variant=rx.cond(OfflineSalesState.pay_method == "现金", "solid", "soft"),
                                        size="2"
                                    ),
                                    rx.button(
                                        "📱 PayPay 扫码",
                                        on_click=lambda: OfflineSalesState.set_pay_method("PayPay"),
                                        color_scheme="violet",
                                        variant=rx.cond(OfflineSalesState.pay_method == "PayPay", "solid", "soft"),
                                        size="2"
                                    ),
                                    columns="2",
                                    spacing="2",
                                    width="100%"
                                ),
                                spacing="2",
                                width="100%"
                            ),
                            
                            rx.divider(),
                            
                            # 金额结算显示
                            rx.vstack(
                                rx.hstack(
                                    rx.text("应收总价:", size="2", weight="bold"),
                                    rx.spacer(),
                                    rx.text(OfflineSalesState.cart_total_str, size="4", weight="bold", color="red"),
                                    width="100%"
                                ),
                                rx.cond(
                                    OfflineSalesState.pay_method == "PayPay",
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text("PayPay 扣减扣点 (1.98%):", size="1", color="slate"),
                                            rx.spacer(),
                                            rx.text(OfflineSalesState.paypay_fee_str, size="1", color="red"),
                                            width="100%"
                                        ),
                                        rx.hstack(
                                            rx.text("预计实际收款入账金额:", size="1", weight="medium", color="green"),
                                            rx.spacer(),
                                            rx.text(OfflineSalesState.paypay_receive_str, size="2", weight="bold", color="green"),
                                            width="100%"
                                        ),
                                        spacing="1",
                                        width="100%"
                                    ),
                                    rx.fragment()
                                ),
                                spacing="1",
                                width="100%"
                            ),
                            
                            # 收款账户绑定
                            custom_form_field(
                                "物理入账账户",
                                rx.select.root(
                                    rx.select.trigger(),
                                    rx.select.content(
                                        rx.foreach(
                                            OfflineSalesState.cash_account_options,
                                            lambda acc: rx.select.item(acc, value=acc)
                                        )
                                    ),
                                    value=OfflineSalesState.selected_account_name,
                                    on_change=OfflineSalesState.set_selected_account_name,
                                    size="2",
                                    width="100%"
                                )
                            ),
                            
                            # 巨大化结账按钮
                            rx.button(
                                "✅ 完成交易并扣减库存记账",
                                on_click=OfflineSalesState.submit_pos_checkout,
                                disabled=OfflineSalesState.is_cart_empty,
                                size="3",
                                color_scheme="green",
                                width="100%",
                                style={"height": "65px", "borderRadius": "8px", "marginTop": "0.5rem"}
                            ),
                            spacing="3",
                            width="100%"
                        ),
                        padding="1rem",
                        width="100%"
                    ),
                    columns="12",
                    spacing="4",
                    width="100%",
                    style={"gridTemplateColumns": "8fr 4fr"}
                )
            ),
            spacing="4",
            width="100%"
        )
    )


def template_config_tab() -> rx.Component:
    """2. 模板配置编辑配置管理组件"""
    return rx.grid(
        # 左侧：新建与编辑控制面板
        rx.vstack(
            rx.segmented_control.root(
                rx.segmented_control.item("➕ 新建收银场景模板", value="create"),
                rx.segmented_control.item("✏️ 编辑/注销现有模板", value="edit"),
                value=rx.cond(OfflineSalesState.is_edit_mode, "edit", "create"),
                on_change=OfflineSalesState.change_template_mode,
                size="2",
                width="100%",
            ),
            rx.divider(),
            
            # 分支 A: 编辑模式下先选模板
            rx.cond(
                OfflineSalesState.is_edit_mode,
                custom_form_field(
                    "选择待配置模板",
                    rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.foreach(
                                OfflineSalesState.template_options,
                                lambda opt: rx.select.item(opt, value=opt)
                            )
                        ),
                        placeholder="请选择模板进行编辑...",
                        on_change=OfflineSalesState.select_template_for_edit_by_option,
                        size="2",
                        width="100%"
                    )
                ),
                rx.fragment()
            ),
            
            # 基础属性录入
            custom_form_field(
                "模板场景名称",
                rx.input(
                    placeholder="如：2026年广州CP展会",
                    value=OfflineSalesState.tpl_name,
                    on_change=OfflineSalesState.set_tpl_name,
                    size="2",
                    width="100%"
                )
            ),
            custom_form_field(
                "代号/单号前缀",
                rx.input(
                    placeholder="如：GZCP26",
                    value=OfflineSalesState.tpl_code,
                    on_change=OfflineSalesState.set_tpl_code,
                    size="2",
                    width="100%"
                )
            ),
            custom_form_field(
                "物理结算币种",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.select.item("CNY", value="CNY"),
                        rx.select.item("JPY", value="JPY")
                    ),
                    value=OfflineSalesState.tpl_currency,
                    on_change=OfflineSalesState.set_tpl_currency,
                    size="2",
                    width="100%"
                )
            ),
            custom_form_field(
                "物理出货指定大货仓库",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            OfflineSalesState.warehouse_options,
                            lambda w: rx.select.item(w, value=w)
                        )
                    ),
                    value=OfflineSalesState.tpl_wh_name,
                    on_change=OfflineSalesState.set_tpl_wh_name,
                    size="2",
                    width="100%"
                )
            ),
            custom_form_field(
                "销售平台",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            OfflineSalesState.platform_options,
                            lambda p: rx.select.item(p, value=p)
                        )
                    ),
                    value=OfflineSalesState.tpl_platform,
                    on_change=OfflineSalesState.set_tpl_platform,
                    size="2",
                    width="100%"
                )
            ),
            
            rx.divider(),
            
            # 保存与删除动作
            rx.hstack(
                rx.button(
                    "💾 保存模板配置",
                    on_click=OfflineSalesState.save_template,
                    size="3",
                    color_scheme="green",
                    width="100%"
                ),
                rx.cond(
                    OfflineSalesState.is_edit_mode,
                    rx.button(
                        "🗑️ 注销此模板",
                        on_click=lambda: OfflineSalesState.delete_template(OfflineSalesState.tpl_id),
                        size="3",
                        color_scheme="red",
                        width="100%"
                    ),
                    rx.fragment()
                ),
                spacing="3",
                width="100%"
            ),
            spacing="3",
            width="100%"
        ),
        
        # 右侧：商品分配勾选表与售价/限量设置
        rx.vstack(
            rx.hstack(
                rx.text("🧩 配置该模板分配的货品清单：", size="2", weight="bold"),
                rx.spacer(),
                rx.badge("实时木桶原理配装上限校验", color_scheme="violet")
            ),
            rx.scroll_area(
                rx.grid(
                    rx.foreach(
                        OfflineSalesState.all_assignable_items,
                        tpl_assign_product_card
                    ),
                    columns="2",
                    spacing="3",
                    width="100%"
                ),
                max_height="620px",
                width="100%"
            ),
            spacing="3",
            width="100%"
        ),
        columns="12",
        spacing="4",
        width="100%",
        style={"gridTemplateColumns": "4fr 8fr"}
    )


def offline_sales_page() -> rx.Component:
    """线下销售POS主页面入口"""
    return page_layout(
        rx.vstack(
            rx.cond(
                OfflineSalesState.is_fullscreen,
                rx.fragment(),
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger("💻 POS 收银台", value="pos"),
                        rx.tabs.trigger("⚙️ 模板配置", value="template"),
                    ),
                    value=OfflineSalesState.active_tab,
                    on_change=OfflineSalesState.select_tab,
                    width="100%",
                ),
            ),
            
            rx.card(
                rx.tabs.root(
                    rx.tabs.content(cashier_pos_tab(), value="pos"),
                    rx.tabs.content(template_config_tab(), value="template"),
                    value=OfflineSalesState.active_tab
                ),
                width="100%",
                padding="1rem",
            ),
            spacing="4",
            width="100%"
        ),
        title="🏪 线下展会模式",
        hide_sidebar=OfflineSalesState.is_fullscreen,
        hide_header=OfflineSalesState.is_fullscreen,
    )
