# yurara_app/state/schedule_state.py
"""
工期日程管理 State 层。
负责 36 旬甘特图矩阵数据生成、具体日期像素按天数精确分割定位、项目与节点分层管理、多行展开/折叠、左右微调箭头平移、独立勾选不设置具体起止日期、时间轴默认自动居左滚动到当前月份。
"""
from datetime import datetime, date
import calendar
from typing import Optional
from pydantic import BaseModel
import reflex as rx
from .app_state import AppState
from services.schedule_service import (
    ScheduleService,
    period_to_index,
    index_to_period,
    date_to_period,
    period_default_date,
    date_to_pixel_offset,
    format_period_range,
    get_current_period,
    PERIOD_MAP,
    PERIOD_LABELS
)


STAGE_PRESETS = [
    "企划设计",
    "样衣打版",
    "产前样衣",
    "大货投产",
    "预售开启",
    "预售结束",
    "大货出货",
    "质检入库",
    "开售",
    "其他"
]

COLOR_OPTIONS = [
    ("violet", "💜 紫色"),
    ("blue", "💙 蓝色"),
    ("cyan", "🩵 青色"),
    ("green", "💚 绿色"),
    ("amber", "💛 琥珀"),
    ("orange", "🧡 橙色"),
    ("ruby", "❤️ 红色")
]

STATUS_CHOICES = [
    ("planned", "🕒 计划中"),
    ("in_progress", "⚡ 进行中"),
    ("completed", "✅ 已完成"),
    ("delayed", "⚠️ 延期预警")
]

YEAR_OPTIONS = [2024, 2025, 2026, 2027, 2028]


class ScheduleNodeItem(BaseModel):
    id: int = 0
    item_type: str = "product"  # 'product', 'event', 'other'
    product_id: int = 0
    product_name: str = ""
    platform_name: str = ""
    title: str = ""
    stage_name: str = ""
    custom_stage: str = ""
    display_title: str = ""
    
    # 具体日期
    start_date: str = ""
    end_date: str = ""
    
    # 旬度定位
    start_year: int = 2026
    start_month: int = 1
    start_period: str = "early"
    end_year: int = 2026
    end_month: int = 1
    end_period: str = "early"
    range_str: str = ""
    display_date_range: str = ""  # 提醒看板展示专用：优先显示具体日期，无具体日期时显示旬度
    
    status: str = "planned"
    status_label: str = "🕒 计划中"
    color: str = "violet"
    remarks: str = ""
    
    # 基于具体日期的像素绝对定位属性 (针对当前 selected_year 计算，全年 0-3600px，按天数精确分割)
    left_px: float = 0.0
    width_px: float = 100.0
    is_visible_in_year: bool = True


class ScheduleLaneItem(BaseModel):
    lane_id: str = ""
    lane_type: str = "product"  # 'product', 'event', 'other'
    product_id: int = 0
    lane_title: str = ""
    badge_label: str = ""
    nodes: list[ScheduleNodeItem] = []
    is_expanded: bool = True
    node_count: int = 0
    node_count_str: str = ""


