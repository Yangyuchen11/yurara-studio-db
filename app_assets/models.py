from django.db import models

class FixedAsset(models.Model):
    name = models.CharField(max_length=255)
    unit_price = models.FloatField()
    quantity = models.IntegerField()
    remaining_qty = models.IntegerField()
    shop_name = models.CharField(max_length=255, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    purchase_date = models.DateField(auto_now_add=True)
    currency = models.CharField(max_length=20, default="CNY")
    url = models.URLField(max_length=1000, null=True, blank=True)
    finance_record_id = models.IntegerField(null=True, blank=True, db_column="finance_record_id")

    class Meta:
        db_table = "fixed_assets_detail"
        verbose_name = "固定資産"
        verbose_name_plural = "固定資産一覧"

    def __str__(self):
        return self.name


class FixedAssetLog(models.Model):
    asset_name = models.CharField(max_length=255)
    decrease_qty = models.IntegerField()
    reason = models.TextField()
    date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "fixed_asset_logs"
        verbose_name = "固定資産ログ"
        verbose_name_plural = "固定資産ログ一覧"


class ConsumableItem(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    unit_price = models.FloatField()
    initial_quantity = models.IntegerField()
    remaining_qty = models.IntegerField()
    shop_name = models.CharField(max_length=255, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    purchase_date = models.DateField(auto_now_add=True)
    currency = models.CharField(max_length=20, default="CNY")
    url = models.URLField(max_length=1000, null=True, blank=True)
    finance_record_id = models.IntegerField(null=True, blank=True, db_column="finance_record_id")

    class Meta:
        db_table = "consumable_items"
        verbose_name = "消耗品"
        verbose_name_plural = "消耗品一覧"

    def __str__(self):
        return self.name


class ConsumableLog(models.Model):
    item_name = models.CharField(max_length=255)
    change_qty = models.IntegerField()
    value_cny = models.FloatField()
    date = models.DateField(auto_now_add=True)
    note = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "consumable_logs"
        verbose_name = "消耗品ログ"
        verbose_name_plural = "消耗品ログ一覧"
