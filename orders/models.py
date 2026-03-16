from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
from product.models import Product
from django.urls import reverse
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Chờ xác nhận'),
        ('processing', 'Đang xử lý'),
        ('shipping', 'Đang giao'),
        ('completed', 'Hoàn thành'),
        ('cancelled', 'Đã hủy'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    final_total = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    qr_code = models.ImageField(upload_to='qrcodes/%Y/%m/%d/', blank=True, null=True)
    is_paid = models.BooleanField(default=False)
    delivery_datetime = models.DateTimeField("Ngày giờ nhận hàng", null=True, blank=True)

    SHIPPING_PICKUP = 'PICKUP'
    SHIPPING_DELIVERY = 'DELIVERY'
    SHIPPING_CHOICES = [
        (SHIPPING_PICKUP, 'Nhận tại cửa hàng'),
        (SHIPPING_DELIVERY, 'Giao tận nơi'),
    ]

    PAYMENT_PAYPAL = 'PAYPAL'
    PAYMENT_COD = 'COD'
    PAYMENT_CHOICES = [
        (PAYMENT_PAYPAL, 'PayPal'),
        (PAYMENT_COD, 'Thu tiền mặt (COD)'),
    ]

    shipping_method = models.CharField(
        max_length=20,
        choices=SHIPPING_CHOICES,
        default=SHIPPING_PICKUP,
        verbose_name='Phương thức giao hàng',
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default=PAYMENT_COD,
        verbose_name='Phương thức thanh toán',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Đơn hàng"
        verbose_name_plural = "Các đơn hàng"

    def __str__(self):
        return f"Đơn hàng #{self.id} - {self.full_name or 'Khách'} ({self.get_status_display()})"

    def get_absolute_url(self):
        return reverse('orders:qr_detail', kwargs={'order_id': self.id})

    def generate_qr(self, full_url: str, save_instance: bool = True):
        if not full_url:
            raise ValueError("Bạn phải truyền full_url (ví dụ request.build_absolute_uri(...)) vào generate_qr.")

        # đảm bảo có id để đặt tên file (nếu chưa có)
        if not self.id:
            self.save()

        # tạo ảnh QR trỏ tới full_url
        qr_img = qrcode.make(full_url)
        buffer = BytesIO()
        qr_img.save(buffer, format='PNG')
        buffer.seek(0)

        file_name = f"order_{self.id}.png"
        # dùng ContentFile để lưu file đúng cách
        self.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=save_instance)
        buffer.close()
        # nếu save_instance=False thì caller phải gọi self.save() sau

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Sản phẩm trong đơn hàng"
        verbose_name_plural = "Sản phẩm trong đơn hàng"

    def get_total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product.name} × {self.quantity}"

class DeliveryProof(models.Model):
    order = models.ForeignKey('Order', on_delete=models.CASCADE, related_name='delivery_proofs')
    image = models.ImageField(upload_to='delivery_proofs/%Y/%m/%d/')
    note = models.TextField(blank=True)
    delivered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ảnh giao hàng cho đơn #{self.order.id}"

class ShippingArea(models.Model):
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('city', 'district')
        verbose_name = "Khu vực giao hàng"
        verbose_name_plural = "Các khu vực giao hàng"

    def __str__(self):
        return f"{self.district}, {self.city}"

class Coupon(models.Model):
    code = models.CharField(max_length=20, unique=True)
    description = models.CharField(max_length=255, blank=True)
    discount_type = models.CharField(
        max_length=10,
        choices=[('PERCENT', 'Phần trăm'), ('AMOUNT', 'Giá trị cố định')]
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    free_shipping = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    start_date = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Mã giảm giá"
        verbose_name_plural = "Các mã giảm giá"

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        now = timezone.now()
        return (
                self.active and
                (not self.start_date or self.start_date <= now) and
                (not self.expiry_date or self.expiry_date > now)
        )

    def apply_discount(self, total):
        if self.discount_type == 'PERCENT':
            return total * (1 - self.discount_value / 100)
        elif self.discount_type == 'AMOUNT':
            return total - self.discount_value
        return total