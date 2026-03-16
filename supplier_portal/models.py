from decimal import Decimal

from django.contrib.auth import forms
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

UNIT_CHOICES = [
    ('bo', 'bó'),
    ('canh', 'cành'),
    ('la', 'lá'),
    ('cong', 'cọng'),
    ('nhanh', 'nhánh'),
    ('chiec', 'chiếc'),
    ('cai', 'cái'),
    ('hop', 'hộp'),
    ('khay', 'khay'),
    ('ke', 'kệ'),
    ('tui', 'túi'),
    ('goi', 'gói'),
    ('bich', 'bịch'),
    ('set', 'set'),
    ('bo_set', 'bộ'),
    ('cuon', 'cuộn'),
    ('kg', 'kg'),
    ('g', 'g'),
    ('m', 'm'),
    ('cm', 'cm'),
    ('pallet', 'pallet'),
]
DEFAULT_UNIT = 'bo'  # mặc định 'bó' (bunch)

class Material(models.Model):
    code = models.CharField(max_length=50, unique=True)  # mã (SKU)
    name = models.CharField(max_length=255)
    # thay unit thành choices
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default=DEFAULT_UNIT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        # hiển thị tên + đơn vị dạng label
        unit_label = dict(UNIT_CHOICES).get(self.unit, self.unit)
        return f"{self.code} - {self.name} ({unit_label})"

class MaterialRequest(models.Model):
    STATUS = [
        ('open', 'Đang mở'),
        ('completed', 'Hoàn thành'),
        ('closed', 'Đã tắt / Ngưng xử lý'),
        ('delivery_failed', 'Giao hàng thất bại'),
    ]

    @property
    def has_new_offer(self):
        return self.offers.filter(status='pending').exists()

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS, default='open')
    failure_reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Phiếu yêu cầu #{self.id}"

class RequestItem(models.Model):
    request = models.ForeignKey(MaterialRequest, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)

    # Thêm trường lưu "giá mong muốn" (có thể để trống)
    desired_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Giá mà shop mong muốn nhà cung cấp báo/nhập (ví dụ VNĐ)."
    )

    def __str__(self):
        return f"{self.material} - {self.quantity}"


class SupplierProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='supplier_profile')
    company_name = models.CharField(max_length=255)
    tax_code = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    approved = models.BooleanField(default=True)

    def __str__(self):
        return self.company_name


class SupplierOffer(models.Model):
    OFFER_STATUS = [
        ('pending', 'Chờ duyệt'),
        ('accepted', 'Đã chấp nhận'),
        ('rejected', 'Từ chối'),
    ]
    supplier = models.ForeignKey(SupplierProfile, on_delete=models.CASCADE)
    # Tham chiếu MaterialRequest trong cùng app
    request = models.ForeignKey(MaterialRequest, on_delete=models.CASCADE, related_name='offers')
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=OFFER_STATUS, default='pending')

    class Meta:
        unique_together = ('supplier', 'request')

    def __str__(self):
        return f"Offer #{self.id} - NCC: {self.supplier.company_name}"

# -----------------------
# Phiếu nhập / phiếu xuất
# -----------------------
class StockIn(models.Model):
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)  # nhân viên tạo phiếu nhập
    supplier = models.ForeignKey(SupplierProfile, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"Phiếu nhập #{self.id}"


class StockInItem(models.Model):
    stockin = models.ForeignKey(StockIn, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"Nhập {self.quantity} x {self.material}"


class StockOut(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    note = models.TextField(blank=True)

    def __str__(self):
        return f"PXK #{self.id}"


class StockOutItem(models.Model):
    stockout = models.ForeignKey(
        StockOut,
        on_delete=models.CASCADE,
        related_name="items"
    )
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()


class SupplierInvoice(models.Model):
    request = models.ForeignKey(
        MaterialRequest,
        on_delete=models.CASCADE,
        related_name="invoices",
        null=True,
        blank=True
    )

    offer = models.ForeignKey(
        SupplierOffer,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    supplier = models.ForeignKey(
        SupplierProfile,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    vat_percent = models.PositiveIntegerField(default=10)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    pdf_file = models.FileField(upload_to="invoices/", null=True, blank=True)
    stocked_in = models.BooleanField(default=False)


class SupplierInvoiceItem(models.Model):
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.CASCADE, related_name="items")
    material = models.ForeignKey(Material, on_delete=models.PROTECT)

    requested_qty = models.PositiveIntegerField()
    received_qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def line_total(self):
        return self.received_qty * self.unit_price


