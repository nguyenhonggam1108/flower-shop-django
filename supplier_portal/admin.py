from django.contrib import admin
from .models import SupplierProfile, Material, StockInItem, StockIn, SupplierOffer, MaterialRequest, RequestItem, \
    StockOut, StockOutItem, SupplierInvoice


@admin.register(SupplierProfile)
class SupplierProfileAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'user', 'phone', 'approved')
    search_fields = ('company_name', 'user__email', 'user__username', 'phone')
    list_filter = ('approved',)

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'get_unit_display', 'quantity')
    list_filter = ('unit',)
    search_fields = ('code', 'name')

# đăng ký các model khác nếu cần
admin.site.register(MaterialRequest)
admin.site.register(RequestItem)
admin.site.register(SupplierOffer)
admin.site.register(SupplierInvoice)
admin.site.register(StockIn)
admin.site.register(StockInItem)
admin.site.register(StockOut)
admin.site.register(StockOutItem)