class ScheduleState(AppState):
    # ===================== 状态变量 =====================
    selected_year: int = 2026
    filter_type: str = "all"  # 'all', 'product', 'event', 'other'
    filter_product_id: int = 0
    
    # 展开/折叠状态记录 (默认全部展开)
    expanded_lanes: list[str] = []
    has_custom_expand: bool = False
    
    # 用户手动添加的项目列表记录
    custom_active_lanes: list[str] = []
    
    # 当前系统时间旬度
    curr_year: int = 2026
    curr_month: int = 8
    curr_period: str = "late"
    curr_col_index: int = 24  # 1-36
    
    # 页面渲染数据
    has_initial_scrolled: bool = False
    nodes_raw: list[ScheduleNodeItem] = []
    lanes: list[ScheduleLaneItem] = []
    upcoming_nodes: list[ScheduleNodeItem] = []
    
    # 统计数据
    total_count: int = 0
    in_progress_count: int = 0
    completed_count: int = 0
    delayed_count: int = 0
    
    # 下拉选项
    product_options: list[dict] = []  # [{"id": 1, "name": "xxx"}]
    platform_options: list[str] = ["微店", "Booth", "线下展会", "淘宝", "小红书"]
    
    # ===================== 弹窗 1: 右上角新增业务项目/活动 =====================
    is_project_dialog_open: bool = False
    p_item_type: str = "product"  # 'product', 'event', 'other'
    p_product_id: int = 0
    p_title: str = ""
    p_remarks: str = ""

    # ===================== 弹窗 2: 单个节点详情与创建/编辑 =====================
    is_node_dialog_open: bool = False
    is_editing: bool = False
    f_node_id: int = 0
    current_lane_title: str = ""
    
    f_item_type: str = "product"  # 'product', 'event', 'other'
    f_product_id: int = 0
    f_product_name: str = ""
    f_platform_name: str = "微店"
    f_stage_name: str = "企划设计"
    f_custom_stage: str = ""
    f_title: str = ""
    
    # 具体日期与「不设置具体日期」勾选状态 (可独立勾选)
    f_start_date: str = ""
    f_end_date: str = ""
    f_no_start_date: bool = False
    f_no_end_date: bool = False
    
    # 旬度字段
    f_start_year: int = 2026
    f_start_month: int = 1
    f_start_period: str = "early"
    f_end_year: int = 2026
    f_end_month: int = 1
    f_end_period: str = "early"
    
    f_status: str = "planned"
    f_color: str = "violet"
    f_remarks: str = ""

    # ===================== 计算属性 (Computed Vars) =====================

    @rx.var
    def is_p_product_type(self) -> bool:
        return self.p_item_type == "product"

    @rx.var
    def is_p_event_type(self) -> bool:
        return self.p_item_type == "event"

    @rx.var
    def is_p_other_type(self) -> bool:
        return self.p_item_type == "other"

    @rx.var
    def is_f_product_type(self) -> bool:
        return self.f_item_type == "product"

    @rx.var
    def is_stage_on_sale(self) -> bool:
        return self.f_stage_name == "开售"

    @rx.var
    def is_stage_other(self) -> bool:
        return self.f_stage_name == "其他"

    @rx.var
    def stage_presets(self) -> list[str]:
        return STAGE_PRESETS

    @rx.var
    def color_choices(self) -> list[tuple[str, str]]:
        return COLOR_OPTIONS

    @rx.var
    def status_choices(self) -> list[tuple[str, str]]:
        return STATUS_CHOICES

    @rx.var
    def year_options(self) -> list[int]:
        return YEAR_OPTIONS

    @rx.var
    def current_period_display(self) -> str:
        p_name = PERIOD_LABELS.get(self.curr_period, "下旬")
        return f"{self.curr_year} 年 {self.curr_month} 月 {p_name}"

    @rx.var
    def months_list(self) -> list[int]:
        return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    # ===================== 核心加载逻辑 =====================

    @rx.event
    async def load_schedule_data(self):
        """从数据库全量拉取工期与活动数据并生成 36 旬网格与泳道"""
        if not await self.is_authenticated_user():
            return

        # 更新今天所属时间
        c_y, c_m, c_p = get_current_period()
        self.curr_year, self.curr_month, self.curr_period = c_y, c_m, c_p
        
        # 计算当前选中年份中高亮线所在的列 (1-36)
        if self.selected_year == c_y:
            self.curr_col_index = (c_m - 1) * 3 + PERIOD_MAP.get(c_p, 0) + 1
        else:
            self.curr_col_index = 0

        db = self.get_db()
        try:
            service = ScheduleService(db)
            
            # 1. 加载商品选项
            prods = service.get_all_products()
            self.product_options = [{"id": p.id, "name": p.name} for p in prods]
            if prods and not self.p_product_id:
                self.p_product_id = prods[0].id
            if prods and not self.f_product_id:
                self.f_product_id = prods[0].id
                self.f_product_name = prods[0].name

            # 2. 加载平台选项
            plats = service.get_all_platforms()
            if plats:
                self.platform_options = [p.name for p in plats]

            # 3. 加载节点
            raw_nodes = service.get_nodes(year=self.selected_year, item_type=self.filter_type)
            
            node_items = []
            status_map = dict(STATUS_CHOICES)
            
            total = 0
            in_prog = 0
            comp = 0
            delay = 0
            
            for n in raw_nodes:
                total += 1
                if n.status == "in_progress": in_prog += 1
                elif n.status == "completed": comp += 1
                elif n.status == "delayed": delay += 1
                
                # 计算展示标题
                p_name = n.product.name if n.product else ""
                if n.item_type == "product":
                    if n.stage_name == "开售":
                        stage_disp = f"开售 ({n.platform_name or '全部平台'})"
                    elif n.stage_name == "其他":
                        stage_disp = n.custom_stage or "其他"
                    else:
                        stage_disp = n.stage_name or "工期"
                    display_title = f"{n.title or p_name} - {stage_disp}"
                else:
                    display_title = n.title

                # 计算在当前 selected_year (0 - 3600px) 中的具体日期像素位置与宽度
                # 解析开始日
                if n.start_date:
                    try:
                        s_dt = datetime.strptime(n.start_date, "%Y-%m-%d")
                        s_y, s_m, s_d = s_dt.year, s_dt.month, s_dt.day
                    except Exception:
                        s_y, s_m, s_d = n.start_year, n.start_month, 1
                else:
                    s_y, s_m = n.start_year, n.start_month
                    s_d = 1 if n.start_period == "early" else (11 if n.start_period == "mid" else 21)

                # 解析结束日
                if n.end_date:
                    try:
                        e_dt = datetime.strptime(n.end_date, "%Y-%m-%d")
                        e_y, e_m, e_d = e_dt.year, e_dt.month, e_dt.day
                    except Exception:
                        e_y, e_m, e_d = n.end_year, n.end_month, 28
                else:
                    e_y, e_m = n.end_year, n.end_month
                    days_in_m = calendar.monthrange(e_y, e_m)[1]
                    e_d = 10 if n.end_period == "early" else (20 if n.end_period == "mid" else days_in_m)

                # 计算在当前 selected_year 的起止像素
                if s_y < self.selected_year:
                    start_x = 0.0
                elif s_y == self.selected_year:
                    start_x = date_to_pixel_offset(s_y, s_m, s_d, is_end=False)
                else:
                    start_x = 3600.0

                if e_y > self.selected_year:
                    end_x = 3600.0
                elif e_y == self.selected_year:
                    end_x = date_to_pixel_offset(e_y, e_m, e_d, is_end=True)
                else:
                    end_x = 0.0

                # 裁剪并计算可见性
                is_vis = not (e_y < self.selected_year or s_y > self.selected_year or end_x <= start_x)
                if is_vis:
                    left_px = round(max(0.0, min(3600.0, start_x)), 1)
                    right_px = round(max(0.0, min(3600.0, end_x)), 1)
                    width_px = round(max(52.0, right_px - left_px), 1)
                else:
                    left_px = 0.0
                    width_px = 52.0

                range_txt = format_period_range(
                    n.start_year, n.start_month, n.start_period,
                    n.end_year, n.end_month, n.end_period,
                    n.start_date or "", n.end_date or ""
                )

                # 优先显示具体日期，若无具体日期则显示旬度
                s_lbl = PERIOD_LABELS.get(n.start_period, "上旬")
                e_lbl = PERIOD_LABELS.get(n.end_period, "上旬")
                if n.start_date and n.end_date:
                    date_badge = f"📅 {n.start_date}" if n.start_date == n.end_date else f"📅 {n.start_date} ~ {n.end_date}"
                elif n.start_date:
                    date_badge = f"📅 {n.start_date} ~ {n.end_month}月{e_lbl}"
                elif n.end_date:
                    date_badge = f"📅 {n.start_month}月{s_lbl} ~ {n.end_date}"
                else:
                    date_badge = f"🗓️ {n.start_month}月{s_lbl} ~ {n.end_month}月{e_lbl}"

                node_items.append(ScheduleNodeItem(
                    id=n.id,
                    item_type=n.item_type,
                    product_id=n.product_id or 0,
                    product_name=p_name,
                    platform_name=n.platform_name or "",
                    title=n.title,
                    stage_name=n.stage_name or "",
                    custom_stage=n.custom_stage or "",
                    display_title=display_title,
                    start_date=n.start_date or "",
                    end_date=n.end_date or "",
                    start_year=n.start_year,
                    start_month=n.start_month,
                    start_period=n.start_period,
                    end_year=n.end_year,
                    end_month=n.end_month,
                    end_period=n.end_period,
                    range_str=range_txt,
                    display_date_range=date_badge,
                    status=n.status,
                    status_label=status_map.get(n.status, "计划中"),
                    color=n.color or "violet",
                    remarks=n.remarks or "",
                    left_px=left_px,
                    width_px=width_px,
                    is_visible_in_year=is_vis
                ))

            self.nodes_raw = node_items
            self.total_count = total
            self.in_progress_count = in_prog
            self.completed_count = comp
            self.delayed_count = delay

            # 4. 生成泳道 Lanes (按商品分组、展会活动、其他事务)
            lanes_list = []
            
            # 4.1 商品泳道：为每个有节点的商品（或全部商品）建立独立行
            prod_node_map = {}
            for ni in node_items:
                if ni.item_type == "product":
                    p_key = ni.product_id or 0
                    if p_key not in prod_node_map:
                        prod_node_map[p_key] = []
                    prod_node_map[p_key].append(ni)

            for p_dict in self.product_options:
                p_id = p_dict["id"]
                p_name = p_dict["name"]
                lane_id = f"prod_{p_id}"
                p_nodes = prod_node_map.get(p_id, [])
                
                # 判断展开状态
                if not self.has_custom_expand:
                    is_exp = True
                else:
                    is_exp = lane_id in self.expanded_lanes

                if p_id in prod_node_map or lane_id in self.custom_active_lanes:
                    lanes_list.append(ScheduleLaneItem(
                        lane_id=lane_id,
                        lane_type="product",
                        product_id=p_id,
                        lane_title=f"👗 {p_name}",
                        badge_label="商品工期",
                        nodes=p_nodes,
                        is_expanded=is_exp,
                        node_count=len(p_nodes),
                        node_count_str=f"{len(p_nodes)} 个节点"
                    ))

            # 4.2 展会与活动泳道 (仅展示有节点或显式添加的活动行，支持完全删除)
            event_node_map = {}
            for ni in node_items:
                if ni.item_type == "event":
                    t_key = ni.title.strip() if ni.title else "展会与活动"
                    if t_key not in event_node_map:
                        event_node_map[t_key] = []
                    event_node_map[t_key].append(ni)

            all_event_titles = list(event_node_map.keys())
            for lid in self.custom_active_lanes:
                if lid.startswith("event_"):
                    t_name = lid[len("event_"):]
                    if t_name not in all_event_titles:
                        all_event_titles.append(t_name)

            if self.filter_type in ["all", "event"]:
                for t_name in all_event_titles:
                    lane_id = f"event_{t_name}"
                    e_nodes = event_node_map.get(t_name, [])
                    is_exp = True if not self.has_custom_expand else (lane_id in self.expanded_lanes)
                    lanes_list.append(ScheduleLaneItem(
                        lane_id=lane_id,
                        lane_type="event",
                        product_id=0,
                        lane_title=f"🎪 {t_name}",
                        badge_label="展会活动",
                        nodes=e_nodes,
                        is_expanded=is_exp,
                        node_count=len(e_nodes),
                        node_count_str=f"{len(e_nodes)} 个活动"
                    ))

            # 4.3 其他事务泳道 (仅展示有节点或显式添加的事项行，支持完全删除)
            other_node_map = {}
            for ni in node_items:
                if ni.item_type == "other":
                    t_key = ni.title.strip() if (ni.title and ni.title != "运营与综合事务") else "其他"
                    if t_key not in other_node_map:
                        other_node_map[t_key] = []
                    other_node_map[t_key].append(ni)

            all_other_titles = list(other_node_map.keys())
            for lid in self.custom_active_lanes:
                if lid.startswith("other_"):
                    t_name = lid[len("other_"):]
                    if t_name not in all_other_titles:
                        all_other_titles.append(t_name)

            if self.filter_type in ["all", "other"]:
                for t_name in all_other_titles:
                    lane_id = f"other_{t_name}"
                    o_nodes = other_node_map.get(t_name, [])
                    is_exp = True if not self.has_custom_expand else (lane_id in self.expanded_lanes)
                    lanes_list.append(ScheduleLaneItem(
                        lane_id=lane_id,
                        lane_type="other",
                        product_id=0,
                        lane_title=f"📌 {t_name}",
                        badge_label="其他日程",
                        nodes=o_nodes,
                        is_expanded=is_exp,
                        node_count=len(o_nodes),
                        node_count_str=f"{len(o_nodes)} 个事务"
                    ))

            self.lanes = lanes_list

            # 5. 提取近期节点
            curr_global_idx = period_to_index(c_y, c_m, c_p)
            upcoming = []
            for ni in node_items:
                n_s_idx = period_to_index(ni.start_year, ni.start_month, ni.start_period)
                n_e_idx = period_to_index(ni.end_year, ni.end_month, ni.end_period)
                if n_e_idx >= curr_global_idx and n_s_idx <= curr_global_idx + 4:
                    upcoming.append(ni)
            self.upcoming_nodes = upcoming[:6]

        except Exception as e:
            print(f"Error loading schedule data: {e}")
        finally:
            db.close()

    @rx.event
    def on_page_load(self):
        """页面每次加载/进入时调用：拉取数据并自动平滑居左滚动到当前月份"""
        c_y, c_m, c_p = get_current_period()
        self.curr_year, self.curr_month, self.curr_period = c_y, c_m, c_p
        target_left = max(0, (c_m - 1) * 300)
        yield ScheduleState.load_schedule_data()
        yield rx.call_script(
            f"""
            function scrollGanttTimeline() {{
                const el = document.getElementById('timeline-scroll-container');
                if (el) {{
                    el.scrollTo({{ left: {target_left}, behavior: 'smooth' }});
                }}
            }}
            setTimeout(scrollGanttTimeline, 150);
            setTimeout(scrollGanttTimeline, 400);
            """
        )

    # ===================== 交互与控制事件 =====================

    @rx.event
    def toggle_lane_expand(self, lane_id: str):
        """展开/折叠指定泳道"""
        self.has_custom_expand = True
        if lane_id in self.expanded_lanes:
            self.expanded_lanes = [lid for lid in self.expanded_lanes if lid != lane_id]
        else:
            if not self.expanded_lanes:
                self.expanded_lanes = [l.lane_id for l in self.lanes if l.lane_id != lane_id]
            else:
                self.expanded_lanes.append(lane_id)
        
        new_lanes = []
        for l in self.lanes:
            l_copy = l.copy()
            l_copy.is_expanded = l.lane_id in self.expanded_lanes
            new_lanes.append(l_copy)
        self.lanes = new_lanes

    @rx.event
    def toggle_all_lanes_expand(self):
        """一键全部展开/折叠"""
        self.has_custom_expand = True
        all_lane_ids = [l.lane_id for l in self.lanes]
        if len(self.expanded_lanes) >= len(all_lane_ids):
            self.expanded_lanes = []
        else:
            self.expanded_lanes = all_lane_ids

        new_lanes = []
        for l in self.lanes:
            l_copy = l.copy()
            l_copy.is_expanded = l.lane_id in self.expanded_lanes
            new_lanes.append(l_copy)
        self.lanes = new_lanes

    @rx.event
    def set_selected_year(self, val: str):
        try:
            self.selected_year = int(val)
            yield ScheduleState.load_schedule_data()
        except ValueError:
            pass

    @rx.event
    def set_filter_type(self, val: str | list[str]):
        if isinstance(val, list):
            self.filter_type = val[0] if val else "all"
        else:
            self.filter_type = str(val)
        yield ScheduleState.load_schedule_data()

    @rx.event
    def shift_node(self, node_id: int, delta: int):
        """前后微调平移 1 旬并即时刷新数据"""
        db = self.get_db()
        try:
            service = ScheduleService(db)
            service.shift_node(int(node_id), int(delta))
            yield rx.toast("工期节点已微调平移！")
            yield ScheduleState.load_schedule_data()
        except Exception as e:
            yield rx.toast(f"位移失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_node(self, node_id: int):
        """删除单个节点"""
        db = self.get_db()
        try:
            service = ScheduleService(db)
            service.delete_node(int(node_id))
            self.is_node_dialog_open = False
            yield rx.toast("工期阶段节点已删除！")
            yield ScheduleState.load_schedule_data()
        except Exception as e:
            yield rx.toast(f"删除失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_lane(self, lane_id: str, lane_type: str, product_id: int, lane_title: str):
        """删除整条泳道/项目行及其下的所有节点"""
        db = self.get_db()
        try:
            service = ScheduleService(db)
            count = service.delete_lane_nodes(lane_type, product_id, lane_title)
            self.custom_active_lanes = [lid for lid in self.custom_active_lanes if lid != lane_id]
            self.expanded_lanes = [lid for lid in self.expanded_lanes if lid != lane_id]
            yield rx.toast(f"已删除「{lane_title}」项目行（清理了 {count} 个节点）！")
            yield ScheduleState.load_schedule_data()
        except Exception as e:
            yield rx.toast(f"删除失败: {e}", level="error")
        finally:
            db.close()

    # ===================== 弹窗 1: 新增商品工期 / 日程 =====================

    @rx.event
    def open_add_project_dialog(self):
        """右上角点击：打开新增商品工期/日程弹窗"""
        self.p_item_type = "product"
        if self.product_options:
            self.p_product_id = self.product_options[0]["id"]
        self.p_title = ""
        self.is_project_dialog_open = True

    @rx.event
    def close_project_dialog(self):
        self.is_project_dialog_open = False

    @rx.event
    def set_p_item_type(self, val: str | list[str]):
        if isinstance(val, list):
            self.p_item_type = val[0] if val else "product"
        else:
            self.p_item_type = str(val)

    @rx.event
    def set_p_product_id(self, val: str):
        try:
            self.p_product_id = int(val)
        except ValueError:
            pass

    @rx.event
    def set_p_title(self, val: str):
        self.p_title = val

    @rx.event
    def submit_project_dialog(self):
        """保存添加商品工期 / 展会活动 / 运营事务新行"""
        if self.p_item_type == "product":
            if not self.p_product_id:
                if self.product_options:
                    self.p_product_id = self.product_options[0]["id"]
                else:
                    return rx.toast("暂无可用商品，请先在商品管理中创建商品！", level="error")

            lane_id = f"prod_{self.p_product_id}"
            if lane_id not in self.custom_active_lanes:
                self.custom_active_lanes.append(lane_id)
            if lane_id not in self.expanded_lanes:
                self.expanded_lanes.append(lane_id)
            self.is_project_dialog_open = False
            yield rx.toast("已添加商品工期行，可在时间轴上点击网格添加阶段节点！")
            yield ScheduleState.load_schedule_data()
        elif self.p_item_type == "event":
            title = self.p_title.strip()
            if not title:
                return rx.toast("请输入展会或活动名称！", level="error")
            lane_id = f"event_{title}"
            if lane_id not in self.custom_active_lanes:
                self.custom_active_lanes.append(lane_id)
            if lane_id not in self.expanded_lanes:
                self.expanded_lanes.append(lane_id)
            self.is_project_dialog_open = False
            yield rx.toast(f"已创建展会活动「{title}」新行，可在时间轴上点击网格添加节点！")
            yield ScheduleState.load_schedule_data()
        elif self.p_item_type == "other":
            title = self.p_title.strip() or "其他"
            lane_id = f"other_{title}"
            if lane_id not in self.custom_active_lanes:
                self.custom_active_lanes.append(lane_id)
            if lane_id not in self.expanded_lanes:
                self.expanded_lanes.append(lane_id)
            self.is_project_dialog_open = False
            yield rx.toast(f"已创建「{title}」新行，可在时间轴上点击网格添加节点！")
            yield ScheduleState.load_schedule_data()

    # ===================== 弹窗 2: 单个阶段节点添加与编辑 =====================

    @rx.event
    def open_add_dialog_for_slot(self, lane_type: str, product_id: int, col_index: int, lane_title: str = ""):
        """🎯 点击时间轴任意时间格时调出节点弹窗，并自动预填该时间点与商品"""
        self.is_editing = False
        self.f_node_id = 0
        self.f_item_type = lane_type
        self.f_product_id = product_id or 0
        self.current_lane_title = lane_title or ("商品工期" if lane_type == "product" else ("展会活动" if lane_type == "event" else "其他日程"))
        
        # 解析所点击的网格列 (1-36)
        month = ((col_index - 1) // 3) + 1
        period_arr = ["early", "mid", "late"]
        period = period_arr[(col_index - 1) % 3]
        year = self.selected_year
        def_date = period_default_date(year, month, period, False)
        
        self.f_start_date = def_date
        self.f_end_date = def_date
        self.f_no_start_date = False
        self.f_no_end_date = False
        
        self.f_start_year = year
        self.f_start_month = month
        self.f_start_period = period
        self.f_end_year = year
        self.f_end_month = month
        self.f_end_period = period

        if product_id and product_id > 0:
            matched_p = next((p for p in self.product_options if p["id"] == product_id), None)
            self.f_product_name = matched_p["name"] if matched_p else ""
        else:
            self.f_product_name = ""

        self.f_stage_name = "企划设计" if lane_type == "product" else "展会"
        self.f_custom_stage = ""
        self.f_platform_name = self.platform_options[0] if self.platform_options else "微店"
        self.f_title = self.f_product_name if lane_type == "product" else (lane_title.replace("🎪 ", "").replace("📌 ", ""))
        self.f_status = "planned"
        self.f_color = "violet"
        self.f_remarks = ""
        self.is_node_dialog_open = True

    @rx.event
    def open_edit_dialog(self, node: dict):
        """打开编辑节点对话框并回填数据"""
        self.is_editing = True
        self.f_node_id = int(node["id"])
        self.f_item_type = node.get("item_type", "product")
        self.f_product_id = node.get("product_id") or (self.product_options[0]["id"] if self.product_options else 0)
        self.f_product_name = node.get("product_name", "")
        self.current_lane_title = node.get("product_name") or node.get("title", "")
        self.f_stage_name = node.get("stage_name", "企划设计")
        self.f_custom_stage = node.get("custom_stage", "")
        self.f_platform_name = node.get("platform_name") or (self.platform_options[0] if self.platform_options else "微店")
        self.f_title = node.get("title", "")
        
        self.f_start_date = node.get("start_date") or ""
        self.f_end_date = node.get("end_date") or ""
        self.f_no_start_date = not bool(self.f_start_date)
        self.f_no_end_date = not bool(self.f_end_date)

        self.f_start_year = int(node.get("start_year", 2026))
        self.f_start_month = int(node.get("start_month", 1))
        self.f_start_period = node.get("start_period", "early")
        self.f_end_year = int(node.get("end_year", 2026))
        self.f_end_month = int(node.get("end_month", 1))
        self.f_end_period = node.get("end_period", "early")

        self.f_status = node.get("status", "planned")
        self.f_color = node.get("color", "violet")
        self.f_remarks = node.get("remarks", "")
        self.is_node_dialog_open = True

    @rx.event
    def close_node_dialog(self):
        self.is_node_dialog_open = False

    # 节点表单输入 Setters
    @rx.event
    def set_f_stage_name(self, val: str): self.f_stage_name = val
    @rx.event
    def set_f_custom_stage(self, val: str): self.f_custom_stage = val
    @rx.event
    def set_f_platform_name(self, val: str): self.f_platform_name = val

    @rx.event
    def set_f_no_start_date(self, val: bool):
        """独立勾选/取消：不设置具体开始日期"""
        self.f_no_start_date = val
        if val:
            self.f_start_date = ""
        else:
            if not self.f_start_date:
                self.f_start_date = period_default_date(self.f_start_year, self.f_start_month, self.f_start_period, False)

    @rx.event
    def set_f_no_end_date(self, val: bool):
        """独立勾选/取消：不设置具体结束日期"""
        self.f_no_end_date = val
        if val:
            self.f_end_date = ""
        else:
            if not self.f_end_date:
                self.f_end_date = period_default_date(self.f_end_year, self.f_end_month, self.f_end_period, True)

    @rx.event
    def set_f_start_date(self, val: str):
        """设置具体开始日期，并自动联动推导开始年份、月份与旬度"""
        self.f_start_date = val.strip()
        if self.f_start_date:
            self.f_no_start_date = False
            s_y, s_m, s_p = date_to_period(self.f_start_date)
            self.f_start_year = s_y
            self.f_start_month = s_m
            self.f_start_period = s_p
            if not self.f_no_end_date and (not self.f_end_date or self.f_end_date < self.f_start_date):
                self.f_end_date = self.f_start_date
                self.f_end_year = s_y
                self.f_end_month = s_m
                self.f_end_period = s_p

    @rx.event
    def set_f_end_date(self, val: str):
        """设置具体结束日期，并自动联动推导结束年份、月份与旬度"""
        self.f_end_date = val.strip()
        if self.f_end_date:
            self.f_no_end_date = False
            e_y, e_m, e_p = date_to_period(self.f_end_date)
            self.f_end_year = e_y
            self.f_end_month = e_m
            self.f_end_period = e_p

    @rx.event
    def set_f_start_year(self, val: str):
        try: 
            self.f_start_year = int(val)
            if not self.f_no_start_date:
                self.f_start_date = period_default_date(self.f_start_year, self.f_start_month, self.f_start_period, False)
        except ValueError: pass

    @rx.event
    def set_f_start_month(self, val: str):
        try: 
            self.f_start_month = int(val)
            if not self.f_no_start_date:
                self.f_start_date = period_default_date(self.f_start_year, self.f_start_month, self.f_start_period, False)
        except ValueError: pass

    @rx.event
    def set_f_start_period(self, val: str): 
        self.f_start_period = val
        if not self.f_no_start_date:
            self.f_start_date = period_default_date(self.f_start_year, self.f_start_month, self.f_start_period, False)

    @rx.event
    def set_f_end_year(self, val: str):
        try: 
            self.f_end_year = int(val)
            if not self.f_no_end_date:
                self.f_end_date = period_default_date(self.f_end_year, self.f_end_month, self.f_end_period, True)
        except ValueError: pass

    @rx.event
    def set_f_end_month(self, val: str):
        try: 
            self.f_end_month = int(val)
            if not self.f_no_end_date:
                self.f_end_date = period_default_date(self.f_end_year, self.f_end_month, self.f_end_period, True)
        except ValueError: pass

    @rx.event
    def set_f_end_period(self, val: str): 
        self.f_end_period = val
        if not self.f_no_end_date:
            self.f_end_date = period_default_date(self.f_end_year, self.f_end_month, self.f_end_period, True)

    @rx.event
    def set_f_status(self, val: str): self.f_status = val
    @rx.event
    def set_f_color(self, val: str): self.f_color = val
    @rx.event
    def set_f_remarks(self, val: str): self.f_remarks = val

    @rx.event
    def submit_node_dialog(self):
        """提交保存节点表单"""
        title = self.f_title.strip()
        if not title and self.f_item_type == "product":
            title = self.f_product_name or "未命名商品"
        elif not title:
            title = self.current_lane_title.replace("🎪 ", "").replace("📌 ", "").strip() or "未命名节点"

        s_date = None if self.f_no_start_date else (self.f_start_date.strip() or None)
        e_date = None if self.f_no_end_date else (self.f_end_date.strip() or None)

        data = {
            "item_type": self.f_item_type,
            "product_id": self.f_product_id if (self.f_item_type == "product" and self.f_product_id > 0) else None,
            "platform_name": self.f_platform_name if (self.f_item_type == "product" and self.f_stage_name == "开售") else None,
            "title": title,
            "stage_name": self.f_stage_name if self.f_item_type == "product" else (self.f_custom_stage or "活动日程"),
            "custom_stage": self.f_custom_stage.strip() if self.f_custom_stage else None,
            "start_date": s_date,
            "end_date": e_date,
            "start_year": self.f_start_year,
            "start_month": self.f_start_month,
            "start_period": self.f_start_period,
            "end_year": self.f_end_year,
            "end_month": self.f_end_month,
            "end_period": self.f_end_period,
            "status": self.f_status,
            "color": self.f_color or "violet",
            "remarks": self.f_remarks.strip() if self.f_remarks else ""
        }

        db = self.get_db()
        try:
            service = ScheduleService(db)
            if self.is_editing:
                service.update_node(self.f_node_id, data)
                msg = "工期节点已成功修改！"
            else:
                service.create_node(data)
                msg = "工期节点已成功创建！"

            self.is_node_dialog_open = False
            yield rx.toast(msg)
            yield ScheduleState.load_schedule_data()
        except Exception as e:
            yield rx.toast(f"保存失败: {e}", level="error")
        finally:
            db.close()
