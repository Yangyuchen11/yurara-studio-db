# yurara_app/pages/schedule.py
"""
工期日程管理视图层。
包含：
1. 36 旬宽版全景甘特图 (每旬 100px，全年 3600px，横向舒适滚动，14px 宽大易点滑块)
2. 左侧「业务主体 / 商品项目」列完全固定 (position: sticky)，横向滑动时始终锁在左侧
3. 按实际天数精确像素分割定位 (如 2月25日 居中对齐在下旬格子中，节点宽度由实际天数驱动)
4. 节点左右微调箭头 (◀ / ▶) 范围放大，点击标签其余任意区域直接打开编辑弹窗
5. 默认打开时自动平滑滚动并将当前月份居左展示
6. 近期关键节点提醒卡片宽度扩展 1.2 倍 (280px) 且固定高度美观排版，优先显示具体日期
7. 阶段节点弹窗支持独立勾选「不设置具体开始日期」与「不设置具体结束日期」，4 个旬度下拉框 2x2 严格等宽对齐
"""
import reflex as rx
from ..state.schedule_state import ScheduleState, ScheduleNodeItem, ScheduleLaneItem
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field


PERIOD_NAMES = ["上", "中", "下"]

SLOT_WIDTH = "var(--timeline-slot-width, 100px)"
MONTH_WIDTH = "calc(var(--timeline-slot-width, 100px) * 3)"
GRID_WIDTH = "calc(var(--timeline-slot-width, 100px) * 36)"
HEADER_LEFT_WIDTH = "240px"
TOTAL_WIDTH = "calc(240px + var(--timeline-slot-width, 100px) * 36)"


def metric_card(label: str, value: rx.Var, icon: str, color_scheme: str = "gray", badge_text: str = "") -> rx.Component:
    """统计概览卡片"""
    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.text(label, size="1", color=rx.color("slate", 10), weight="medium"),
                    rx.cond(
                        badge_text != "",
                        rx.badge(badge_text, size="1", color_scheme="violet", variant="soft"),
                        rx.fragment()
                    ),
                    spacing="2",
                    align="center"
                ),
                rx.text(value, size="5", weight="bold", color=rx.color(color_scheme, 11)),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.center(
                rx.icon(icon, size=22, color=rx.color(color_scheme, 9)),
                background=rx.color(color_scheme, 3),
                border_radius="10px",
                width="40px",
                height="40px",
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        variant="surface",
        size="1",
        width="100%",
    )


