# services/schedule_service.py
"""
工期日程业务逻辑层。
实现 36 旬索引转换、具体日期与旬度双向匹配、日期按天数像素精准分割定位、同旬具体日期精确排序、节点位移与 CRUD 操作。
"""
from datetime import datetime, date, timedelta
import calendar
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import nulls_last
from models import ScheduleNode, Product, SalesPlatform


PERIOD_MAP = {"early": 0, "mid": 1, "late": 2}
REVERSE_PERIOD_MAP = {0: "early", 1: "mid", 2: "late"}
PERIOD_LABELS = {"early": "上旬", "mid": "中旬", "late": "下旬"}


def period_to_index(year: int, month: int, period: str) -> int:
    """将 (year, month, period) 转换为从元年开始计量的全局旬度整数索引"""
    p_val = PERIOD_MAP.get(period, 0)
    return year * 36 + (month - 1) * 3 + p_val


def index_to_period(index: int) -> Tuple[int, int, str]:
    """将全局旬度整数索引还原为 (year, month, period)"""
    year = index // 36
    rem = index % 36
    month = (rem // 3) + 1
    period = REVERSE_PERIOD_MAP.get(rem % 3, "early")
    return year, month, period


def date_to_period(date_str: str) -> Tuple[int, int, str]:
    """根据具体日期字符串 (如 '2026-08-15') 自动推导所属 (年份, 月份, 旬度)"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day = dt.day
    if day <= 10:
        period = "early"
    elif day <= 20:
        period = "mid"
    else:
        period = "late"
    return dt.year, dt.month, period


def period_default_date(year: int, month: int, period: str, is_end: bool = False) -> str:
    """获取指定旬度的推荐默认具体日期"""
    if period == "early":
        d = 10 if is_end else 1
    elif period == "mid":
        d = 20 if is_end else 11
    else:
        if is_end:
            if month in [1, 3, 5, 7, 8, 10, 12]:
                d = 31
            elif month in [4, 6, 9, 11]:
                d = 30
            else:
                d = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
        else:
            d = 21
    return f"{year:04d}-{month:02d}-{d:02d}"


def date_to_pixel_offset(year: int, month: int, day: int, is_end: bool = False) -> float:
    """将具体日期换算为当年 3600px 时间轴上的像素 X 坐标 (每月 300px，上中下旬各 100px，按天数精确分割)"""
    month_offset = (month - 1) * 300.0
    days_in_m = calendar.monthrange(year, month)[1]
    
    if day <= 10:
        frac = float(day) / 10.0 if is_end else float(day - 1) / 10.0
        slot_offset = frac * 100.0
    elif day <= 20:
        frac = float(day - 10) / 10.0 if is_end else float(day - 11) / 10.0
        slot_offset = 100.0 + frac * 100.0
    else:
        late_days = float(days_in_m - 20)
        frac = float(day - 20) / late_days if is_end else float(day - 21) / late_days
        slot_offset = 200.0 + frac * 100.0
        
    return month_offset + slot_offset


def format_period_range(
    start_year: int, start_month: int, start_period: str,
    end_year: int, end_month: int, end_period: str,
    start_date: Optional[str] = "", end_date: Optional[str] = ""
) -> str:
    """生成带具体日期与旬度的时间范围友好展示文本"""
    s_label = PERIOD_LABELS.get(start_period, "上旬")
    e_label = PERIOD_LABELS.get(end_period, "上旬")
    
    if start_date and end_date:
        if start_date == end_date:
            return f"{start_date} ({start_month}月{s_label})"
        return f"{start_date} ~ {end_date}"
    elif start_date:
        return f"{start_date} ~ {end_month}月{e_label}"
    elif end_date:
        return f"{start_month}月{s_label} ~ {end_date}"
    else:
        if start_year == end_year and start_month == end_month and start_period == end_period:
            return f"{start_year}年{start_month}月 {s_label}"
        elif start_year == end_year:
            return f"{start_year}年 {start_month}月{s_label} ~ {end_month}月{e_label}"
        else:
            return f"{start_year}年{start_month}月{s_label} ~ {end_year}年{end_month}月{e_label}"


def get_current_period() -> Tuple[int, int, str]:
    """获取当前系统日期所属的 (年份, 月份, 旬度)"""
    today = date.today()
    day = today.day
    if day <= 10:
        period = "early"
    elif day <= 20:
        period = "mid"
    else:
        period = "late"
    return today.year, today.month, period


class ScheduleService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_products(self) -> list[Product]:
        """获取所有商品列表"""
        return self.db.query(Product).order_by(Product.id.asc()).all()

    def get_all_platforms(self) -> list[SalesPlatform]:
        """获取所有平台列表"""
        return self.db.query(SalesPlatform).order_by(SalesPlatform.id.asc()).all()

    def get_nodes(
        self,
        year: Optional[int] = None,
        item_type: Optional[str] = None,
        product_id: Optional[int] = None
    ) -> list[ScheduleNode]:
        """
        获取工期与活动节点。
        按照 (开始年份, 开始月份, 开始旬度, start_date) 严格升序排列。
        同旬度内的节点，根据具体 start_date 的先后自然排列。
        """
        query = self.db.query(ScheduleNode)
        
        if year is not None:
            query = query.filter(
                (ScheduleNode.start_year <= year) & (ScheduleNode.end_year >= year)
            )
        
        if item_type and item_type != "all":
            query = query.filter(ScheduleNode.item_type == item_type)
            
        if product_id:
            query = query.filter(ScheduleNode.product_id == product_id)

        nodes = query.all()

        def node_sort_key(n: ScheduleNode):
            s_idx = period_to_index(n.start_year, n.start_month, n.start_period)
            s_date_str = n.start_date or "9999-12-31"
            return (s_idx, s_date_str, n.id)

        return sorted(nodes, key=node_sort_key)

    def get_node_by_id(self, node_id: int) -> Optional[ScheduleNode]:
        return self.db.query(ScheduleNode).filter(ScheduleNode.id == node_id).first()

    def create_node(self, data: dict) -> ScheduleNode:
        """创建新的工期或活动节点 (支持只设置旬度或精确具体日期)"""
        start_date = data.get("start_date") or None
        if start_date:
            s_year, s_month, s_period = date_to_period(start_date)
            data["start_year"], data["start_month"], data["start_period"] = s_year, s_month, s_period
        else:
            s_year = int(data.get("start_year") or 2026)
            s_month = int(data.get("start_month") or 1)
            s_period = data.get("start_period") or "early"

        end_date = data.get("end_date") or None
        if end_date:
            e_year, e_month, e_period = date_to_period(end_date)
            data["end_year"], data["end_month"], data["end_period"] = e_year, e_month, e_period
        else:
            e_year = int(data.get("end_year") or s_year)
            e_month = int(data.get("end_month") or s_month)
            e_period = data.get("end_period") or s_period

        s_idx = period_to_index(s_year, s_month, s_period)
        e_idx = period_to_index(e_year, e_month, e_period)
        
        # 确保结束时间不早于开始时间
        if e_idx < s_idx or (start_date and end_date and end_date < start_date):
            e_idx = s_idx
            e_year, e_month, e_period = s_year, s_month, s_period
            end_date = start_date

        pid = data.get("product_id")
        product_id = None
        if pid and int(pid) > 0:
            p_obj = self.db.query(Product).filter(Product.id == int(pid)).first()
            if p_obj:
                product_id = p_obj.id

        title = str(data.get("title") or "").strip()
        stage_name = str(data.get("stage_name") or "企划设计").strip() if data.get("stage_name") is not None else None
        custom_stage = str(data.get("custom_stage") or "").strip() if data.get("custom_stage") else None
        platform_name = str(data.get("platform_name") or "").strip() if data.get("platform_name") else None
        remarks = str(data.get("remarks") or "").strip()

        node = ScheduleNode(
            item_type=data.get("item_type", "product"),
            product_id=product_id,
            platform_name=platform_name,
            title=title,
            stage_name=stage_name,
            custom_stage=custom_stage,
            start_date=start_date,
            end_date=end_date,
            start_year=s_year,
            start_month=s_month,
            start_period=s_period,
            end_year=e_year,
            end_month=e_month,
            end_period=e_period,
            status=data.get("status", "planned"),
            color=data.get("color", "violet"),
            remarks=remarks
        )
        self.db.add(node)
        self.db.commit()
        self.db.refresh(node)
        return node

    def update_node(self, node_id: int, updates: dict) -> ScheduleNode:
        """更新工期节点"""
        node = self.get_node_by_id(node_id)
        if not node:
            raise ValueError(f"工期节点 ID {node_id} 不存在")

        # 处理日期联动
        if "start_date" in updates:
            sd = updates["start_date"] or None
            if sd:
                s_year, s_month, s_period = date_to_period(sd)
                updates["start_year"] = s_year
                updates["start_month"] = s_month
                updates["start_period"] = s_period
                updates["start_date"] = sd
            else:
                updates["start_date"] = None
        
        if "end_date" in updates:
            ed = updates["end_date"] or None
            if ed:
                e_year, e_month, e_period = date_to_period(ed)
                updates["end_year"] = e_year
                updates["end_month"] = e_month
                updates["end_period"] = e_period
                updates["end_date"] = ed
            else:
                updates["end_date"] = None

        if "product_id" in updates:
            pid = updates["product_id"]
            if pid and int(pid) > 0:
                p_obj = self.db.query(Product).filter(Product.id == int(pid)).first()
                updates["product_id"] = p_obj.id if p_obj else None
            else:
                updates["product_id"] = None

        for key, val in updates.items():
            if hasattr(node, key):
                setattr(node, key, val)

        # 确保结束时间不早于开始时间
        s_idx = period_to_index(node.start_year, node.start_month, node.start_period)
        e_idx = period_to_index(node.end_year, node.end_month, node.end_period)
        if e_idx < s_idx or (node.start_date and node.end_date and node.end_date < node.start_date):
            node.end_year = node.start_year
            node.end_month = node.start_month
            node.end_period = node.start_period
            node.end_date = node.start_date

        self.db.commit()
        self.db.refresh(node)
        return node

    def shift_node(self, node_id: int, delta_periods: int) -> ScheduleNode:
        """前后微调平移 1 旬 (保持跨度不变，并平移具体日期)"""
        node = self.get_node_by_id(node_id)
        if not node:
            raise ValueError(f"工期节点 ID {node_id} 不存在")

        s_idx = period_to_index(node.start_year, node.start_month, node.start_period) + delta_periods
        e_idx = period_to_index(node.end_year, node.end_month, node.end_period) + delta_periods

        node.start_year, node.start_month, node.start_period = index_to_period(s_idx)
        node.end_year, node.end_month, node.end_period = index_to_period(e_idx)

        # 同步更新具体日期（若原本存在具体日期）
        try:
            if node.start_date:
                s_dt = datetime.strptime(node.start_date, "%Y-%m-%d") + timedelta(days=10 * delta_periods)
                node.start_date = s_dt.strftime("%Y-%m-%d")
            if node.end_date:
                e_dt = datetime.strptime(node.end_date, "%Y-%m-%d") + timedelta(days=10 * delta_periods)
                node.end_date = e_dt.strftime("%Y-%m-%d")
        except Exception:
            pass

        self.db.commit()
        self.db.refresh(node)
        return node

    def delete_node(self, node_id: int) -> bool:
        """删除节点"""
        node = self.get_node_by_id(node_id)
        if node:
            self.db.delete(node)
            self.db.commit()
            return True
        return False

    def delete_lane_nodes(self, lane_type: str, product_id: int, lane_title: str) -> int:
        """删除整条泳道/项目行下的所有阶段节点"""
        query = self.db.query(ScheduleNode)
        clean_title = lane_title.replace("👗 ", "").replace("🎪 ", "").replace("📌 ", "").strip()
        if lane_type == "product" and product_id > 0:
            query = query.filter(ScheduleNode.item_type == "product", ScheduleNode.product_id == product_id)
        elif lane_type == "event":
            if clean_title == "展会与活动":
                query = query.filter(ScheduleNode.item_type == "event", (ScheduleNode.title == "展会与活动") | (ScheduleNode.title == "") | (ScheduleNode.title.is_(None)))
            else:
                query = query.filter(ScheduleNode.item_type == "event", ScheduleNode.title == clean_title)
        elif lane_type == "other":
            if clean_title in ["其他", "运营与综合事务"]:
                query = query.filter(ScheduleNode.item_type == "other", (ScheduleNode.title.in_(["其他", "运营与综合事务"])) | (ScheduleNode.title == "") | (ScheduleNode.title.is_(None)))
            else:
                query = query.filter(ScheduleNode.item_type == "other", ScheduleNode.title == clean_title)
        else:
            return 0
        
        nodes = query.all()
        count = len(nodes)
        for n in nodes:
            self.db.delete(n)
        self.db.commit()
        return count
