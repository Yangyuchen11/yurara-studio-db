# app_core/services/memo_service.py
from datetime import datetime
from app_core.models import MemoNote

def get_all_memos() -> list[MemoNote]:
    """作成日時降順で全備忘録を取得。"""
    return list(MemoNote.objects.order_by('-created_at'))

def create_memo(date_str: str, content: str = "") -> MemoNote:
    """新規備忘録を作成。"""
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return MemoNote.objects.create(
        date=date_str,
        content=content,
        created_at=now_str
    )

def update_memo(memo_id: int, date_str: str, content: str) -> MemoNote | None:
    """備忘録を更新。"""
    memo = MemoNote.objects.filter(id=memo_id).first()
    if not memo:
        return None
    memo.date = date_str
    memo.content = content
    memo.save()
    return memo

def delete_memo(memo_id: int) -> bool:
    """備忘録を削除。"""
    count, _ = MemoNote.objects.filter(id=memo_id).delete()
    return count > 0
