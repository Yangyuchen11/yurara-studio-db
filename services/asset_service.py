# services/asset_service.py
from datetime import date
from sqlalchemy import func
from models import FixedAsset, FixedAssetLog
from constants import Currency

class AssetService:
    """
    负责处理固定资产的业务逻辑
    """

    @staticmethod
    def get_all_assets(db):
        """获取所有固定资产记录"""
        return db.query(FixedAsset).all()

    @staticmethod
    def get_active_assets(db):
        """获取剩余数量大于0的活跃资产"""
        # 注意：这里假设 remaining_qty 是整数或浮点数，做 > 0 判断
        return db.query(FixedAsset).filter(FixedAsset.remaining_qty > 0).all()

    @staticmethod
    def calculate_asset_totals(assets, exchange_rate):
        """
        计算资产总值统计信息
        返回: (总采购价值(CNY折算), 当前剩余价值(CNY折算), 仅日元资产原值)
        """
        total_val_cny_equiv = 0.0
        total_remain_val_cny_equiv = 0.0
        total_remain_val_jpy_only = 0.0

        for a in assets:
            curr = getattr(a, "currency", Currency.CNY)
            # 计算汇率系数
            rate = exchange_rate if curr == Currency.JPY else 1.0
            
            # 累加采购总值 (折合CNY)
            total_val_cny_equiv += (a.unit_price * a.quantity) * rate
            
            # 计算剩余价值
            remain_origin = a.unit_price * a.remaining_qty
            total_remain_val_cny_equiv += remain_origin * rate

            if curr == Currency.JPY:
                total_remain_val_jpy_only += remain_origin
                
        return total_val_cny_equiv, total_remain_val_cny_equiv, total_remain_val_jpy_only

    @staticmethod
    def update_asset_info(db, asset_id, updates: dict):
        """
        更新资产基础信息 (如店名、备注)
        updates: 包含字段名和新值的字典
        """
        asset = db.query(FixedAsset).filter(FixedAsset.id == asset_id).first()
        if asset:
            for field, value in updates.items():
                if hasattr(asset, field):
                    setattr(asset, field, value)
            db.commit()
            return True
        return False

    @staticmethod
    def write_off_asset(db, asset_id, decrease_qty, reason):
        """
        执行资产核销/报废
        """
        target_asset = db.query(FixedAsset).filter(FixedAsset.id == asset_id).first()
        
        if not target_asset:
            raise ValueError("资产不存在")
            
        if target_asset.remaining_qty < decrease_qty:
            raise ValueError(f"剩余数量不足 (当前: {target_asset.remaining_qty})")

        # A. 减少库存
        target_asset.remaining_qty -= decrease_qty
        
        # B. 记录日志
        new_log = FixedAssetLog(
            asset_name=target_asset.name,
            decrease_qty=decrease_qty,
            reason=reason,
            date=date.today()
        )
        db.add(new_log)
        db.commit()
        return target_asset.name

    @staticmethod
    def get_asset_logs(db, limit=100):
        """获取核销记录"""
        return db.query(FixedAssetLog).order_by(FixedAssetLog.id.desc()).limit(limit).all()