def node_gantt_bar(node: ScheduleNodeItem, is_compact: bool = False) -> rx.Component:
    """时间轴节点条块组件 (支持点击主体打开编辑，左右扩大范围微调箭头)"""
    status_icon = rx.cond(
        node.status == "completed",
        "badge-check",
        rx.cond(
            node.status == "in_progress",
            "zap",
            rx.cond(node.status == "delayed", "alert-triangle", "clock")
        )
    )

    return rx.hover_card.root(
        rx.hover_card.trigger(
            rx.box(
                rx.hstack(
                    # 快捷前移按钮 (加大可点击范围，点击微调前移 1 旬)
                    rx.icon_button(
                        rx.icon("chevron-left", size=13),
                        size="1",
                        variant="ghost",
                        color_scheme="gray",
                        cursor="pointer",
                        on_click=ScheduleState.shift_node(node.id, -1),
                        title="前移一旬",
                        padding="0",
                        min_width="20px",
                        width="20px",
                        height="24px" if is_compact else "26px",
                        flex_shrink="0",
                        _hover={"background": "rgba(0,0,0,0.12)"},
                    ),
                    # 主体内容 (点击此区域打开编辑弹窗，占满除箭头外的全部范围)
                    rx.hstack(
                        rx.icon(status_icon, size=12),
                        rx.text(
                            node.display_title,
                            size="1",
                            weight="bold",
                            white_space="nowrap",
                            overflow="hidden",
                            text_overflow="ellipsis",
                        ),
                        spacing="1",
                        align="center",
                        flex="1",
                        height="100%",
                        cursor="pointer",
                        on_click=ScheduleState.open_edit_dialog(node),
                        overflow="hidden",
                        min_width="0",
                    ),
                    # 快捷后移按钮 (加大可点击范围，点击微调后移 1 旬)
                    rx.icon_button(
                        rx.icon("chevron-right", size=13),
                        size="1",
                        variant="ghost",
                        color_scheme="gray",
                        cursor="pointer",
                        on_click=ScheduleState.shift_node(node.id, 1),
                        title="后移一旬",
                        padding="0",
                        min_width="20px",
                        width="20px",
                        height="24px" if is_compact else "26px",
                        flex_shrink="0",
                        _hover={"background": "rgba(0,0,0,0.12)"},
                    ),
                    spacing="1",
                    align="center",
                    width="100%",
                    height="100%",
                    padding="0 1px",
                    overflow="hidden",
                ),
                style={
                    "position": "absolute",
                    "left": f"calc({node.left_px}px * var(--timeline-zoom, 1))",
                    "width": f"calc({node.width_px}px * var(--timeline-zoom, 1))",
                    "minWidth": "46px",
                    "top": "3px",
                    "height": "26px" if is_compact else "32px",
                    "borderRadius": "6px",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.12)",
                    "transition": "all 0.15s ease",
                    "zIndex": "2",
                    "pointerEvents": "auto",
                    "userSelect": "none",
                    "overflow": "hidden",
                },
                background=rx.color(node.color, 4),
                border=f"1px solid {rx.color(node.color, 7)}",
                color=rx.color(node.color, 11),
                _hover={
                    "background": rx.color(node.color, 5),
                    "transform": "translateY(-1px)",
                    "boxShadow": "0 3px 8px rgba(0,0,0,0.2)",
                    "zIndex": "10",
                },
            )
        ),
        rx.hover_card.content(
            rx.vstack(
                rx.hstack(
                    rx.badge(node.status_label, size="1", color_scheme="violet"),
                    rx.badge(rx.cond(node.item_type == "product", "👗 商品工期", rx.cond(node.item_type == "event", "🎪 展会活动", "📌 其他日程")), size="1", variant="outline"),
                    spacing="2",
                    align="center",
                ),
                rx.text(node.display_title, size="2", weight="bold"),
                rx.hstack(
                    rx.icon("calendar", size=12, color=rx.color("slate", 9)),
                    rx.text(node.range_str, size="1", color=rx.color("slate", 10), weight="medium"),
                    spacing="1",
                    align="center",
                ),
                rx.cond(
                    node.remarks != "",
                    rx.text(node.remarks, size="1", color=rx.color("slate", 9), style={"maxWidth": "280px"}),
                    rx.fragment()
                ),
                rx.divider(margin_y="0.25rem"),
                rx.hstack(
                    rx.button("✏️ 编辑详情", size="1", variant="soft", color_scheme="violet", on_click=ScheduleState.open_edit_dialog(node)),
                    rx.button("🗑️ 删除节点", size="1", variant="ghost", color_scheme="red", on_click=ScheduleState.delete_node(node.id)),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="2",
                align="start",
                padding="0.25rem",
            ),
            max_width="340px",
        ),
    )


def timeline_clickable_grid_bg(lane_type: str, product_id: int, lane_title: str) -> rx.Component:
    """生成 36 列可点击背景格子 (点击任意格子直接打开节点创建弹窗)"""
    return rx.box(
        *[
            rx.box(
                width=SLOT_WIDTH,
                height="100%",
                border_right=f"1px dashed {rx.color('slate', 4)}",
                background=rx.cond(
                    ci + 1 == ScheduleState.curr_col_index,
                    "rgba(236, 72, 153, 0.06)",
                    "transparent"
                ),
                _hover={
                    "background": "rgba(139, 92, 246, 0.05)",
                    "cursor": "cell",
                },
                position="absolute",
                left=f"calc(var(--timeline-slot-width, 100px) * {ci})",
                top="0",
                z_index="1",
                on_click=ScheduleState.open_add_dialog_for_slot(lane_type, product_id, ci + 1, lane_title),
                title=f"点击创建阶段节点 ({((ci)//3)+1}月{PERIOD_NAMES[ci%3]}旬)",
            )
            for ci in range(36)
        ],
        position="absolute",
        left="0",
        top="0",
        width=GRID_WIDTH,
        height="100%",
    )


