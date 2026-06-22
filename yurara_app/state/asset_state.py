# yurara_app/state/asset_state.py
"""
固定资产管理 State 模块。
处理固定资产获取、统计计算、编辑保存和核销报废的交互。
"""
import reflex as rx
from pydantic import BaseModel
from ..state.app_state import AppState
from services.asset_service import AssetService

from constants import to_cny

class AssetItem(BaseModel):
    id: int = 0
    name: str = ""
    currency: str = ""
    unit_price: float = 0.0
    quantity: float = 0.0
    remaining_qty: float = 0.0
    total_price: float = 0.0
    remaining_cny: float = 0.0
    remaining_original: float = 0.0
    shop_name: str = ""
    url: str = ""
    remarks: str = ""

class AssetLogItem(BaseModel):
    id: int = 0
    date: str = ""
    asset_name: str = ""
    decrease_qty: float = 0.0
    reason: str = ""

class AssetState(AppState):
    assets: list[AssetItem] = []
    logs: list[AssetLogItem] = []
    
    # 统计数据
    val_total: float = 0.0
    val_remain: float = 0.0
    val_jpy_raw: float = 0.0
    
    is_loading: bool = False
    
    # 编辑模态框状态
    is_edit_open: bool = False
    edit_asset_id: int = 0
    edit_name: str = ""
    edit_shop_name: str = ""
    edit_url: str = ""
    edit_remarks: str = ""
    
    # 核销操作表单状态
    write_off_asset_id: str = ""  # 选中资产ID
    write_off_max_qty: float = 1.0  # 选中资产最大可核销数量
    write_off_qty: float = 1.0     # 用户输入的核销数量
    write_off_reason: str = ""    # 核销原因

    # 搜索状态
    asset_search_query: str = ""

    # ===================== 计算属性 =====================

    @rx.var
    def val_total_str(self) -> str:
        return f"{self.val_total:,.2f} CNY"

    @rx.var
    def val_remain_str(self) -> str:
        return f"{self.val_remain:,.2f} CNY"

    @rx.var
    def has_assets(self) -> bool:
        return len(self.assets) > 0

    @rx.var
    def filtered_assets(self) -> list[AssetItem]:
        """根据搜索词过滤资产清单（匹配名称、店铺、备注、币种）"""
        if not self.asset_search_query.strip():
            return self.assets
        q = self.asset_search_query.strip().lower()
        return [
            a for a in self.assets
            if q in a.name.lower()
            or q in a.shop_name.lower()
            or q in a.remarks.lower()
            or q in a.currency.lower()
        ]

    @rx.var
    def active_assets_options(self) -> list[dict[str, str]]:
        """为下拉选择构建可核销资产的选项"""
        options = []
        for a in self.assets:
            if a.remaining_qty > 0.001:
                options.append({
                    "value": str(a.id),
                    "label": f"{a.name} (余: {int(a.remaining_qty)})"
                })
        return options

    # ===================== 事件处理器 =====================

    @rx.event
    def load_asset_page(self):
        """加载所有的固定资产信息、计算指标与核销审计日志"""
        self.is_loading = True
        db = self.get_db()
        try:
            # 1. 资产列表
            raw_assets = AssetService.get_all_assets(db)
            formatted_assets = []
            for a in raw_assets:
                curr = getattr(a, "currency", "CNY")
                remain_origin = a.unit_price * a.remaining_qty
                total_origin = a.unit_price * a.quantity
                
                show_cny = to_cny(remain_origin, curr, self.rates_map)
                show_original = remain_origin

                formatted_assets.append(AssetItem(
                    id=a.id,
                    name=a.name,
                    currency=curr,
                    unit_price=round(float(a.unit_price), 2),
                    quantity=round(float(a.quantity), 2),
                    remaining_qty=round(float(a.remaining_qty), 2),
                    total_price=round(float(total_origin), 2),
                    remaining_cny=round(float(show_cny), 2),
                    remaining_original=round(float(show_original), 2),
                    shop_name=a.shop_name or "",
                    url=getattr(a, 'url', '') or "",
                    remarks=a.remarks or ""
                ))
            self.assets = formatted_assets

            # 2. 计算大项指标
            if raw_assets:
                v_total, v_remain, v_jpy_raw = AssetService.calculate_asset_totals(raw_assets, self.rates_map)
                self.val_total = round(float(v_total), 2)
                self.val_remain = round(float(v_remain), 2)
                self.val_jpy_raw = round(float(v_jpy_raw), 2)
            else:
                self.val_total = 0.0
                self.val_remain = 0.0
                self.val_jpy_raw = 0.0

            # 3. 核销日志
            raw_logs = AssetService.get_asset_logs(db)
            self.logs = [AssetLogItem(
                    id=l.id,
                    date=str(l.date),
                    asset_name=l.asset_name,
                    decrease_qty=round(float(l.decrease_qty), 2),
                    reason=l.reason or ""
                ) for l in raw_logs]

            # 4. 初始化核销表单选择默认值
            active_opts = self.active_assets_options
            if active_opts and not self.write_off_asset_id:
                self.on_select_write_off_asset(active_opts[0]["value"])
                
        finally:
            db.close()
            self.is_loading = False

    @rx.event
    def open_edit_dialog(self, asset: AssetItem):
        """将选定资产的数据载入编辑对话框"""
        self.edit_asset_id = asset.id
        self.edit_name = asset.name
        self.edit_shop_name = asset.shop_name
        self.edit_url = asset.url
        self.edit_remarks = asset.remarks
        self.is_edit_open = True

    @rx.event
    def close_edit_dialog(self):
        """关闭并重置编辑状态"""
        self.is_edit_open = False
        self.edit_asset_id = 0
        self.edit_name = ""
        self.edit_shop_name = ""
        self.edit_url = ""
        self.edit_remarks = ""

    @rx.event
    def submit_edit_asset(self):
        """保存固定资产信息更改"""
        if not self.edit_shop_name.strip():
            yield rx.toast("店名/来源不能为空", level="error")
            return
            
        db = self.get_db()
        try:
            updates = {
                "shop_name": self.edit_shop_name.strip(),
                "url": self.edit_url.strip(),
                "remarks": self.edit_remarks.strip()
            }
            if AssetService.update_asset_info(db, self.edit_asset_id, updates):
                yield rx.toast("💾 固定资产信息更新成功！")
                yield AssetState.load_asset_page()
                self.is_edit_open = False
            else:
                yield rx.toast("更新失败，未找到该资产项", level="error")
        except Exception as e:
            yield rx.toast(f"保存更新失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def on_select_write_off_asset(self, asset_id: str):
        """当用户在下拉选框选中要核销的资产时，同步更新数量上限"""
        self.write_off_asset_id = asset_id
        for a in self.assets:
            if str(a.id) == asset_id:
                self.write_off_max_qty = a.remaining_qty
                # 如果当前填写的数量超出新上限，则重置为新上限
                if self.write_off_qty > a.remaining_qty or self.write_off_qty <= 0:
                    self.write_off_qty = 1.0
                break

    @rx.event
    def submit_write_off(self):
        """提交核销报废资产的请求"""
        if not self.write_off_asset_id:
            yield rx.toast("请选择要核销的固定资产", level="error")
            return
        if not self.write_off_reason.strip():
            yield rx.toast("请填写核销原因说明", level="error")
            return
        if self.write_off_qty <= 0 or self.write_off_qty > self.write_off_max_qty:
            yield rx.toast(f"核销数量有误 (范围: 1 到 {int(self.write_off_max_qty)})", level="error")
            return

        db = self.get_db()
        try:
            target_id = int(self.write_off_asset_id)
            name = AssetService.write_off_asset(
                db, 
                target_id, 
                self.write_off_qty, 
                self.write_off_reason.strip()
            )
            yield rx.toast(f"📉 已核销 {int(self.write_off_qty)} 个 {name}！")
            # 重置核销表单状态
            self.write_off_qty = 1.0
            self.write_off_reason = ""
            # 重新加载页面数据
            yield AssetState.load_asset_page()
        except Exception as e:
            yield rx.toast(f"核销处理失败: {e}", level="error")
        finally:
            db.close()

    @rx.event
    def set_write_off_qty(self, val: float):
        self.write_off_qty = val

    @rx.event
    def set_edit_shop_name(self, val: str): self.edit_shop_name = val

    @rx.event
    def set_edit_url(self, val: str): self.edit_url = val

    @rx.event
    def set_edit_remarks(self, val: str): self.edit_remarks = val

    @rx.event
    def set_write_off_reason(self, val: str): self.write_off_reason = val

    @rx.event
    def set_asset_search_query(self, val: str): self.asset_search_query = val
