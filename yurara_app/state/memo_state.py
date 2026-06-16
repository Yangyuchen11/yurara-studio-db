# yurara_app/state/memo_state.py
"""
备忘录功能的 State 层。
管理：备忘录列表、搜索词、弹窗开关、字段编辑。
"""
from datetime import date as _date
import reflex as rx
from .app_state import AppState


class MemoState(AppState):
    """备忘录状态，继承自 AppState 以复用 get_db()。"""

    # 备忘录列表（按 created_at 降序）
    memos: list[dict] = []

    # 搜索关键词
    memo_search_query: str = ""

    # 弹窗开关
    memo_dialog_open: bool = False

    # ---- 计算属性 ----

    @rx.var
    def filtered_memos(self) -> list[dict]:
        """按搜索词（同时匹配 date 和 content）过滤备忘录列表。"""
        q = self.memo_search_query.strip().lower()
        if not q:
            return self.memos
        return [
            m for m in self.memos
            if q in m.get("date", "").lower() or q in m.get("content", "").lower()
        ]

    @rx.var
    def latest_memo_preview(self) -> str:
        """返回最新一条备忘录的预览文本（最多 120 字）。"""
        if not self.memos:
            return "暂无备忘录…"
        latest = self.memos[0]
        date_str = latest.get("date", "")
        content = latest.get("content", "").strip()
        if not content:
            return f"{date_str}（空白备忘录）"
        preview = f"{date_str}  {content}"
        return preview[:120]

    @rx.var
    def has_memos(self) -> bool:
        return len(self.memos) > 0

    # ---- 事件处理器 ----

    @rx.event
    def load_memos(self):
        """从数据库加载所有备忘录。"""
        db = self.get_db()
        try:
            from services.memo_service import get_all_memos
            rows = get_all_memos(db)
            self.memos = [
                {
                    "id": r.id,
                    "date": r.date or "",
                    "content": r.content or "",
                    "created_at": r.created_at or "",
                }
                for r in rows
            ]
        except Exception as e:
            self.toast_message = f"❌ 加载备忘录失败: {e}"
            self.toast_icon = "⚠️"
        finally:
            db.close()

    @rx.event
    def add_memo(self):
        """新增一条今天日期的空白备忘录。"""
        today_str = _date.today().isoformat()
        db = self.get_db()
        try:
            from services.memo_service import create_memo
            memo = create_memo(db, date_str=today_str, content="")
            # 插入到列表最前面（最新）
            self.memos = [
                {
                    "id": memo.id,
                    "date": memo.date or "",
                    "content": memo.content or "",
                    "created_at": memo.created_at or "",
                }
            ] + list(self.memos)
        except Exception as e:
            self.toast_message = f"❌ 新增备忘录失败: {e}"
            self.toast_icon = "⚠️"
        finally:
            db.close()

    @rx.event
    def update_memo_date(self, memo_id: int, new_date: str):
        """更新备忘录的日期字段（blur 触发）。"""
        db = self.get_db()
        try:
            # 先找到当前 content
            target = next((m for m in self.memos if m["id"] == memo_id), None)
            if not target:
                return
            from services.memo_service import update_memo
            update_memo(db, memo_id, date_str=new_date, content=target["content"])
            # 同步更新本地状态
            self.memos = [
                {**m, "date": new_date} if m["id"] == memo_id else m
                for m in self.memos
            ]
        except Exception as e:
            self.toast_message = f"❌ 更新日期失败: {e}"
            self.toast_icon = "⚠️"
        finally:
            db.close()

    @rx.event
    def update_memo_content(self, memo_id: int, new_content: str):
        """更新备忘录的内容字段（blur 触发）。"""
        db = self.get_db()
        try:
            target = next((m for m in self.memos if m["id"] == memo_id), None)
            if not target:
                return
            from services.memo_service import update_memo
            update_memo(db, memo_id, date_str=target["date"], content=new_content)
            # 同步更新本地状态（也更新 latest_memo_preview）
            self.memos = [
                {**m, "content": new_content} if m["id"] == memo_id else m
                for m in self.memos
            ]
        except Exception as e:
            self.toast_message = f"❌ 更新内容失败: {e}"
            self.toast_icon = "⚠️"
        finally:
            db.close()

    @rx.event
    def delete_memo(self, memo_id: int):
        """删除一条备忘录。"""
        db = self.get_db()
        try:
            from services.memo_service import delete_memo
            delete_memo(db, memo_id)
            self.memos = [m for m in self.memos if m["id"] != memo_id]
        except Exception as e:
            self.toast_message = f"❌ 删除备忘录失败: {e}"
            self.toast_icon = "⚠️"
        finally:
            db.close()

    @rx.event
    def set_memo_search_query(self, val: str):
        self.memo_search_query = val

    @rx.event
    def open_memo_dialog(self):
        """打开备忘录弹窗并刷新数据。"""
        self.memo_dialog_open = True
        return MemoState.load_memos()

    @rx.event
    def close_memo_dialog(self):
        self.memo_dialog_open = False
        self.memo_search_query = ""
