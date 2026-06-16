# yurara_app/state/platforms_state.py
"""
销售平台管理 State 模块。
负责对销售平台的数据进行获取、新增和删除操作。
"""
import reflex as rx
from pydantic import BaseModel
from ..state.app_state import AppState
from models import SalesPlatform

class PlatformDisplayItem(BaseModel):
    id: int = 0
    code: str = ""
    name: str = ""
    currency: str = ""
    fee_rate: float = 0.0
    fee_fixed: float = 0.0
    fee_rate_pct_str: str = ""

class PlatformsState(AppState):
    platforms: list[PlatformDisplayItem] = []
    
    # 新增平台表单状态
    new_code: str = ""
    new_name: str = ""
    new_currency: str = "CNY"
    new_fee_rate: float = 0.0
    new_fee_fixed: float = 0.0

    @rx.var
    def currency_options(self) -> list[str]:
        """所有可用于平台的币种列表 (CNY + AppState.rates_map 中的其他外币)"""
        return ["CNY"] + list(self.rates_map.keys())

    @rx.event
    def load_platforms(self):
        """从数据库读取所有平台信息"""
        db = self.get_db()
        try:
            raw_platforms = db.query(SalesPlatform).order_by(SalesPlatform.id.asc()).all()
            self.platforms = [
                PlatformDisplayItem(
                    id=p.id,
                    code=p.code,
                    name=p.name,
                    currency=p.currency,
                    fee_rate=p.fee_rate,
                    fee_fixed=p.fee_fixed,
                    fee_rate_pct_str=f"{p.fee_rate * 100:.2f}%"
                ) for p in raw_platforms
            ]
        finally:
            db.close()

    @rx.event
    def set_new_code(self, val: str): self.new_code = val
    @rx.event
    def set_new_name(self, val: str): self.new_name = val
    @rx.event
    def set_new_currency(self, val: str): self.new_currency = val
    @rx.event
    def set_new_fee_rate(self, val: str):
        try: self.new_fee_rate = float(val) / 100.0 if val else 0.0
        except ValueError: pass
    @rx.event
    def set_new_fee_fixed(self, val: str):
        try: self.new_fee_fixed = float(val) if val else 0.0
        except ValueError: pass

    @rx.event
    def add_platform(self):
        """新增销售平台"""
        code = self.new_code.strip().lower()
        name = self.new_name.strip()
        if not code:
            yield rx.toast("平台代号不能为空", level="error")
            return
        if not name:
            yield rx.toast("平台名称不能为空", level="error")
            return

        db = self.get_db()
        try:
            # 校验代号唯一性
            exist_code = db.query(SalesPlatform).filter(SalesPlatform.code == code).first()
            if exist_code:
                yield rx.toast(f"平台代号 '{code}' 已存在，请换一个", level="error")
                return
            
            exist_name = db.query(SalesPlatform).filter(SalesPlatform.name == name).first()
            if exist_name:
                yield rx.toast(f"平台名称 '{name}' 已存在，请换一个", level="error")
                return

            new_p = SalesPlatform(
                code=code,
                name=name,
                currency=self.new_currency,
                fee_rate=self.new_fee_rate,
                fee_fixed=self.new_fee_fixed
            )
            db.add(new_p)
            db.commit()
            
            yield rx.toast(f"🎉 成功追加销售平台: {name}！")
            # 重置表单
            self.new_code = ""
            self.new_name = ""
            self.new_currency = "CNY"
            self.new_fee_rate = 0.0
            self.new_fee_fixed = 0.0
            
            yield PlatformsState.load_platforms()
        except Exception as e:
            db.rollback()
            yield rx.toast(f"保存平台失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def delete_platform(self, platform_id: int):
        """物理删除销售平台"""
        db = self.get_db()
        try:
            target = db.query(SalesPlatform).filter(SalesPlatform.id == platform_id).first()
            if not target:
                yield rx.toast("未找到该销售平台", level="error")
                return
            
            name = target.name
            db.delete(target)
            db.commit()
            yield rx.toast(f"🗑️ 已成功删除销售平台: {name}")
            yield PlatformsState.load_platforms()
        except Exception as e:
            db.rollback()
            yield rx.toast(f"删除失败: {e}", level="error")
        finally:
            db.close()
