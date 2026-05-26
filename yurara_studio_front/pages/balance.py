# yurara_studio_front/pages/balance.py
import reflex as rx
from yurara_studio_front.components.layout import require_auth
from yurara_studio_front.states.balance_state import BalanceState
from yurara_studio_front.states.base_state import BaseState

# 修改 summary_card 函数定义
def summary_card(title: str, cny_val: rx.Var[float], jpy_val: rx.Var[float], color_scheme: str) -> rx.Component:
    exchange_rate = BaseState.exchange_rate 
    
    # 计算折合总额：这是在前端生成的表达式
    total_cny_val = cny_val + (jpy_val * exchange_rate)

    return rx.card(
        rx.vstack(
            rx.heading(title, size="4", color=rx.color(color_scheme, 11)),
            rx.divider(margin_y="2"),
            rx.hstack(
                rx.text("CNY:", weight="bold", color=rx.color("gray", 11)),
                # 使用 .to_string() 转换 Var 为字符串进行渲染
                rx.text(cny_val.to_string(), weight="bold", size="3"),
                justify="between", width="100%"
            ),
            rx.hstack(
                rx.text("JPY:", weight="bold", color=rx.color("gray", 11)),
                rx.text(jpy_val.to_string(), weight="bold", size="3"),
                justify="between", width="100%"
            ),
            rx.hstack(
                rx.text("综合折合 (CNY):", weight="bold", color=rx.color(color_scheme, 11)),
                # 这里直接使用上面算好的 total_cny_val
                rx.text(
                    total_cny_val.to_string(), 
                    weight="bold", size="4", color=rx.color(color_scheme, 11)
                ),
                justify="between", width="100%", margin_top="3",
                padding_top="3", border_top=f"1px dashed {rx.color(color_scheme, 6)}"
            ),
            width="100%"
        ),
        variant="surface",
        width="100%",
    )

def balance_page() -> rx.Component:
    """公司账面概览主页面"""
    return require_auth(
        rx.vstack(
            rx.heading("📊 公司账面概览 (资产负债表)", size="7", margin_bottom="4"),
            
            # --- 顶部四大汇总模块 ---
            rx.grid(
                summary_card("💵 现金总计", BalanceState.cash_cny, BalanceState.cash_jpy, "green"),
                summary_card("🏢 资产总计 (非现金)", BalanceState.pure_asset_cny, BalanceState.pure_asset_jpy, "blue"),
                summary_card("📉 负债总计", BalanceState.total_liab_cny, BalanceState.total_liab_jpy, "orange"),
                summary_card("✨ 净资产", BalanceState.net_cny, BalanceState.net_jpy, "purple"),
                columns="4",
                spacing="4",
                width="100%",
                margin_bottom="6"
            ),
            
            rx.divider(margin_y="4"),
            
            # --- 底部明细表格区域 ---
            rx.grid(
                # 左侧：负债明细
                rx.vstack(
                    rx.heading("📉 负债明细", size="5"),
                    rx.cond(
                        BalanceState.liabilities_data.length() > 0,
                        rx.data_table(
                            data=BalanceState.liabilities_data,
                            columns=["项目", "CNY", "JPY"],
                            width="100%",
                        ),
                        rx.text("暂无负债记录", color=rx.color("gray", 11))
                    ),
                    width="100%",
                    padding="4",
                    bg="white",
                    border_radius="8px",
                    box_shadow="sm"
                ),
                
                # 右侧：资本/权益明细
                rx.vstack(
                    rx.heading("💎 资本与权益明细", size="5"),
                    rx.cond(
                        BalanceState.equities_data.length() > 0,
                        rx.data_table(
                            data=BalanceState.equities_data,
                            columns=["项目", "CNY", "JPY"],
                            width="100%",
                        ),
                        rx.text("暂无资本记录", color=rx.color("gray", 11))
                    ),
                    width="100%",
                    padding="4",
                    bg="white",
                    border_radius="8px",
                    box_shadow="sm"
                ),
                columns="2", # 2列网格布局
                spacing="6",
                width="100%"
            ),
            width="100%",
            max_width="1400px",
        )
    )