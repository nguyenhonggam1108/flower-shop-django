import pdfkit
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.urls import reverse
from .models import Order, OrderItem, DeliveryProof
from .forms_admin import OrderStatusForm, DeliveryProofForm
from django.core.paginator import Paginator
from django.db.models import Q
from django.views import View
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff

class OrderAdminListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = Order
    template_name = 'orders/orders_admin_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('user')
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        if q:
            qs = qs.filter(
                Q(full_name__icontains=q) |
                Q(email__icontains=q) |
                Q(phone__icontains=q) |
                Q(id__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['status_choices'] = Order.STATUS_CHOICES
        ctx['selected_status'] = self.request.GET.get('status', '')
        return ctx

class OrderAdminDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = Order
    template_name = 'orders/orders_detail_admin.html'
    context_object_name = 'order'
    pk_url_kwarg = 'order_id'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.object.items.select_related('product').all()
        ctx['status_form'] = OrderStatusForm(instance=self.object)
        ctx['delivery_form'] = DeliveryProofForm()
        ctx['delivery_proofs'] = self.object.delivery_proofs.all()
        return ctx

class OrderStatusUpdateView(LoginRequiredMixin, StaffRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        form = OrderStatusForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, "Cập nhật trạng thái đơn hàng thành công.")
        else:
            messages.error(request, "Dữ liệu không hợp lệ.")
        return redirect(reverse('orders_admin:detail', kwargs={'order_id': order.id}))

class DeliveryProofCreateView(LoginRequiredMixin, StaffRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        # Lấy note chung (nếu muốn gán cho tất cả ảnh cùng 1 note)
        note = request.POST.get('note', '')
        files = request.FILES.getlist('image')
        if not files:
            messages.error(request, "Không có file nào được tải lên.")
            return redirect(reverse('orders_admin:detail', kwargs={'order_id': order.id}))

        for f in files:
            proof = DeliveryProof(order=order, image=f, note=note)
            proof.save()
        messages.success(request, "Đã lưu ảnh giao hàng.")
        return redirect(reverse('orders_admin:detail', kwargs={'order_id': order.id}))


class OrderInvoicePDFView(View):
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        config = pdfkit.configuration(wkhtmltopdf=r"C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe")  # đường dẫn bạn đã xác nhận đúng
        html = render_to_string("orders/order_pdf.html", {"order": order})  # Sử dụng template của bạn
        try:
            pdf = pdfkit.from_string(html, False, configuration=config)
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="HoaDon_KhachHang_{order.id}.pdf"'
            return response
        except Exception as e:
            return HttpResponse(f"Lỗi tạo PDF: {e}", status=500)