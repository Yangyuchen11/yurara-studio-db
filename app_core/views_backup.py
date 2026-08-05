# app_core/views_backup.py
import io
import zipfile
import pandas as pd
from datetime import datetime
from django.db import connection, transaction
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser

from app_core.models import (
    Warehouse, Product, ProductColor, ProductPart, ProductPrice,
    CostItem, SalesPlatform, MemoNote, SystemSetting
)
from app_finance.models import FinanceRecord, CompanyBalanceItem
from app_inventory.models import InventoryLog
from app_assets.models import FixedAsset, FixedAssetLog, ConsumableItem, ConsumableLog
from app_sales.models import SalesOrder, SalesOrderItem, OrderRefund, OfflineTemplate, OfflineTemplateItem

TABLES_MAP = [
    ("warehouses.csv", "warehouses"),
    ("products.csv", "products"),
    ("product_colors.csv", "product_colors"),
    ("product_parts.csv", "product_parts"),
    ("product_prices.csv", "product_prices"),
    ("finance_records.csv", "finance_records"),
    ("cost_items.csv", "cost_items"),
    ("inventory_logs.csv", "inventory_logs"),
    ("fixed_assets.csv", "fixed_assets_detail"),
    ("fixed_asset_logs.csv", "fixed_asset_logs"),
    ("consumables.csv", "consumable_items"),
    ("consumable_logs.csv", "consumable_logs"),
    ("company_balance.csv", "company_balance_items"),
    ("sales_orders.csv", "sales_orders"),
    ("sales_order_items.csv", "sales_order_items"),
    ("order_refunds.csv", "order_refunds"),
    ("offline_templates.csv", "offline_templates"),
    ("offline_template_items.csv", "offline_template_items"),
]

class BackupDownloadView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        zip_buffer = io.BytesIO()
        current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        filename = f"yurara-db-backup_{current_time}.zip"

        try:
            with connection.cursor() as cursor:
                with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for csv_name, table_name in TABLES_MAP:
                        try:
                            df = pd.read_sql(f"SELECT * FROM {table_name}", connection)
                            zf.writestr(csv_name, df.to_csv(index=False).encode("utf-8-sig"))
                        except Exception as e:
                            print(f"[Backup] Failed exporting {table_name}: {e}")

            response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            return Response({"error": f"Failed generating backup: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BackupRestoreView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        if 'file' not in request.FILES:
            return Response({"error": "No backup file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = request.FILES['file']
        try:
            zip_bytes = io.BytesIO(uploaded_file.read())
            with transaction.atomic():
                with connection.cursor() as cursor:
                    db_engine = connection.vendor
                    if db_engine == 'postgresql':
                        cursor.execute("SET session_replication_role = 'replica';")
                    elif db_engine == 'sqlite':
                        cursor.execute("PRAGMA foreign_keys = OFF;")

                    with zipfile.ZipFile(zip_bytes) as zf:
                        for csv_name, table_name in TABLES_MAP:
                            if csv_name in zf.namelist():
                                with zf.open(csv_name) as f:
                                    df = pd.read_csv(f, encoding='utf-8-sig')
                                    cursor.execute(f"DELETE FROM {table_name};")
                                    if not df.empty:
                                        # pandas to_sql
                                        df.to_sql(table_name, connection, if_exists='append', index=False)

                    if db_engine == 'postgresql':
                        cursor.execute("SET session_replication_role = 'origin';")
                        for _, table_name in TABLES_MAP:
                            try:
                                cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), coalesce(max(id),0) + 1, false) FROM {table_name};")
                            except Exception:
                                pass
                    elif db_engine == 'sqlite':
                        cursor.execute("PRAGMA foreign_keys = ON;")

            return Response({"message": "Database successfully restored from backup ZIP"})
        except Exception as e:
            return Response({"error": f"Failed restoring backup: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