def timeline_gantt_matrix() -> rx.Component:
    """36 旬度全景甘特图时间轴矩阵视图 (左侧列完全固定 Sticky，按实际天数像素定位)"""
    
    # 顶部月份表头 (1-12 月，每月中跨 3 旬，各 300px)
    month_header = rx.hstack(
        # 左侧固定标题占位 (Sticky 绝对固定在最左侧)
        rx.hstack(
            rx.text("业务主体 / 商品项目", size="1", weight="bold", color=rx.color("slate", 10)),
            rx.spacer(),
            rx.tooltip(
                rx.icon_button(
                    rx.icon("unfold_vertical", size=13),
                    size="1",
                    variant="surface",
                    color_scheme="violet",
                    on_click=ScheduleState.toggle_all_lanes_expand,
                ),
                content="一键全部展开 / 全部折叠",
            ),
            width=HEADER_LEFT_WIDTH,
            min_width=HEADER_LEFT_WIDTH,
            padding="0.6rem 0.85rem",
            border_right=f"1px solid {rx.color('slate', 6)}",
            align="center",
            style={
                "position": "sticky",
                "left": "0",
                "zIndex": "20",
                "background": rx.color("slate", 3),
                "boxShadow": "2px 0 5px rgba(0,0,0,0.06)",
            },
        ),
        # 右侧 12 个月份表头
        rx.hstack(
            *[
                rx.center(
                    rx.text(f"{m} 月", size="2", weight="bold", color=rx.color("slate", 11)),
                    width=MONTH_WIDTH,
                    min_width=MONTH_WIDTH,
                    padding="0.45rem 0",
                    border_right=f"1px solid {rx.color('slate', 5)}",
                    background=rx.color("slate", 3),
                )
                for m in range(1, 13)
            ],
            spacing="0",
        ),
        spacing="0",
        align="center",
        border_bottom=f"1px solid {rx.color('slate', 5)}",
        background=rx.color("slate", 2),
        width=TOTAL_WIDTH,
    )

    # 次级旬度表头 (36 旬: 上 / 中 / 下，各 100px)
    sub_period_header = rx.hstack(
        rx.box(
            rx.text("工期阶段泳道", size="1", color=rx.color("slate", 8)),
            width=HEADER_LEFT_WIDTH,
            min_width=HEADER_LEFT_WIDTH,
            padding="0.3rem 0.85rem",
            border_right=f"1px solid {rx.color('slate', 6)}",
            style={
                "position": "sticky",
                "left": "0",
                "zIndex": "20",
                "background": rx.color("slate", 3),
                "boxShadow": "2px 0 5px rgba(0,0,0,0.06)",
            },
        ),
        rx.hstack(
            *[
                rx.center(
                    rx.hstack(
                        rx.text(PERIOD_NAMES[col_i % 3], size="1", color=rx.color("slate", 9), weight="medium"),
                        rx.cond(
                            col_i + 1 == ScheduleState.curr_col_index,
                            rx.badge("今", size="1", color_scheme="pink", variant="solid", style={"padding": "0 2px", "fontSize": "9px"}),
                            rx.fragment()
                        ),
                        spacing="1",
                        align="center",
                    ),
                    width=SLOT_WIDTH,
                    min_width=SLOT_WIDTH,
                    padding="0.3rem 0",
                    border_right=f"1px solid {rx.color('slate', 4)}",
                    background=rx.cond(
                        col_i + 1 == ScheduleState.curr_col_index,
                        "rgba(236, 72, 153, 0.12)",
                        "transparent"
                    ),
                )
                for col_i in range(36)
            ],
            spacing="0",
        ),
        spacing="0",
        align="center",
        border_bottom=f"1px solid {rx.color('slate', 6)}",
        background=rx.color("slate", 2),
        width=TOTAL_WIDTH,
    )

    def render_node_single_row(node: ScheduleNodeItem) -> rx.Component:
        """展开模式下，每个节点独占一行 (整行空白处均可点击以新建节点，节点像素绝对定位)"""
        return rx.box(
            timeline_clickable_grid_bg(node.item_type, node.product_id, node.display_title),
            node_gantt_bar(node, is_compact=False),
            position="relative",
            width=GRID_WIDTH,
            min_width=GRID_WIDTH,
            min_height="38px",
            height="38px",
            border_bottom=f"1px dotted {rx.color('slate', 4)}",
        )

    def render_lane_row(lane: ScheduleLaneItem) -> rx.Component:
        """单条泳道行 (左侧 Sticky 绝对固定、醒目折叠按钮、删除整行按钮、多行/单行自适应)"""
        return rx.hstack(
            # 左侧泳道标题、折叠按钮与删除行按钮 (Sticky 锁定在最左侧)
            rx.hstack(
                rx.vstack(
                    rx.text(lane.lane_title, size="1", weight="bold", line_clamp=1),
                    rx.hstack(
                        rx.badge(lane.badge_label, size="1", variant="surface", color_scheme="gray"),
                        # 醒目的展开/折叠切换按钮
                        rx.cond(
                            lane.node_count > 0,
                            rx.button(
                                rx.cond(lane.is_expanded, rx.icon("chevron-up", size=12), rx.icon("chevron-down", size=12)),
                                rx.cond(lane.is_expanded, "收起", lane.node_count_str),
                                size="1",
                                variant="surface",
                                color_scheme="violet",
                                padding="0 6px",
                                height="20px",
                                border_radius="6px",
                                on_click=ScheduleState.toggle_lane_expand(lane.lane_id),
                                title="点击展开/折叠多行视图",
                            ),
                            rx.fragment()
                        ),
                        spacing="2",
                        align="center",
                    ),
                    spacing="1",
                    align="start",
                    overflow="hidden",
                ),
                rx.spacer(),
                # 删除整行/整项目按钮
                rx.alert_dialog.root(
                    rx.alert_dialog.trigger(
                        rx.icon_button(
                            rx.icon("trash_2", size=13),
                            size="1",
                            variant="ghost",
                            color_scheme="red",
                            title="删除此项目行及所有节点",
                        )
                    ),
                    rx.alert_dialog.content(
                        rx.alert_dialog.title("确认清理此业务项目？"),
                        rx.alert_dialog.description(f"将删除「{lane.lane_title}」及其下的全部工期阶段记录，该操作无法撤销。"),
                        rx.hstack(
                            rx.alert_dialog.cancel(rx.button("取消", variant="soft", color_scheme="gray")),
                            rx.alert_dialog.action(rx.button("确认删除", color_scheme="red", on_click=ScheduleState.delete_lane(lane.lane_id, lane.lane_type, lane.product_id, lane.lane_title))),
                            spacing="3",
                            justify="end",
                            margin_top="0.75rem",
                        ),
                        max_width="400px",
                    ),
                ),
                width=HEADER_LEFT_WIDTH,
                min_width=HEADER_LEFT_WIDTH,
                padding="0.6rem 0.85rem",
                border_right=f"1px solid {rx.color('slate', 6)}",
                align="center",
                background=rx.color("slate", 2),
                align_self="stretch",
                style={
                    "position": "sticky",
                    "left": "0",
                    "zIndex": "15",
                    "boxShadow": "2px 0 5px rgba(0,0,0,0.06)",
                },
            ),

            # 右侧时间轴内容区：根据 is_expanded 动态切换 多行展开 或 单行折叠
            rx.box(
                rx.cond(
                    lane.is_expanded,
                    # 【展开多行模式】：每个节点独占一行，解决重叠问题；点击任意行空白处或底部新增行即可直接创建节点
                    rx.cond(
                        lane.nodes.length() > 0,
                        rx.vstack(
                            rx.foreach(lane.nodes, render_node_single_row),
                            # 底部快捷空白添加行
                            rx.box(
                                timeline_clickable_grid_bg(lane.lane_type, lane.product_id, lane.lane_title),
                                rx.hstack(
                                    rx.icon("circle_plus", size=12, color=rx.color("slate", 8)),
                                    rx.text("+ 点击时间格添加新阶段节点", size="1", color=rx.color("slate", 8)),
                                    spacing="1",
                                    align="center",
                                    padding_left="1rem",
                                    height="28px",
                                    pointer_events="none",
                                ),
                                position="relative",
                                width=GRID_WIDTH,
                                height="28px",
                                opacity="0.6",
                                _hover={"opacity": "1"},
                            ),
                            spacing="0",
                            width=GRID_WIDTH,
                        ),
                        # 无节点时显示 1 行空白可点击格
                        rx.box(
                            timeline_clickable_grid_bg(lane.lane_type, lane.product_id, lane.lane_title),
                            rx.center(
                                rx.text("+ 点击此处任意时间格添加首个节点", size="1", color=rx.color("slate", 8)),
                                width="100%",
                                height="38px",
                                pointer_events="none",
                            ),
                            position="relative",
                            width=GRID_WIDTH,
                            height="38px",
                        )
                    ),
                    # 【单行折叠模式】：节点全部按照实际具体日期像素精准放置，彻底杜绝推移冲突！
                    rx.box(
                        timeline_clickable_grid_bg(lane.lane_type, lane.product_id, lane.lane_title),
                        rx.box(
                            rx.foreach(
                                lane.nodes,
                                lambda n: node_gantt_bar(n, is_compact=True)
                            ),
                            position="relative",
                            width=GRID_WIDTH,
                            height="38px",
                        ),
                        position="relative",
                        width=GRID_WIDTH,
                        min_width=GRID_WIDTH,
                        min_height="38px",
                    )
                ),
                width=GRID_WIDTH,
                min_width=GRID_WIDTH,
            ),
            spacing="0",
            align="start",
            border_bottom=f"1px solid {rx.color('slate', 4)}",
            _hover={"background": rx.color("slate", 2)},
            width=TOTAL_WIDTH,
        )

    return rx.box(
        rx.box(
            rx.vstack(
                rx.box(
                    month_header,
                    sub_period_header,
                    id="timeline-header-area",
                    class_name="timeline-header-area",
                    title="💡 提示：在表头区域滚动鼠标滚轮可直接左右缩放时间轴，双击可重置为 100%",
                    width=TOTAL_WIDTH,
                ),
                rx.cond(
                    ScheduleState.lanes.length() > 0,
                    rx.vstack(
                        rx.foreach(ScheduleState.lanes, render_lane_row),
                        spacing="0",
                        width=TOTAL_WIDTH,
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("calendar_off", size=28, color=rx.color("slate", 7)),
                            rx.text("当前筛选条件下暂无排期项目", size="2", color=rx.color("slate", 9)),
                            rx.button("➕ 新增商品工期 / 日程", size="1", color_scheme="violet", on_click=ScheduleState.open_add_project_dialog),
                            spacing="2",
                            align="center",
                            padding="2.5rem 0",
                        ),
                        width="100%",
                    )
                ),
                spacing="0",
                width=TOTAL_WIDTH,
            ),
            id="timeline-scroll-container",
            style={
                "--timeline-slot-width": "100px",
                "--timeline-zoom": "1",
                "overflowX": "auto",
                "width": "100%",
                "scrollbarWidth": "auto",
            },
            class_name="timeline-scrollbar-container",
        ),
        border=f"1px solid {rx.color('slate', 5)}",
        border_radius="10px",
        overflow="hidden",
        background=rx.color("slate", 1),
        width="100%",
    )


