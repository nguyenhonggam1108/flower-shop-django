from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered
from .models import FlowerCategory, Supplier, FlowerItem, Inventory, GoodsReceipt, GoodsReceiptItem
# models related to requests
from .models import MaterialRequest, RequestItem

@admin.register(FlowerCategory)
class FlowerCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}

@admin.register(FlowerItem)
class FlowerItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'stock_bunches')
    list_filter = ('category',)
    search_fields = ('name',)

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone')
    search_fields = ('name', 'email', 'phone')

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('flower', 'quantity', 'type', 'staff', 'date')
    list_filter = ('type', 'date')

class GoodsReceiptItemInline(admin.TabularInline):
    model = GoodsReceiptItem
    extra = 0

@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    inlines = [GoodsReceiptItemInline]
    list_display = ('id','supplier','created_at','total_amount')
    readonly_fields = ('total_amount','created_at')

# --- MaterialRequest admin ---
class RequestItemInline(admin.TabularInline):
    model = RequestItem
    extra = 1

@admin.register(MaterialRequest)
class MaterialRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_by', 'created_at', 'status')
    list_filter = ('status','created_at')
    search_fields = ('created_by__username','created_by__email','note')
    inlines = (RequestItemInline,)

# If RequestItem was registered elsewhere, avoid double registration
try:
    admin.site.register(RequestItem)
except AlreadyRegistered:
    pass