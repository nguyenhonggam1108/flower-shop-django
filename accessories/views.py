from django.shortcuts import render
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.http import JsonResponse
from .models import AccessoryCategory, AccessoryItem

class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff

# danh sách phụ kiện (public / admin)
class AccessoryListView(ListView):
    model = AccessoryItem
    template_name = 'accessories/list.html'
    context_object_name = 'items'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('category')
        q = self.request.GET.get('q')
        cat = self.request.GET.get('category')
        if q:
            qs = qs.filter(name__icontains=q)
        if cat:
            qs = qs.filter(category_id=cat)
        return qs.order_by('-created_at')

class AccessoryDetailView(DetailView):
    model = AccessoryItem
    template_name = 'accessories/detail.html'
    context_object_name = 'item'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

# API nhỏ cho frontend (dùng trong JS)
class AccessoryCategoryListAPI(View):
    def get(self, request):
        qs = AccessoryCategory.objects.order_by('name').values('id', 'name')
        return JsonResponse(list(qs), safe=False)

class AccessoryItemsByCategoryAPI(View):
    def get(self, request, category_id):
        qs = AccessoryItem.objects.filter(category_id=category_id).values('id','name','price','stock','slug')
        return JsonResponse(list(qs), safe=False)

# --- Category CRUD cho staff/admin ---
class AccessoryCategoryListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = AccessoryCategory
    template_name = 'accessories/manage_categories.html'
    context_object_name = 'categories'
    paginate_by = 30
    ordering = ['name']

class AccessoryCategoryCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = AccessoryCategory
    fields = ['name']
    template_name = 'accessories/category_form.html'
    success_url = reverse_lazy('accessories:manage_categories')

class AccessoryCategoryUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = AccessoryCategory
    fields = ['name']
    template_name = 'accessories/category_form.html'
    success_url = reverse_lazy('accessories:manage_categories')

class AccessoryCategoryDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = AccessoryCategory
    template_name = 'accessories/category_confirm_delete.html'
    success_url = reverse_lazy('accessories:manage_categories')