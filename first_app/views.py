from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from category.models import Category
from django.views.generic import TemplateView , ListView
from product.models import Product
from accounts.models import Customer


# Create your views here.

class IndexView(TemplateView):
    template_name = "index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] =Category.objects.filter(is_featured=True, is_visible=True)
        return context


class AboutView(TemplateView):
    template_name = "about.html"

class DesignView(TemplateView):
    template_name = "design.html"


# ----DropDown----
class AllFlowerView(ListView):
    model = Product
    template_name = "dropdown/all_flower.html"
    context_object_name = "products"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = {'name': 'Tất cả sản phẩm'}
        return context


class BoHoaTuoiView(TemplateView):
    template_name = "dropdown/bo_hoa_tuoi.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            category = Category.objects.get(name__iexact="Bó hoa tươi")
            products = category.products.all()  # ✅ chính xác cho ManyToMany
        except Category.DoesNotExist:
            category = {'name': 'Bó Hoa Tươi'}
            products = []
        context['category'] = category
        context['products'] = products
        return context


class ChauHoaView(TemplateView):
    template_name = "dropdown/chau_hoa.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            category = Category.objects.get(name__iexact="Chậu hoa")
            products = category.products.all()
        except Category.DoesNotExist:
            category = {'name': 'Chậu Hoa'}
            products = []
        context['category'] = category
        context['products'] = products
        return context



# --- Hoa sáp ---
class HoaSapView(TemplateView):
    template_name = "dropdown/hoa_sap.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            category = Category.objects.get(name__iexact="Hoa sáp")
            products = category.products.all()
        except Category.DoesNotExist:
            category = {'name': 'Hoa Sáp'}
            products = []
        context['category'] = category
        context['products'] = products
        return context


# --- Hoa chia buồn ---
class HoaChiaBuonView(TemplateView):
    template_name = "dropdown/themed_flower/hoa_chia_buon.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            category = Category.objects.get(name__iexact="Hoa chia buồn")
            products = category.products.all()
        except Category.DoesNotExist:
            category = {'name': 'Hoa Chia Buồn'}
            products = []
        context['category'] = category
        context['products'] = products
        return context


# --- Hoa chúc mừng ---
class HoaChucMungView(TemplateView):
    template_name = "dropdown/themed_flower/hoa_chuc_mung.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            category = Category.objects.get(name__iexact="Hoa chúc mừng")
            products = category.products.all()
        except Category.DoesNotExist:
            category = {'name': 'Hoa Chúc Mừng'}
            products = []
        context['category'] = category
        context['products'] = products
        return context


# --- Hoa cưới ---
class HoaCuoiView(TemplateView):
    template_name = "dropdown/themed_flower/hoa_cuoi.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            category = Category.objects.get(name__iexact="Hoa cưới")
            products = category.products.all()
        except Category.DoesNotExist:
            category = {'name': 'Hoa Cưới'}
            products = []
        context['category'] = category
        context['products'] = products
        return context


# --- Hoa sinh nhật ---
class HoaSinhNhatView(TemplateView):
    template_name = "dropdown/themed_flower/hoa_sinh_nhat.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            category = Category.objects.get(name__iexact="Hoa sinh nhật")
            products = category.products.all()
        except Category.DoesNotExist:
            category = {'name': 'Hoa Sinh Nhật'}
            products = []
        context['category'] = category
        context['products'] = products
        return context


# --- Hoa tình yêu ---
class HoaTinhYeuView(TemplateView):
    template_name = "dropdown/themed_flower/hoa_tinh_yeu.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            category = Category.objects.get(name__iexact="Hoa tình yêu")
            products = category.products.all()
        except Category.DoesNotExist:
            category = {'name': 'Hoa Tình Yêu'}
            products = []
        context['category'] = category
        context['products'] = products
        return context