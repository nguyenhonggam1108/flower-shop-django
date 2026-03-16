from django.urls import path
from .views_admin import OrderAdminListView, OrderAdminDetailView, OrderStatusUpdateView, DeliveryProofCreateView, \
    OrderInvoicePDFView

app_name = 'orders_admin'

urlpatterns = [
    path('',OrderAdminListView.as_view(), name='list'),
    path('<int:order_id>/',OrderAdminDetailView.as_view(), name='detail'),
    path('<int:order_id>/update-status/',OrderStatusUpdateView.as_view(), name='update_status'),
    path('<int:order_id>/delivery-proof/',DeliveryProofCreateView.as_view(), name='delivery_proof'),
    path("orders/<int:order_id>/customer_invoice_pdf/", OrderInvoicePDFView.as_view(), name="order_invoice_pdf"),
]