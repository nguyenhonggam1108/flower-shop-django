from django.urls import path
from . import views
from .views import (
    AccessoryListView,
    AccessoryDetailView,
    AccessoryCategoryListView,
    AccessoryCategoryCreateView,
    AccessoryCategoryUpdateView,
    AccessoryCategoryDeleteView,
    AccessoryCategoryListAPI,
    AccessoryItemsByCategoryAPI,
)

app_name = 'accessories'

urlpatterns = [
    path('', AccessoryListView.as_view(), name='list'),

    # quản lý danh mục (staff/admin) -> đặt trước route slug để không bị bắt nhầm
    path('categories/', AccessoryCategoryListView.as_view(), name='manage_categories'),
    path('categories/add/', AccessoryCategoryCreateView.as_view(), name='category_add'),
    path('categories/<int:pk>/edit/', AccessoryCategoryUpdateView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/', AccessoryCategoryDeleteView.as_view(), name='category_delete'),

    # API hiện có (giữ nguyên)
    path('api/categories/', AccessoryCategoryListAPI.as_view(), name='api_categories'),
    path('api/categories/<int:category_id>/items/', AccessoryItemsByCategoryAPI.as_view(), name='api_items_by_cat'),

    # Chi tiết item (slug-based) -> để cuối cùng
    path('<slug:slug>/', AccessoryDetailView.as_view(), name='detail'),
]