from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone
from decimal import Decimal

User = get_user_model()


class FlowerCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)

    class Meta:
        verbose_name = "Danh mục hoa lẻ"
        verbose_name_plural = "Các danh mục hoa lẻ"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Supplier(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    def __str__(self):
        return self.name


# class FlowerCategory(models.Model):
#     name = models.CharField(max_length=120, unique=True)
#     slug = models.SlugField(max_length=140, unique=True, blank=True)
#
#     class Meta:
#         verbose_name = "Danh mục hoa"
#         verbose_name_plural = "Các danh mục hoa"
#
#     def save(self, *args, **kwargs):
#         if not self.slug:
#             self.slug = slugify(self.name)
#         super().save(*args, **kwargs)
#
#     def __str__(self):
#         return self.name


# =========================
# Hoa
# =========================
class FlowerItem(models.Model):
    category = models.ForeignKey(
        FlowerCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='flowers'
    )
    name = models.CharField(max_length=100)
    unit = models.CharField(max_length=20, default='bó')  # nhập theo bó
    stock_bunches = models.IntegerField(default=0)  # tồn theo bó
    stems_per_bunch = models.IntegerField(default=10)  # số cành/bó

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(stock_bunches__gte=0), name='stock_bunches_non_negative'),
        ]
        verbose_name = "Hoa"
        verbose_name_plural = "Các loại hoa"

    def __str__(self):
        return self.name


class Inventory(models.Model):
    TYPE_CHOICES = [
        ('IMPORT', 'Nhập hàng'),
        ('EXPORT', 'Xuất hàng'),
    ]

    flower = models.ForeignKey(FlowerItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    note = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    def __str__(self):
        return f"{self.flower.name} - {self.type} ({self.quantity})"


class GoodsReceipt(models.Model):
    supplier = models.ForeignKey('inventory.Supplier', on_delete=models.PROTECT, related_name='receipts')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    invoice_file = models.FileField(upload_to='receipts/invoices/%Y/%m/%d/', null=True, blank=True)
    note = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Phiếu nhập"
        verbose_name_plural = "Phiếu nhập"

    def __str__(self):
        return f"PN#{self.id} - {self.supplier.name if self.supplier else 'NCC'} - {self.created_at.date()}"

class GoodsReceiptItem(models.Model):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='items')

    # Generic relation to any item model (FlowerItem or AccessoryItem ...)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, null=True, blank=True)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    quantity_bunch = models.PositiveIntegerField(default=1)  # số bó nhập / đơn vị đối với phụ kiện
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)  # giá / bó hoặc giá / cái
    total_price = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Dòng phiếu nhập"
        verbose_name_plural = "Dòng phiếu nhập"

    def save(self, *args, **kwargs):
        qty = Decimal(self.quantity_bunch or 0)
        price = Decimal(self.unit_price or 0)
        self.total_price = (price * qty)
        super().save(*args, **kwargs)

    def get_model_display(self):
        if self.content_type:
            return f"{self.content_type.app_label}.{self.content_type.model}"
        return "N/A"

class Material(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=20, default="bó")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.code} - {self.name}"


class MaterialRequest(models.Model):
    STATUS = [
        ('open', 'Đang mở'),
        ('offered', 'Đã có nhà cung cấp gửi đề nghị'),
        ('approved', 'Đã duyệt'),
        ('completed', 'Hoàn thành'),
        ('cancelled', 'Đã hủy'),
    ]
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='material_requests')
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    # new field: ngày mong muốn nhận hàng
    desired_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='open')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Phiếu yêu cầu #{self.id}"


class RequestItem(models.Model):
    request = models.ForeignKey(MaterialRequest, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.material} - {self.quantity}"