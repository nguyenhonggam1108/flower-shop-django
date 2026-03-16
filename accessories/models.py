from django.db import models
from django.utils.text import slugify

class AccessoryCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)

    class Meta:
        verbose_name = "Danh mục phụ kiện"
        verbose_name_plural = "Các danh mục phụ kiện"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# =========================
# Phụ kiện
# =========================
class AccessoryItem(models.Model):
    category = models.ForeignKey(
        AccessoryCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accessories'
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    stock = models.IntegerField(default=0)  # tồn theo đơn vị (ví dụ cái / bộ)
    sku = models.CharField(max_length=64, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Phụ kiện"
        verbose_name_plural = "Phụ kiện"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

