# yurara_project/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from app_core.views import (
    WarehouseViewSet, ProductViewSet, ProductColorViewSet,
    CostItemViewSet, SalesPlatformViewSet, MemoNoteViewSet,
    RatesView, FetchLiveRatesView
)
from app_core.views_backup import BackupDownloadView, BackupRestoreView
from app_finance.views import (
    FinanceRecordViewSet, CompanyBalanceItemViewSet, FinancialSummaryView, FinancialReportView
)
from app_inventory.views import (
    InventoryLogViewSet, InventorySummaryView, ClearWipView
)
from app_sales.views import (
    SalesOrderViewSet, OfflineTemplateViewSet, SalesAnalyticsView
)
from app_assets.views import (
    FixedAssetViewSet, FixedAssetLogViewSet,
    ConsumableItemViewSet, ConsumableLogViewSet
)

router = DefaultRouter()

# app_core
router.register(r'warehouses', WarehouseViewSet, basename='warehouse')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'product-colors', ProductColorViewSet, basename='productcolor')
router.register(r'cost-items', CostItemViewSet, basename='costitem')
router.register(r'platforms', SalesPlatformViewSet, basename='platform')
router.register(r'memos', MemoNoteViewSet, basename='memo')

# app_finance
router.register(r'finance/records', FinanceRecordViewSet, basename='financerecord')
router.register(r'finance/balance-items', CompanyBalanceItemViewSet, basename='balanceitem')

# app_inventory
router.register(r'inventory/logs', InventoryLogViewSet, basename='inventorylog')

# app_sales
router.register(r'sales/orders', SalesOrderViewSet, basename='salesorder')
router.register(r'sales/offline-templates', OfflineTemplateViewSet, basename='offlinetemplate')

# app_assets
router.register(r'assets/fixed', FixedAssetViewSet, basename='fixedasset')
router.register(r'assets/fixed-logs', FixedAssetLogViewSet, basename='fixedassetlog')
router.register(r'assets/consumables', ConsumableItemViewSet, basename='consumableitem')
router.register(r'assets/consumable-logs', ConsumableLogViewSet, basename='consumablelog')

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # JWT Authentication
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # REST API v1
    path('api/v1/', include(router.urls)),
    path('api/v1/rates/', RatesView.as_view(), name='rates'),
    path('api/v1/rates/fetch-live/', FetchLiveRatesView.as_view(), name='rates_fetch_live'),
    path('api/v1/finance/summary/', FinancialSummaryView.as_view(), name='financial_summary'),
    path('api/v1/finance/report-data/', FinancialReportView.as_view(), name='financial_report'),
    path('api/v1/inventory/summary/', InventorySummaryView.as_view(), name='inventory_summary'),
    path('api/v1/inventory/clear-wip/', ClearWipView.as_view(), name='inventory_clear_wip'),
    path('api/v1/sales/analytics/', SalesAnalyticsView.as_view(), name='sales_analytics'),
    path('api/v1/backup/download/', BackupDownloadView.as_view(), name='backup_download'),
    path('api/v1/backup/restore/', BackupRestoreView.as_view(), name='backup_restore'),
]

if settings.DEBUG or True:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


