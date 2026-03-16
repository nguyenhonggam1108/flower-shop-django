import json
from datetime import datetime, timedelta

from django.apps import apps
from django.utils import timezone
from django.db.models import Sum, Q
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from product.models import Product
from orders.models import Order
from inventory.models import Inventory
from inventory.models import FlowerItem
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from orders.models import OrderItem
from product.view_admin import ProductAdminRequiredMixin
from django.urls import reverse
from django.contrib import messages
from django.db import transaction
from inventory.forms import MaterialRequestForm, RequestItemFormSet
from inventory.models import MaterialRequest

class DashboardView(ProductAdminRequiredMixin, View):
    def get(self, request):
        user = request.user
        now = timezone.now()

        # -----------------------------
        # 1. Xử lý dữ liệu nhập / xuất kho
        # -----------------------------
        end_date = now
        start_date = end_date - timedelta(days=6)

        records = Inventory.objects.filter(date__date__range=[start_date, end_date])

        import_data = (
            records.filter(type='IMPORT')
            .annotate(day=TruncDay('date'))
            .values('day')
            .annotate(total=Sum('quantity'))
            .order_by('day')
        )
        export_data = (
            records.filter(type='EXPORT')
            .annotate(day=TruncDay('date'))
            .values('day')
            .annotate(total=Sum('quantity'))
            .order_by('day')
        )

        labels = sorted(list(set(
            [d['day'].strftime('%d/%m') for d in import_data] +
            [d['day'].strftime('%d/%m') for d in export_data]
        )))
        import_dict = {d['day'].strftime('%d/%m'): d['total'] for d in import_data}
        export_dict = {d['day'].strftime('%d/%m'): d['total'] for d in export_data}
        import_list = [import_dict.get(label, 0) for label in labels]
        export_list = [export_dict.get(label, 0) for label in labels]

        # -----------------------------
        # 2. Xử lý dữ liệu doanh thu
        # -----------------------------
        if user.is_staff and not user.is_superuser:
            # Staff chỉ xem doanh thu trong ngày
            start_rev = now.date()
            end_rev = now.date()
            orders = Order.objects.filter(
                created_at__date=start_rev
            ).filter(Q(status='completed') | Q(is_paid=True))
        else:
            # Admin được chọn khoảng thời gian
            start_rev = request.GET.get('start_date')
            end_rev = request.GET.get('end_date')
            if not start_rev or not end_rev:
                end_rev = now
                start_rev = end_rev - timedelta(days=6)
            else:
                start_rev = datetime.strptime(start_rev, '%Y-%m-%d')
                end_rev = datetime.strptime(end_rev, '%Y-%m-%d')
            orders = Order.objects.filter(
                created_at__date__range=[start_rev, end_rev]
            ).filter(Q(status='completed') | Q(is_paid=True))

        revenue_data = (
            orders.annotate(day=TruncDay('created_at'))
            .values('day')
            .annotate(total=Sum('final_total'))
            .order_by('day')
        )

        rev_labels = [d['day'].strftime('%d/%m') for d in revenue_data]
        rev_values = [float(d['total'] or 0) for d in revenue_data]

        context = {
            # nhập xuất kho
            'labels': labels,
            'import_data': import_list,
            'export_data': export_list,

            # doanh thu
            'rev_labels': rev_labels,
            'rev_values': rev_values,
            'is_staff_view': user.is_staff and not user.is_superuser,
            'start_rev': start_rev.strftime('%Y-%m-%d') if not isinstance(start_rev, str) else start_rev,
            'end_rev': end_rev.strftime('%Y-%m-%d') if not isinstance(end_rev, str) else end_rev,
        }

        return render(request, 'dashboard/dashboard.html', context)


