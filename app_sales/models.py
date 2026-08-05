from django.db import models

class SalesOrder(models.Model):
    order_no = models.CharField(max_length=255, unique=True, db_index=True)
    order_type = models.CharField(max_length=50, default="线上")
    final_order_no = models.CharField(max_length=255, null=True, blank=True)
    deposit_amount = models.FloatField(default=0.0)
    final_amount = models.FloatField(default=0.0)
    status = models.CharField(max_length=100, default="待发货")
    total_amount = models.FloatField(default=0.0)
    currency = models.CharField(max_length=20, default="CNY")
    platform = models.CharField(max_length=100, null=True, blank=True)
    target_account_name = models.CharField(max_length=255, null=True, blank=True)
    created_date = models.DateField(auto_now_add=True)
    shipped_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    notes = models.TextField(default="", blank=True)
    discount_note = models.TextField(default="", blank=True)

    class Meta:
        db_table = "sales_orders"
        verbose_name = "販売注文"
        verbose_name_plural = "販売注文一覧"

    def __str__(self):
        return f"{self.order_no} ({self.status})"


class SalesOrderItem(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items", db_column="order_id")
    product_name = models.CharField(max_length=255)
    variant = models.CharField(max_length=255, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    unit_price = models.FloatField(default=0.0)
    subtotal = models.FloatField(default=0.0)
    warehouse_id = models.IntegerField(null=True, blank=True, db_column="warehouse_id")

    class Meta:
        db_table = "sales_order_items"
        verbose_name = "注文明細"
        verbose_name_plural = "注文明細一覧"


class OrderRefund(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="refunds", db_column="order_id")
    refund_amount = models.FloatField(default=0.0)
    refund_reason = models.TextField(null=True, blank=True)
    refund_date = models.DateField(auto_now_add=True)
    is_returned = models.BooleanField(default=False)
    returned_quantity = models.IntegerField(default=0)
    is_resend = models.BooleanField(default=False)
    resend_quantity = models.IntegerField(default=0)
    cost_item_id = models.IntegerField(null=True, blank=True, db_column="cost_item_id")

    class Meta:
        db_table = "order_refunds"
        verbose_name = "返金・返品記録"
        verbose_name_plural = "返金・返品記録一覧"


class OfflineTemplate(models.Model):
    name = models.CharField(max_length=255, unique=True, db_index=True)
    code = models.CharField(max_length=255, unique=True, db_index=True)
    currency = models.CharField(max_length=20, default="CNY")
    created_at = models.DateField(auto_now_add=True)
    warehouse_id = models.IntegerField(null=True, blank=True, db_column="warehouse_id")
    platform = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "offline_templates"
        verbose_name = "オフラインテンプレート"
        verbose_name_plural = "オフラインテンプレート一覧"

    def __str__(self):
        return self.name


class OfflineTemplateItem(models.Model):
    template = models.ForeignKey(OfflineTemplate, on_delete=models.CASCADE, related_name="items", db_column="template_id")
    product_name = models.CharField(max_length=255)
    variant = models.CharField(max_length=255, null=True, blank=True)
    preset_price = models.FloatField(default=0.0)
    quantity = models.IntegerField(default=0)
    remaining_quantity = models.IntegerField(default=0)

    class Meta:
        db_table = "offline_template_items"
        verbose_name = "オフラインテンプレート明細"
        verbose_name_plural = "オフラインテンプレート明细一覧"


class PresaleOrderBinding(models.Model):
    deposit_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="bound_finals", db_column="deposit_order_id")
    deposit_order_no = models.CharField(max_length=255, db_index=True)
    final_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="bound_deposits", null=True, blank=True, db_column="final_order_id")
    final_order_no = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default="ACTIVE")

    class Meta:
        db_table = "presale_order_bindings"
        verbose_name = "予約注文紐付け"
        verbose_name_plural = "予約注文紐付け一覧"

