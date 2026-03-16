from django.urls import path
from . import views
from .views import InventoryStatsView

app_name = 'inventory'

urlpatterns = [
    path('', views.InventoryListView.as_view(), name='list'),
    # inventory/urls.py (thêm)
    path('stats/', views.InventoryStatsView.as_view(), name='stats'),
    path('api/stats/inventory-timeseries/', views.InventoryTimeseriesAPI.as_view(), name='api_inventory_timeseries'),
    path('api/stats/top-items/', views.InventoryTopItemsAPI.as_view(), name='api_inventory_top_items'),
    path('receipts/', views.GoodsReceiptListView.as_view(), name='receipts_list'),
    path('receipts/add/', views.GoodsReceiptCreateView.as_view(), name='receipts_add'),
    path('receipts/<int:receipt_id>/', views.GoodsReceiptDetailView.as_view(), name='receipts_detail'),


    # trang quản lý (list tất cả các category từ ALLOWED_CATEGORY_MODELS)
    path('manage-categories/', views.CategoryManagerView.as_view(), name='manage_categories'),
    path('manage-categories/add/', views.CategoryCreateView.as_view(), name='category_add'),
    # dùng app_label + model_name + pk để xác định model khi edit/delete
    path('manage-categories/<str:app_label>/<str:model_name>/<int:pk>/edit/', views.CategoryUpdateView.as_view(),
         name='category_edit'),
    path('manage-categories/<str:app_label>/<str:model_name>/<int:pk>/delete/', views.CategoryDeleteView.as_view(),
         name='category_delete'),
    path('api/categories/', views.FlowerCategoryListAPI.as_view(), name='api_categories'),
    path('api/flowers-by-category/<int:category_id>/', views.FlowersByCategoryAPI.as_view(), name='api_flowers_by_category'),

    path('api/items-by-category/<str:app_label>/<int:category_id>/', views.ItemsByCategoryAPI.as_view(), name='api_items_by_category'),
]