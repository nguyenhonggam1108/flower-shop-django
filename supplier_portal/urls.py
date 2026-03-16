from django.urls import path
from .views import (
    SupplierRegisterView,
    SupplierDashboardView,
    SupplierProfileView,
    SupplierRequestListView,
    SupplierMyRequestsView,
    StaffRequestListView,
    SendOfferView,
    ApproveOfferView,
    RejectOfferView,
    CompleteRequestView,
    RequestCreateView,
    RequestDetailView,
    UpdateRequestStatusView,
    CloseRequestView,
    CreateInvoiceFromOfferView,
    InvoiceDetailView,
    SupplierInvoicePDFView,
    StockInCreateView,
    StockOutCreateView,
    materials_by_category, SendRequestNotificationView, SupplierInvoiceConfirmView, StockOutDetailView,
)
from accounts.views import LogoutView

app_name = "supplier_portal"

urlpatterns = [

    # ===== Supplier Portal (MẶC ĐỊNH) =====
    path("", SupplierDashboardView.as_view(), name="supplier_dashboard"),
    path("profile/", SupplierProfileView.as_view(), name="supplier_profile"),

    # Đăng ký NCC
    path("register/", SupplierRegisterView.as_view(), name="supplier_register"),

    # Supplier xem phiếu shop gửi
    path("my-offers/", SupplierMyRequestsView.as_view(), name="supplier_my_requests"),
    path("send-request/<int:pk>/", SendRequestNotificationView.as_view(), name="send_request_notification"),

    # Supplier xem offer đã gửi
    path("requests/", SupplierRequestListView.as_view(), name="supplier_request_list"),

    # Gửi báo giá
    path("requests/<int:req_id>/offer/", SendOfferView.as_view(), name="supplier_send_offer"),

    # Staff duyệt offer
    path("offer/<int:offer_id>/approve/", ApproveOfferView.as_view(), name="approve_offer"),
    path("offer/<int:offer_id>/reject/", RejectOfferView.as_view(), name="reject_offer"),

    # Phiếu yêu cầu
    path("request/create/", RequestCreateView.as_view(), name="request_create"),
    path("request/<int:pk>/", RequestDetailView.as_view(), name="request_detail"),
    path("request/<int:pk>/update-status/", UpdateRequestStatusView.as_view(), name="update_request_status"),
    path("request/<int:pk>/close/", CloseRequestView.as_view(), name="close_request"),
    path("request/<int:req_id>/complete/", CompleteRequestView.as_view(), name="complete_request"),

    # Hóa đơn
    path("offer/<int:offer_id>/invoice/", CreateInvoiceFromOfferView.as_view(), name="invoice_create"),
    path("invoice/<int:pk>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoice/<int:invoice_id>/pdf/", SupplierInvoicePDFView.as_view(), name="invoice_pdf"),

    # Staff Request List
    path("staff/requests/", StaffRequestListView.as_view(), name="request_list"),

    # Kho
    path("stockin/create/", StockInCreateView.as_view(), name="stockin_create"),
    path('stockout/create/', StockOutCreateView.as_view(), name="stockout_create"),
    path('stockout/<int:pk>/', StockOutDetailView.as_view(), name="stockout_detail"),
    path("ajax/materials-by-category/", materials_by_category, name="materials_by_category"),
    path("offer/<int:offer_id>/invoice/",CreateInvoiceFromOfferView.as_view(),name="invoice_create"),
    path("invoice/<int:invoice_id>/pdf/",SupplierInvoicePDFView.as_view(),name="invoice_pdf"),
    path('supplier/invoice/<int:pk>/confirm/', SupplierInvoiceConfirmView.as_view(), name='invoice_confirm'),
    # Logout
    path("logout/", LogoutView.as_view(), name="logout"),
]
