from django.db import models

class FinanceRecord(models.Model):
    date = models.DateField()
    amount = models.FloatField()
    currency = models.CharField(max_length=20, default="CNY")
    category = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    url = models.URLField(max_length=1000, null=True, blank=True)
    account_id = models.IntegerField(null=True, blank=True, db_column="account_id")
    order_id = models.IntegerField(null=True, blank=True, db_column="order_id")
    related_item_id = models.IntegerField(null=True, blank=True)
    related_cost_id = models.IntegerField(null=True, blank=True, db_column="related_cost_id")

    class Meta:
        db_table = "finance_records"
        verbose_name = "財務流水"
        verbose_name_plural = "財務流水一覧"

    def __str__(self):
        return f"{self.date} - {self.category}: {self.amount} {self.currency}"


class CompanyBalanceItem(models.Model):
    category = models.CharField(max_length=100)  # asset, liability, equity
    name = models.CharField(max_length=255)
    amount = models.FloatField()
    currency = models.CharField(max_length=20, default="CNY")
    asset_type = models.CharField(max_length=100, default="資産")
    finance_record_id = models.IntegerField(null=True, blank=True, db_column="finance_record_id")
    product_id = models.IntegerField(null=True, blank=True, db_column="product_id")

    class Meta:
        db_table = "company_balance_items"
        verbose_name = "資産負債項目"
        verbose_name_plural = "資産負債項目一覧"

    def __str__(self):
        return f"{self.name} ({self.category}): {self.amount} {self.currency}"