def upcoming_milestones_banner() -> rx.Component:
    """近期关键节点与当月任务概览 (宽度扩大 1.2 倍为 280px，固定 76px 高度，内容靠上对齐，优先显示具体日期)"""
    return rx.cond(
        ScheduleState.upcoming_nodes.length() > 0,
        data_card(
            "📍 近期关键工期与活动提醒",
            rx.hstack(
                rx.foreach(
                    ScheduleState.upcoming_nodes,
                    lambda item: rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.badge(item.status_label, size="1", color_scheme="violet"),
                                rx.badge(item.display_date_range, size="1", variant="outline"),
                                spacing="1",
                                align="center",
                            ),
                            rx.text(item.display_title, size="1", weight="bold", line_clamp=1),
                            rx.cond(
                                item.remarks != "",
                                rx.text(item.remarks, size="1", color=rx.color("slate", 9), line_clamp=1),
                                rx.fragment()
                            ),
                            spacing="1",
                            align="start",
                            justify="start",
                            height="100%",
                            padding_top="2px",
                        ),
                        size="1",
                        variant="surface",
                        width="280px",
                        min_width="280px",
                        height="76px",
                        cursor="pointer",
                        on_click=ScheduleState.open_edit_dialog(item),
                    )
                ),
                spacing="3",
                overflow_x="auto",
                width="100%",
                padding_y="0.25rem",
            ),
        ),
        rx.fragment()
    )


