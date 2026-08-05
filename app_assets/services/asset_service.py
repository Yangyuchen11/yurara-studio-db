# app_assets/services/asset_service.py
from datetime import date
from django.db import transaction
from app_assets.models import FixedAsset, FixedAssetLog
from app_core.constants import Currency, to_cny

class AssetService:
    @staticmethod
    def get_all_assets():
        return FixedAsset.objects.all()

    @staticmethod
    def get_active_assets():
        return FixedAsset.objects.filter(remaining_qty__gt=0)

    @staticmethod
    def calculate_asset_totals(assets, rates_map: dict):
        total_val_cny_equiv = 0.0
        total_remain_val_cny_equiv = 0.0
        total_remain_val_jpy_only = 0.0

        for a in assets:
            curr = getattr(a, "currency", Currency.CNY) or Currency.CNY
            total_val_cny_equiv += to_cny(a.unit_price * a.quantity, curr, rates_map)

            remain_origin = a.unit_price * a.remaining_qty
            total_remain_val_cny_equiv += to_cny(remain_origin, curr, rates_map)

            if curr == Currency.JPY:
                total_remain_val_jpy_only += remain_origin

        return total_val_cny_equiv, total_remain_val_cny_equiv, total_remain_val_jpy_only

    @staticmethod
    def update_asset_info(asset_id: int, updates: dict) -> bool:
        asset = FixedAsset.objects.filter(id=asset_id).first()
        if asset:
            for field, value in updates.items():
                if hasattr(asset, field):
                    setattr(asset, field, value)
            asset.save()
            return True
        return False

    @staticmethod
    @transaction.atomic
    def write_off_asset(asset_id: int, decrease_qty: int, reason: str) -> str:
        target_asset = FixedAsset.objects.filter(id=asset_id).first()
        if not target_asset:
            raise ValueError("資産が存在しません。")

        if target_asset.remaining_qty < decrease_qty:
            raise ValueError(f"残数が不足しています (現在: {target_asset.remaining_qty})")

        target_asset.remaining_qty -= decrease_qty
        target_asset.save()

        FixedAssetLog.objects.create(
            asset_name=target_asset.name,
            decrease_qty=decrease_qty,
            reason=reason,
            date=date.today()
        )
        return target_asset.name

    @staticmethod
    def get_asset_logs(limit=100):
        return FixedAssetLog.objects.order_by('-id')[:limit]
