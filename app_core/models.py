from django.db import models

class Warehouse(models.Model):
    name = models.CharField(max_length=255, unique=True, db_index=True)
    remarks = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "warehouses"
        verbose_name = "倉庫"
        verbose_name_plural = "倉庫一覧"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    total_quantity = models.IntegerField(default=0)
    marketable_quantity = models.IntegerField(default=0)
    is_production_completed = models.BooleanField(default=False)
    target_platform = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "products"
        verbose_name = "商品"
        verbose_name_plural = "商品一覧"

    def __str__(self):
        return self.name


class ProductColor(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="colors", db_column="product_id")
    color_name = models.CharField(max_length=255)
    quantity = models.IntegerField(default=0)
    produced_quantity = models.IntegerField(default=0)
    image_data = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to="product_colors/", null=True, blank=True)

    class Meta:
        db_table = "product_colors"
        verbose_name = "商品カラー"
        verbose_name_plural = "商品カラー一覧"

    def __str__(self):
        return f"{self.product.name} - {self.color_name}"


class ProductPrice(models.Model):
    color = models.ForeignKey(ProductColor, on_delete=models.CASCADE, related_name="prices", db_column="color_id")
    platform = models.CharField(max_length=100)
    currency = models.CharField(max_length=20)
    price = models.FloatField(default=0.0)

    class Meta:
        db_table = "product_prices"
        verbose_name = "商品価格"
        verbose_name_plural = "商品価格一覧"


class ProductPart(models.Model):
    color = models.ForeignKey(ProductColor, on_delete=models.CASCADE, related_name="parts", db_column="color_id")
    part_name = models.CharField(max_length=255)
    quantity = models.IntegerField(default=1)

    class Meta:
        db_table = "product_parts"
        verbose_name = "商品パーツ"
        verbose_name_plural = "商品パーツ一覧"


class CostItem(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="costs", db_column="product_id")
    item_name = models.CharField(max_length=255)
    actual_cost = models.FloatField(default=0.0)
    supplier = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    unit_price = models.FloatField(default=0.0)
    quantity = models.FloatField(default=1.0)
    remarks = models.TextField(default="", blank=True)
    unit = models.CharField(max_length=50, default="", blank=True)
    order_no = models.CharField(max_length=255, null=True, blank=True)
    url = models.URLField(max_length=1000, null=True, blank=True)
    currency = models.CharField(max_length=20, default="CNY")
    original_amount = models.FloatField(null=True, blank=True)
    actual_qty = models.FloatField(default=0.0, null=True, blank=True)
    actual_unit_price = models.FloatField(default=0.0, null=True, blank=True)
    is_budget = models.BooleanField(default=False)
    finance_record_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "cost_items"
        verbose_name = "原価項目"
        verbose_name_plural = "原価項目一覧"

    def __str__(self):
        return f"{self.item_name} ({self.product.name})"


class SalesPlatform(models.Model):
    code = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    currency = models.CharField(max_length=20, default="CNY")
    fee_rate = models.FloatField(default=0.0)
    fee_fixed = models.FloatField(default=0.0)

    class Meta:
        db_table = "sales_platforms"
        verbose_name = "販売プラットフォーム"
        verbose_name_plural = "販売プラットフォーム一覧"

    def __str__(self):
        return self.name


class MemoNote(models.Model):
    date = models.CharField(max_length=50)
    content = models.TextField(default="", blank=True)
    created_at = models.CharField(max_length=100)

    class Meta:
        db_table = "memo_notes"
        verbose_name = "備忘録"
        verbose_name_plural = "備忘録一覧"


class SystemSetting(models.Model):
    key = models.CharField(max_length=255, primary_key=True, db_index=True)
    value = models.TextField()
    description = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "system_settings"
        verbose_name = "システム設定"
        verbose_name_plural = "システム設定一覧"

    def __str__(self):
        return f"{self.key}: {self.value}"
