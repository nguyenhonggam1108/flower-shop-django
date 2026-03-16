from django.contrib import admin
from .models import AccessoryCategory, AccessoryItem

@admin.register(AccessoryCategory)
class AccessoryCategoryAdmin(admin.ModelAdmin):
    list_display = ('name','slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

@admin.register(AccessoryItem)
class AccessoryItemAdmin(admin.ModelAdmin):
    list_display = ('name','category','stock','sku')
    list_filter = ('category',)
    search_fields = ('name','sku')
    prepopulated_fields = {'slug': ('name',)}