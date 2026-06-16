# services/memo_service.py
"""
备忘录 CRUD 服务层。
"""
from datetime import datetime
from models import MemoNote


def get_all_memos(db) -> list[MemoNote]:
    """按 created_at 降序返回所有备忘录（最新在前）。"""
    return db.query(MemoNote).order_by(MemoNote.created_at.desc()).all()


def create_memo(db, date_str: str, content: str = "") -> MemoNote:
    """新增一条备忘录。"""
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    memo = MemoNote(
        date=date_str,
        content=content,
        created_at=now_str,
    )
    db.add(memo)
    db.commit()
    db.refresh(memo)
    return memo


def update_memo(db, memo_id: int, date_str: str, content: str) -> MemoNote | None:
    """更新一条备忘录的日期与内容。"""
    memo = db.query(MemoNote).filter(MemoNote.id == memo_id).first()
    if not memo:
        return None
    memo.date = date_str
    memo.content = content
    db.commit()
    db.refresh(memo)
    return memo


def delete_memo(db, memo_id: int) -> bool:
    """删除一条备忘录，成功返回 True。"""
    memo = db.query(MemoNote).filter(MemoNote.id == memo_id).first()
    if not memo:
        return False
    db.delete(memo)
    db.commit()
    return True
