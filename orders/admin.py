# Register your models here.
from django.contrib import admin
from django.utils.html import format_html
from django.conf import settings
from .models import Order, OrderItem, ShippingArea, Coupon

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'phone', 'total_amount', 'shipping_method_display', 'payment_method_display', 'status', 'created_at', 'qr_code_thumbnail')
    list_filter = ('status', 'shipping_method', 'payment_method', 'created_at')
    search_fields = ('full_name', 'phone', 'email')
    readonly_fields = ('qr_code_preview', 'total_amount', 'final_total', 'created_at')
    inlines = [OrderItemInline]

    def shipping_method_display(self, obj):
        return obj.get_shipping_method_display()
    shipping_method_display.short_description = 'Giao hàng'

    def payment_method_display(self, obj):
        return obj.get_payment_method_display()
    payment_method_display.short_description = 'Thanh toán'

    fieldsets = (
        ('Thông tin khách hàng', {
            'fields': ('full_name', 'phone', 'email', 'address', 'shipping_address', 'note')
        }),
        ('Thông tin đơn hàng', {
            'fields': ('total_amount', 'final_total', 'status', 'qr_code_preview', 'created_at', 'shipping_method', 'payment_method')
        }),
    )

    def qr_code_preview(self, obj):
        """Hiển thị ảnh QR trong trang change/form của admin"""
        if not obj or not obj.qr_code:
            return "(Chưa có mã QR)"
        # obj.qr_code là ImageField -> có .url
        try:
            return format_html('<img src="{}" width="120" height="120" />', obj.qr_code.url)
        except Exception:
            # fallback nếu qr_code là chuỗi đường dẫn
            return format_html('<img src="{}{}" width="120" height="120" />', settings.MEDIA_URL, obj.qr_code)

    qr_code_preview.short_description = "Mã QR"

    def qr_code_thumbnail(self, obj):
        """Thumbnail nhỏ cho list_display"""
        if not obj or not obj.qr_code:
            return "-"
        try:
            return format_html('<img src="{}" width="40" height="40" style="object-fit:cover; border-radius:4px;" />', obj.qr_code.url)
        except Exception:
            return format_html('<img src="{}{}" width="40" height="40" style="object-fit:cover; border-radius:4px;" />', settings.MEDIA_URL, obj.qr_code)
    qr_code_thumbnail.short_description = "QR"

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'price')

admin.site.register(ShippingArea)
admin.site.register(Coupon)