def project_creation_dialog() -> rx.Component:
    """弹窗 1: 右上角【新增商品工期 / 日程】独立弹窗 (支持商品工期、展会活动与运营事务新增独立行)"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("folder_plus", size=18, color=rx.color("violet", 9)),
                    rx.text("➕ 新增商品工期 / 日程"),
                    spacing="2",
                    align="center",
                )
            ),
            rx.dialog.description("创建新的商品工期行、展会活动行或其他日程行。创建后可在时间轴上直接点击网格添加各个阶段节点。", size="1"),
            
            rx.vstack(
                # 1. 业务类型切换 (100% 满宽)
                custom_form_field(
                    "项目大类分类",
                    rx.segmented_control.root(
                        rx.segmented_control.item("👗 商品工期", value="product"),
                        rx.segmented_control.item("🎪 展会与活动", value="event"),
                        rx.segmented_control.item("📌 其他", value="other"),
                        value=ScheduleState.p_item_type,
                        on_change=ScheduleState.set_p_item_type,
                        size="2",
                        width="100%",
                    ),
                    width="100%",
                ),

                # 2. 如果是商品类型：从商品数据库下拉选择 (100% 满宽)
                rx.cond(
                    ScheduleState.is_p_product_type,
                    custom_form_field(
                        "选择要管理的商品 (从数据库拉取)",
                        rx.select.root(
                            rx.select.trigger(placeholder="请选择商品...", width="100%"),
                            rx.select.content(
                                rx.foreach(
                                    ScheduleState.product_options,
                                    lambda p: rx.select.item(p["name"], value=p["id"].to_string())
                                )
                            ),
                            value=ScheduleState.p_product_id.to_string(),
                            on_change=ScheduleState.set_p_product_id,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.fragment()
                ),

                # 3. 如果是展会与活动类型：输入展会/活动名称 (100% 满宽)
                rx.cond(
                    ScheduleState.is_p_event_type,
                    custom_form_field(
                        "展会 / 活动名称",
                        rx.input(
                            placeholder="如：WF 2026 冬 / COMICUP 30 / 广州IDO展...",
                            value=ScheduleState.p_title,
                            on_change=ScheduleState.set_p_title,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.fragment()
                ),

                # 4. 如果是其他类型：输入事项名称 (100% 满宽)
                rx.cond(
                    ScheduleState.is_p_other_type,
                    custom_form_field(
                        "事项 / 日程名称",
                        rx.input(
                            placeholder="如：年中大盘点 / 品牌升级企划 / 耗材盘库...",
                            value=ScheduleState.p_title,
                            on_change=ScheduleState.set_p_title,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.fragment()
                ),

                # 操作按钮
                rx.hstack(
                    rx.spacer(),
                    rx.dialog.close(
                        rx.button("取消", variant="soft", color_scheme="gray", on_click=ScheduleState.close_project_dialog)
                    ),
                    rx.button("确认添加", on_click=ScheduleState.submit_project_dialog, color_scheme="violet"),
                    spacing="3",
                    align="center",
                    width="100%",
                    margin_top="0.75rem",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="480px",
        ),
        open=ScheduleState.is_project_dialog_open,
    )


def node_modal_dialog() -> rx.Component:
    """弹窗 2: 单个工期阶段节点创建 / 编辑详情弹窗 (支持独立勾选不设置具体日期，4 下拉框 2x2 严格等宽对齐)"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("calendar_clock", size=18, color=rx.color("violet", 9)),
                    rx.text(rx.cond(ScheduleState.is_editing, "✏️ 编辑阶段节点详情", "➕ 添加阶段节点")),
                    spacing="2",
                    align="center",
                )
            ),
            rx.dialog.description(
                rx.hstack(
                    rx.text("当前所属项目:"),
                    rx.badge(ScheduleState.current_lane_title, size="1", color_scheme="violet", variant="soft"),
                    spacing="1",
                    align="center",
                ),
                size="1"
            ),
            
            rx.vstack(
                # 1. 如果是商品类型：选择阶段模板预设
                rx.cond(
                    ScheduleState.is_f_product_type,
                    rx.vstack(
                        custom_form_field(
                            "阶段模板预设",
                            rx.select.root(
                                rx.select.trigger(placeholder="选择阶段...", width="100%"),
                                rx.select.content(
                                    rx.foreach(
                                        ScheduleState.stage_presets,
                                        lambda st: rx.select.item(st, value=st)
                                    )
                                ),
                                value=ScheduleState.f_stage_name,
                                on_change=ScheduleState.set_f_stage_name,
                                size="2",
                                width="100%",
                            ),
                            width="100%",
                        ),
                        # 如果选择了【开售】，联动显示开售平台下拉选择
                        rx.cond(
                            ScheduleState.is_stage_on_sale,
                            custom_form_field(
                                "🛒 开售平台 (平台数据库动态联动)",
                                rx.select.root(
                                    rx.select.trigger(placeholder="选择开售平台...", width="100%"),
                                    rx.select.content(
                                        rx.foreach(
                                            ScheduleState.platform_options,
                                            lambda pl: rx.select.item(pl, value=pl)
                                        )
                                    ),
                                    value=ScheduleState.f_platform_name,
                                    on_change=ScheduleState.set_f_platform_name,
                                    size="2",
                                    width="100%",
                                ),
                                width="100%",
                            ),
                            rx.fragment()
                        ),
                        # 如果选择了【其他】，显示自定义阶段文本输入
                        rx.cond(
                            ScheduleState.is_stage_other,
                            custom_form_field(
                                "✏️ 自定义阶段名称",
                                rx.input(
                                    placeholder="如：面料二造、配件定制...",
                                    value=ScheduleState.f_custom_stage,
                                    on_change=ScheduleState.set_f_custom_stage,
                                    size="2",
                                    width="100%",
                                ),
                                width="100%",
                            ),
                            rx.fragment()
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    # 非商品类型 (活动/其他): 自定义阶段/子事项
                    custom_form_field(
                        "阶段事项说明",
                        rx.input(
                            placeholder="如：展会布景 / 现货特惠 / 物料清点...",
                            value=ScheduleState.f_custom_stage,
                            on_change=ScheduleState.set_f_custom_stage,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    )
                ),

                # 2. 具体起止日期选择与独立勾选「不设置具体日期」
                rx.grid(
                    rx.vstack(
                        custom_form_field(
                            "📅 开始日期 (具体日期)",
                            rx.input(
                                type="date",
                                value=ScheduleState.f_start_date,
                                on_change=ScheduleState.set_f_start_date,
                                disabled=ScheduleState.f_no_start_date,
                                size="2",
                                width="100%",
                            ),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.checkbox(
                                checked=ScheduleState.f_no_start_date,
                                on_change=ScheduleState.set_f_no_start_date,
                                size="1",
                            ),
                            rx.text("不设置具体开始日期（仅按旬度）", size="1", color=rx.color("slate", 9)),
                            spacing="2",
                            align="center",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        custom_form_field(
                            "🏁 结束日期 (具体日期)",
                            rx.input(
                                type="date",
                                value=ScheduleState.f_end_date,
                                on_change=ScheduleState.set_f_end_date,
                                disabled=ScheduleState.f_no_end_date,
                                size="2",
                                width="100%",
                            ),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.checkbox(
                                checked=ScheduleState.f_no_end_date,
                                on_change=ScheduleState.set_f_no_end_date,
                                size="1",
                            ),
                            rx.text("不设置具体结束日期（仅按旬度）", size="1", color=rx.color("slate", 9)),
                            spacing="2",
                            align="center",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),

                # 3. 时间轴起始与结束旬度 (左列 2 个下拉框平分 50%/50%，右列 2 个下拉框平分 50%/50%，与上下行严格等宽对齐)
                rx.grid(
                    custom_form_field(
                        "🚀 起始旬度 (联动)",
                        rx.grid(
                            rx.select.root(
                                rx.select.trigger(width="100%"),
                                rx.select.content(
                                    rx.foreach(ScheduleState.months_list, lambda m: rx.select.item(f"{m}月", value=m.to_string()))
                                ),
                                value=ScheduleState.f_start_month.to_string(),
                                on_change=ScheduleState.set_f_start_month,
                                size="2",
                                width="100%",
                            ),
                            rx.select.root(
                                rx.select.trigger(width="100%"),
                                rx.select.content(
                                    rx.select.item("上旬", value="early"),
                                    rx.select.item("中旬", value="mid"),
                                    rx.select.item("下旬", value="late"),
                                ),
                                value=ScheduleState.f_start_period,
                                on_change=ScheduleState.set_f_start_period,
                                size="2",
                                width="100%",
                            ),
                            columns="2",
                            spacing="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    custom_form_field(
                        "🏁 结束旬度 (联动)",
                        rx.grid(
                            rx.select.root(
                                rx.select.trigger(width="100%"),
                                rx.select.content(
                                    rx.foreach(ScheduleState.months_list, lambda m: rx.select.item(f"{m}月", value=m.to_string()))
                                ),
                                value=ScheduleState.f_end_month.to_string(),
                                on_change=ScheduleState.set_f_end_month,
                                size="2",
                                width="100%",
                            ),
                            rx.select.root(
                                rx.select.trigger(width="100%"),
                                rx.select.content(
                                    rx.select.item("上旬", value="early"),
                                    rx.select.item("中旬", value="mid"),
                                    rx.select.item("下旬", value="late"),
                                ),
                                value=ScheduleState.f_end_period,
                                on_change=ScheduleState.set_f_end_period,
                                size="2",
                                width="100%",
                            ),
                            columns="2",
                            spacing="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),

                # 4. 状态与主题色 (左右两列对齐)
                rx.grid(
                    custom_form_field(
                        "当前执行状态",
                        rx.select.root(
                            rx.select.trigger(width="100%"),
                            rx.select.content(
                                rx.foreach(
                                    ScheduleState.status_choices,
                                    lambda st: rx.select.item(st[1], value=st[0])
                                )
                            ),
                            value=ScheduleState.f_status,
                            on_change=ScheduleState.set_f_status,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    custom_form_field(
                        "标签主题色",
                        rx.select.root(
                            rx.select.trigger(width="100%"),
                            rx.select.content(
                                rx.foreach(
                                    ScheduleState.color_choices,
                                    lambda co: rx.select.item(co[1], value=co[0])
                                )
                            ),
                            value=ScheduleState.f_color,
                            on_change=ScheduleState.set_f_color,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),

                # 5. 详细备注说明 (100% 满宽占满窗口)
                custom_form_field(
                    "说明备注 / 待办清单",
                    rx.text_area(
                        placeholder="记录具体的工艺要求、展位号、预算或关键提醒事项...",
                        value=ScheduleState.f_remarks,
                        on_change=ScheduleState.set_f_remarks,
                        size="2",
                        min_height="75px",
                        width="100%",
                    ),
                    width="100%",
                ),

                # 6. 操作按钮
                rx.hstack(
                    rx.cond(
                        ScheduleState.is_editing,
                        rx.button("🗑️ 删除节点", variant="soft", color_scheme="red", on_click=ScheduleState.delete_node(ScheduleState.f_node_id)),
                        rx.fragment()
                    ),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.button("取消", variant="soft", color_scheme="gray", on_click=ScheduleState.close_node_dialog)
                    ),
                    rx.button("确认保存", on_click=ScheduleState.submit_node_dialog, color_scheme="violet"),
                    spacing="3",
                    align="center",
                    width="100%",
                    margin_top="0.75rem",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="560px",
        ),
        open=ScheduleState.is_node_dialog_open,
    )


def timeline_zoom_script() -> rx.Component:
    """引入时间轴鼠标滚轮左右平滑定点缩放及交互脚本"""
    return rx.script(src="/timeline_zoom.js")



def schedule_page() -> rx.Component:
    """工期日程管理主页面入口"""
    return page_layout(
        rx.vstack(
            # 1. 顶部指标看板
            rx.grid(
                metric_card("工期日程总数", ScheduleState.total_count.to_string(), "calendar", "gray"),
                metric_card("正在进行中", ScheduleState.in_progress_count.to_string(), "zap", "amber", "进行中"),
                metric_card("已达成完结", ScheduleState.completed_count.to_string(), "badge_check", "green", "已完成"),
                metric_card("当前所处旬度", ScheduleState.current_period_display, "pin", "pink", "实时时间"),
                columns="4",
                spacing="3",
                width="100%",
            ),

            # 2. 近期关键节点看板 (280px 宽度，固定 76px 高度)
            upcoming_milestones_banner(),

            # 3. 过滤控制、缩放调节与动作栏
            rx.card(
                rx.hstack(
                    # 年份切换
                    rx.hstack(
                        rx.text("年份:", size="1", color=rx.color("slate", 9), weight="medium"),
                        rx.select.root(
                            rx.select.trigger(),
                            rx.select.content(
                                rx.foreach(ScheduleState.year_options, lambda y: rx.select.item(f"{y} 年", value=y.to_string()))
                            ),
                            value=ScheduleState.selected_year.to_string(),
                            on_change=ScheduleState.set_selected_year,
                            size="1",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.divider(orientation="vertical", size="2"),
                    # 分类切换 (全部类型)
                    rx.segmented_control.root(
                        rx.segmented_control.item("全部类型", value="all"),
                        rx.segmented_control.item("👗 商品工期", value="product"),
                        rx.segmented_control.item("🎪 展会与活动", value="event"),
                        rx.segmented_control.item("📌 其他", value="other"),
                        value=ScheduleState.filter_type,
                        on_change=ScheduleState.set_filter_type,
                        size="1",
                    ),
                    rx.divider(orientation="vertical", size="2"),
                    # 缩放调节控制组
                    rx.hstack(
                        rx.text("缩放:", size="1", color=rx.color("slate", 9), weight="medium"),
                        rx.tooltip(
                            rx.icon_button(
                                rx.icon("zoom_out", size=13),
                                size="1",
                                variant="surface",
                                color_scheme="gray",
                                on_click=ScheduleState.zoom_out,
                                title="缩小时间轴",
                            ),
                            content="缩小时间轴 (Ctrl + 滚轮向下)",
                        ),
                        rx.tooltip(
                            rx.badge(
                                "100%",
                                id="timeline-zoom-text",
                                size="1",
                                color_scheme="violet",
                                variant="surface",
                                cursor="pointer",
                                on_click=ScheduleState.zoom_reset,
                            ),
                            content="当前缩放比例 (点击重置为 100%)",
                        ),
                        rx.tooltip(
                            rx.icon_button(
                                rx.icon("zoom_in", size=13),
                                size="1",
                                variant="surface",
                                color_scheme="gray",
                                on_click=ScheduleState.zoom_in,
                                title="放大时间轴",
                            ),
                            content="放大时间轴 (Ctrl + 滚轮向上)",
                        ),
                        rx.segmented_control.root(
                            rx.segmented_control.item("50%", value="50"),
                            rx.segmented_control.item("100%", value="100"),
                            rx.segmented_control.item("150%", value="150"),
                            rx.segmented_control.item("200%", value="200"),
                            value=ScheduleState.zoom_preset_value,
                            on_change=ScheduleState.set_zoom_preset,
                            size="1",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.spacer(),
                    # 提示信息
                    rx.text("💡 提示：按住 Ctrl/Alt + 滚轮 或在表头区域滚动即可平滑缩放；Shift + 滚轮横向平移", size="1", color=rx.color("slate", 9)),
                    # 右上角新增商品工期/日程按钮
                    rx.button(
                        rx.icon("folder_plus", size=14),
                        "新增商品工期 / 日程",
                        on_click=ScheduleState.open_add_project_dialog,
                        size="2",
                        color_scheme="violet",
                    ),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                variant="surface",
                size="1",
                width="100%",
            ),

            # 4. 36 旬甘特图时间轴矩阵 (左侧列 position: sticky 绝对固定，支持鼠标滚轮平滑定点缩放)
            timeline_gantt_matrix(),

            # 5. 弹窗 1: 业务项目/活动创建弹窗 (满宽美化)
            project_creation_dialog(),

            # 6. 弹窗 2: 单个节点详情与创建/编辑弹窗 (满宽美化，支持独立勾选不设置具体日期)
            node_modal_dialog(),

            # 7. 客户端缩放脚本注入
            timeline_zoom_script(),

            spacing="4",
            width="100%",
        )
    )
