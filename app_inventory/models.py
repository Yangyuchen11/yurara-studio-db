from django.db import models

class InventoryLog(models.Model):
    product_name = models.CharField(max_length=255)
    variant = models.CharField(max_length=255, null=True, blank=True)
    change_amount = models.IntegerField()
    reason = models.CharField(max_length=255)
    date = models.DateField(auto_now_add=True)
    note = models.TextField(null=True, blank=True)
    is_sold = models.BooleanField(default=False)
    sale_amount = models.FloatField(default=0.0)
    currency = models.CharField(max_length=20, null=True, blank=True)
    platform = models.CharField(max_length=100, null=True, blank=True)
    is_other_out = models.BooleanField(default=False)
    warehouse_id = models.IntegerField(null=True, blank=True, db_column="warehouse_id")
    part_name = models.CharField(max_length=255, null=True, blank=True)
    order_id = models.IntegerField(null=True, blank=True, db_column="order_id")
    cost_item_id = models.IntegerField(null=True, blank=True, db_column="cost_item_id")

    class Meta:
        db_table = "inventory_logs"
        verbose_name = "在庫ログ"
        verbose_name_plural = "在庫ログ一覧"

    def __str__(self):
        return f"{self.date} - {self.product_name} ({self.reason}): {self.change_amount}"