class RevenueStatsView(ProductAdminRequiredMixin, View):
    def get(self, request):
        today = timezone.now().date()

        # ===== Xác định quyền xem ngày =====
        if request.user.is_staff and not request.user.is_superuser:
            # Staff chỉ xem hôm nay
            start_date = today
            end_date = today
        else:
            # Admin có thể chọn khoảng thời gian
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            if not start_date or not end_date:
                end_date = today
                start_date = end_date - timedelta(days=6)
            else:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        # ===== Lọc đơn hàng =====
        orders = Order.objects.filter(
            created_at__date__range=[start_date, end_date],
            status="completed"
        )

        # ===== TOP 5 SẢN PHẨM BÁN CHẠY =====
        top_products = (
            OrderItem.objects.filter(order__in=orders)
            .values('product__name')
            .annotate(total_qty=Sum('quantity'))
            .order_by('-total_qty')[:5]
        )

        # ===== TOP 5 KHÁCH HÀNG CHI TIÊU NHIỀU =====
        top_customers = (
            orders.values('user__username', 'user__first_name', 'user__last_name')
            .annotate(total_spent=Sum('final_total'))
            .order_by('-total_spent')[:5]
        )

        # ===== KPI DOANH THU =====
        revenue_today = orders.filter(created_at__date=today).aggregate(total=Sum('final_total'))['total'] or 0
        revenue_week = orders.filter(created_at__date__gte=today - timedelta(days=7)).aggregate(total=Sum('final_total'))['total'] or 0
        revenue_month = orders.filter(created_at__month=today.month).aggregate(total=Sum('final_total'))['total'] or 0
        total_orders = orders.count()

        # ===== Doanh thu theo ngày (biểu đồ) =====
        daily_data = (
            orders.annotate(day=TruncDay('created_at'))
            .values('day')
            .annotate(total=Sum('final_total'))
            .order_by('day')
        )

        labels = [d['day'].strftime('%d/%m') for d in daily_data]
        values = [float(d['total']) for d in daily_data]
        revenue_list = [{'date': d['day'].strftime('%d/%m/%Y'), 'total': d['total']} for d in daily_data]

        context = {
            'labels': labels,
            'values': values,
            'revenue_list': revenue_list,
            'revenue_today': revenue_today,
            'revenue_week': revenue_week,
            'revenue_month': revenue_month,
            'total_orders': total_orders,
            'top_products': top_products,
            'top_customers': top_customers,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'is_staff_view': request.user.is_staff and not request.user.is_superuser,  # dùng trong template ẩn form
        }

        return render(request, 'dashboard/revenue_stats.html', context)

class StaffOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        messages.error(self.request, "Bạn không có quyền thực hiện hành động này.")
        return redirect('index')

class MaterialRequestCreateView(LoginRequiredMixin, StaffOnlyMixin, View):

    template_name = "dashboard/request_create.html"

    @staticmethod
    def _build_materials_json_and_categories():

        FlowerCategory = apps.get_model('inventory', 'FlowerCategory')
        FlowerItem = apps.get_model('inventory', 'FlowerItem')
        # sửa 'accessories' nếu app chứa Accessory* có tên khác
        AccessoryCategory = apps.get_model('accessories', 'AccessoryCategory')
        AccessoryItem = apps.get_model('accessories', 'AccessoryItem')

        materials_by_cat = {}
        categories = []

        for cat in FlowerCategory.objects.all():
            key = f"flower-{cat.id}"
            items = list(FlowerItem.objects.filter(category=cat).values('id', 'name'))
            materials_by_cat[key] = items
            categories.append((key, f"Hoa - {cat.name}"))

        for acc_cat in AccessoryCategory.objects.all():
            key = f"acc-{acc_cat.id}"
            items = list(AccessoryItem.objects.filter(category=acc_cat).values('id', 'name'))
            materials_by_cat[key] = items
            categories.append((key, f"Phụ kiện - {acc_cat.name}"))

        return json.dumps(materials_by_cat), categories

    def get(self, request, *args, **kwargs):
        form = MaterialRequestForm()
        formset = RequestItemFormSet()
        materials_json, combined_categories = self._build_materials_json_and_categories()
        return render(request, self.template_name, {
            'form': form,
            'formset': formset,
            'materials_json': materials_json,
            'combined_categories': combined_categories,
        })

    def post(self, request, *args, **kwargs):
        form = MaterialRequestForm(request.POST)
        formset = RequestItemFormSet(request.POST)
        materials_json, combined_categories = self._build_materials_json_and_categories()

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                mr = form.save(commit=False)
                mr.created_by = request.user
                mr.status = 'open'
                mr.save()
                formset.instance = mr
                formset.save()
                messages.success(request, "Tạo phiếu yêu cầu thành công.")
                return redirect(reverse('dashboard:dashboard'))

        # Nếu invalid, render lại form kèm materials_json để JS còn hoạt động
        return render(request, self.template_name, {
            'form': form,
            'formset': formset,
            'materials_json': materials_json,
            'combined_categories': combined_categories,
        })

# class DashboardCouponListView(ListView):
#     model = Coupon
#     template_name = 'dashboard/coupon_list.html'
#     context_object_name = 'coupons'
#     queryset = Coupon.objects.all()