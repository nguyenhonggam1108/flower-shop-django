import os
from django.utils import timezone
from inventory.models import GoodsReceipt, GoodsReceiptItem, Supplier as InventorySupplier
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import authenticate, login, get_user_model
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic import FormView, ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.apps import apps
import json
from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse, HttpResponseBadRequest
from django.forms import modelform_factory, inlineformset_factory
from django.http import HttpResponse
from django.core.files import File
import pdfkit
from inventory.models import Inventory, FlowerItem
from accessories.models import AccessoryItem
from .forms import (
    MaterialRequestForm,
    RequestItemFormSet,
    SupplierRegistrationForm,
    OfferForm,
    StockInItemFormSet,
    StockOutItemFormSet, SupplierInvoiceForm, InvoiceItemFormSet, SupplierInvoiceItemFormSet, StockOutForm,
    SupplierInvoiceItemForm,
)
from .models import (
    SupplierProfile,
    MaterialRequest,
    SupplierOffer,
    Material,
    StockIn,
    StockOut,
    RequestItem, SupplierInvoice, SupplierInvoiceItem, StockInItem,
)

User = get_user_model()

class SupplierOnlyMixin:
    """Chỉ cho phép Supplier truy cập"""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')

        if not hasattr(request.user, 'supplier_profile'):
            return redirect('index')   # hoặc trang báo lỗi riêng

        return super().dispatch(request, *args, **kwargs)

class StaffOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return getattr(self.request.user, "is_staff", False)

class StaffRequestListView(LoginRequiredMixin, StaffOnlyMixin, ListView):
    model = MaterialRequest
    template_name = "supplier_portal/request_list.html"
    context_object_name = "requests"

    def get_queryset(self):
        # đếm số offer đang 'pending' mỗi request để hiển thị badge
        qs = MaterialRequest.objects.annotate(
            pending_offers_count=Count('offers', filter=Q(offers__status='pending'))
        ).order_by('-created_at')
        return qs

class SupplierRegisterView(FormView):
    template_name = "supplier_portal/register.html"
    form_class = SupplierRegistrationForm
    success_url = reverse_lazy("supplier_portal:supplier_request_list")

    def form_valid(self, form):
        user = form.save()
        password = form.cleaned_data.get("password1")
        user_auth = authenticate(self.request, username=user.username, password=password)
        if user_auth is not None:
            login(self.request, user_auth)
            messages.success(self.request, "Đăng ký và đăng nhập thành công.")
            return redirect(self.get_success_url())
        return super().form_valid(form)

class SupplierRequestListView(LoginRequiredMixin, SupplierOnlyMixin, ListView):
    model = MaterialRequest
    template_name = "supplier_portal/supplier_request_list.html"
    context_object_name = "requests"

    def get_queryset(self):
        supplier = getattr(self.request.user, 'supplier_profile', None)
        if not supplier:
            return MaterialRequest.objects.none()
        # Lấy tất cả phiếu đang mở (không exclude phiếu đã accept NCC khác)
        return MaterialRequest.objects.filter(status="open")

class SendOfferView(LoginRequiredMixin, View):
    def post(self, request, req_id):
        # Lấy phiếu và NCC
        req = get_object_or_404(MaterialRequest, id=req_id)
        supplier_profile = getattr(request.user, "supplier_profile", None)

        if not supplier_profile:
            messages.error(request, "Chỉ nhà cung cấp đã đăng ký mới được gửi đề nghị.")
            return redirect('supplier_portal:supplier_request_list')

        # GỬI ĐỀ NGHỊ: tạo/ghi nhận offer
        message_text = request.POST.get("message", "Nhà cung cấp gửi đề nghị tới shop").strip()
        offer, created = SupplierOffer.objects.update_or_create(
            supplier=supplier_profile,
            request=req,
            defaults={"message": message_text, "status": "pending"}
        )

        # Gửi MAIL về SHOP alert mới
        try:
            shop_email = getattr(settings, "SHOP_EMAIL", None)
            if shop_email:
                subject = f"Nhà cung cấp gửi đề nghị báo giá cho Phiếu #{req.id}"
                message = f"Nhà cung cấp {supplier_profile.company_name} đã gửi đề nghị cho phiếu #{req.id}\n\nNội dung: {message_text}"
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [shop_email],
                    fail_silently=True
                )
        except Exception as e:
            print(f"Lỗi gửi mail về shop: {e}")

        messages.success(request, "Đã gửi đề nghị. Shop sẽ duyệt và phản hồi sau!")
        return redirect('supplier_portal:supplier_my_requests')

# Duyệt offer
class ApproveOfferView(LoginRequiredMixin, StaffOnlyMixin, View):
    def post(self, request, offer_id):
        offer = get_object_or_404(SupplierOffer, id=offer_id)
        req = offer.request

        offer.status = "accepted"
        offer.save()
        # Update phiếu trạng thái approved (tuỳ business)
        req.status = "approved"
        req.save()

        # Gửi mail tới NHÀ CUNG CẤP
        try:
            send_mail(
                subject=f"ĐỀ NGHỊ từ nhà cung cấp đã ĐƯỢC SHOP CHẤP NHẬN",
                message=f"Kính gửi {offer.supplier.company_name}, đề nghị cho phiếu #{req.id} đã được chấp nhận.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[offer.supplier.user.email],
                fail_silently=True
            )
        except Exception as e:
            print(f"Lỗi gửi mail tới NCC: {e}")

        messages.success(request, "Đã duyệt offer, thông báo đã gửi mail tới NCC.")
        return redirect('supplier_portal:request_detail', req.id)

# Từ chối offer
class RejectOfferView(LoginRequiredMixin, StaffOnlyMixin, View):
    def post(self, request, offer_id):
        offer = get_object_or_404(SupplierOffer, id=offer_id)
        req = offer.request

        offer.status = "rejected"
        offer.save()
        req.status = "open"  # hoặc giữ nguyên status phiếu nếu business là shop luôn mở cho ncc khác

        try:
            send_mail(
                subject=f"ĐỀ NGHỊ của nhà cung cấp ĐÃ BỊ TỪ CHỐI",
                message=f"Kính gửi {offer.supplier.company_name}, đề nghị của bạn cho phiếu #{req.id} đã bị shop từ chối.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[offer.supplier.user.email],
                fail_silently=True
            )
        except Exception as e:
            print(f"Lỗi gửi mail tới NCC bị từ chối: {e}")

        messages.success(request, "Đã từ chối offer, thông báo đã gửi mail tới NCC.")
        return redirect('supplier_portal:request_detail', req.id)

class CompleteRequestView(LoginRequiredMixin, StaffOnlyMixin, View):
    def post(self, request, req_id):
        req = get_object_or_404(MaterialRequest, id=req_id)
        # nếu đã có invoice gần nhất, cập nhật theo invoice items
        last_invoice = req.invoices.order_by('-created_at').first()
        if last_invoice:
            for it in last_invoice.items.all():
                mat = it.material
                mat.quantity += it.received_qty
                mat.save()
        else:
            for item in req.items.all():
                mat = item.material
                mat.quantity += item.quantity
                mat.save()
        req.status = "completed"
        req.save()
        messages.success(request, "Đã cập nhật tồn kho và hoàn thành phiếu yêu cầu.")
        return redirect('supplier_portal:request_detail', req.id)

class StockInCreateView(LoginRequiredMixin, StaffOnlyMixin, CreateView):
    model = StockIn
    fields = ('supplier', 'note')
    template_name = 'supplier_portal/stockin_form.html'
    success_url = reverse_lazy('stockin_list')

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        formset = StockInItemFormSet()
        return render(request, self.template_name, {'form': form, 'formset': formset})

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        formset = StockInItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            stockin = form.save(commit=False)
            stockin.created_by = request.user
            stockin.save()
            formset.instance = stockin
            formset.save()
            for item in stockin.items.all():
                mat = item.material
                mat.quantity += item.quantity
                mat.save()
            messages.success(request, "Đã tạo phiếu nhập và cập nhật tồn kho.")
            return redirect(self.success_url)
        return render(request, self.template_name, {'form': form, 'formset': formset})

class StockOutCreateView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_staff

    def get(self, request):
        form = StockOutForm()
        formset = StockOutItemFormSet()
        return render(request, "inventory/stockout_form.html", {
            "form": form,
            "formset": formset
        })

    def post(self, request):
        form = StockOutForm(request.POST)
        formset = StockOutItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            stockout = form.save(commit=False)
            stockout.created_by = request.user
            stockout.save()
            formset.instance = stockout
            formset.save()

            for item in stockout.items.all():
                # Kiểm tra đủ tồn kho
                if item.quantity > item.material.quantity:
                    messages.error(request, f"Không đủ tồn kho cho {item.material.name}")
                    stockout.delete()
                    return redirect("supplier_portal:stockout_create")

                # 1. TRỪ tồn kho Material (gốc)
                item.material.quantity = item.material.quantity - item.quantity
                item.material.save()

                # 2. Nếu là hoa/phụ kiện thực tế, trừ tiếp và lưu Inventory
                updated = False
                # Trừ hoa lẻ nếu có liên kết tên
                try:
                    flower = FlowerItem.objects.get(name=item.material.name)
                    flower.stock_bunches = (flower.stock_bunches or 0) - item.quantity
                    flower.save()
                    Inventory.objects.create(
                        flower=flower,
                        quantity=item.quantity,
                        type='EXPORT',
                        date=timezone.now(),
                        staff=request.user,
                        note=f"Xuất từ phiếu xuất #{stockout.id}",
                        unit_price=None,
                        total_value=None,
                    )
                    updated = True
                except FlowerItem.DoesNotExist:
                    pass

                # Nếu phụ kiện, trừ tiếp & lưu lại
                if not updated:
                    try:
                        accessory = AccessoryItem.objects.get(name=item.material.name)
                        accessory.stock = (accessory.stock or 0) - item.quantity
                        accessory.save()
                        # Nếu muốn, có thể tạo record vào bảng Inventory riêng cho phụ kiện
                    except AccessoryItem.DoesNotExist:
                        pass

            messages.success(request, f"Đã tạo phiếu xuất kho #{stockout.id}")
            return redirect("supplier_portal:stockout_detail", pk=stockout.id)
        return render(request, "inventory/stockout_form.html", {
            "form": form,
            "formset": formset
        })

class StockOutDetailView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, pk):
        stockout = get_object_or_404(StockOut, pk=pk)
        return render(request, "inventory/stockout_detail.html", {'stockout': stockout})

class RequestCreateView(LoginRequiredMixin, StaffOnlyMixin, View):
    template_name = "supplier_portal/request_create.html"

    @staticmethod
    def _build_materials_json_and_categories():
        """
        Build materials_by_cat mapping where option values are keys like 'flower-<id>' or 'acc-<id>'.
        Returns (materials_json_string, categories_list)
        """
        materials_by_cat = {}
        categories = []

        # Try to use inventory/accessories apps
        try:
            FlowerCategory = apps.get_model('inventory', 'FlowerCategory')
            FlowerItem = apps.get_model('inventory', 'FlowerItem')
            AccessoryCategory = apps.get_model('accessories', 'AccessoryCategory')
            AccessoryItem = apps.get_model('accessories', 'AccessoryItem')

            # Add all flower categories (items may be empty)
            for cat in FlowerCategory.objects.all():
                key = f"flower-{cat.id}"
                items = []
                for fi in FlowerItem.objects.filter(category=cat):
                    mat_obj, _ = Material.objects.get_or_create(
                        name=fi.name,
                        defaults={'code': f'flower-{fi.id}', 'unit': getattr(fi, 'unit', 'bó')}
                    )
                    items.append({
                        'id': mat_obj.id,
                        'name': mat_obj.name,
                        'unit': mat_obj.get_unit_display() if hasattr(mat_obj, 'get_unit_display') else getattr(mat_obj, 'unit', '')
                    })
                materials_by_cat[key] = items
                categories.append((key, f"Hoa - {cat.name}"))

            # Add all accessory categories (items may be empty)
            for acc_cat in AccessoryCategory.objects.all():
                key = f"acc-{acc_cat.id}"
                items = []
                for ai in AccessoryItem.objects.filter(category=acc_cat):
                    mat_obj, _ = Material.objects.get_or_create(
                        name=ai.name,
                        defaults={'code': f'acc-{ai.id}', 'unit': getattr(ai, 'unit', '') or 'cái'}
                    )
                    items.append({
                        'id': mat_obj.id,
                        'name': mat_obj.name,
                        'unit': mat_obj.get_unit_display() if hasattr(mat_obj, 'get_unit_display') else getattr(mat_obj, 'unit', '')
                    })
                materials_by_cat[key] = items
                categories.append((key, f"Phụ kiện - {acc_cat.name}"))

        except LookupError:
            # Fallback: use Material model grouping (if inventory apps are absent)
            mats = Material.objects.all().order_by('name')
            if mats.exists():
                seen = {}
                for m in mats:
                    cat_key = getattr(m, 'category_key', None) or getattr(m, 'category', None) or 'all'
                    label = str(cat_key)
                    seen[cat_key] = label
                    materials_by_cat.setdefault(cat_key, []).append({
                        'id': m.id,
                        'name': m.name,
                        'unit': m.get_unit_display() if hasattr(m, 'get_unit_display') else getattr(m, 'unit', '')
                    })
                for k, lbl in seen.items():
                    categories.append((k, lbl))

        return json.dumps(materials_by_cat), categories

    def get(self, request, *args, **kwargs):
        materials_json, combined_categories = self._build_materials_json_and_categories()
        form = MaterialRequestForm()
        formset = RequestItemFormSet(form_kwargs={'categories': combined_categories})
        recent_requests = MaterialRequest.objects.order_by('-created_at')[:20]
        return render(request, self.template_name, {
            'form': form,
            'formset': formset,
            'recent_requests': recent_requests,
            'materials_json': materials_json,
            'combined_categories': combined_categories,
        })

    def post(self, request, *args, **kwargs):
        materials_json, combined_categories = self._build_materials_json_and_categories()
        form = MaterialRequestForm(request.POST)
        formset = RequestItemFormSet(request.POST, form_kwargs={'categories': combined_categories})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                mr = form.save(commit=False)
                mr.created_by = request.user
                if hasattr(mr, 'status'):
                    mr.status = 'open'
                mr.save()
                formset.instance = mr
                formset.save()
                messages.success(request, "Tạo phiếu thành công.")
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    recent_requests = MaterialRequest.objects.order_by('-created_at')[:20]
                    return render(request, self.template_name, {
                        'form': MaterialRequestForm(),
                        'formset': RequestItemFormSet(form_kwargs={'categories': combined_categories}),
                        'recent_requests': recent_requests,
                        'materials_json': materials_json,
                        'combined_categories': combined_categories,
                    })
                return redirect('supplier_portal:request_create')

        recent_requests = MaterialRequest.objects.order_by('-created_at')[:20]
        return render(request, self.template_name, {
            'form': form,
            'formset': formset,
            'recent_requests': recent_requests,
            'materials_json': materials_json,
            'combined_categories': combined_categories,
        })

class RequestDetailView(LoginRequiredMixin, DetailView):
    model = MaterialRequest
    template_name = "supplier_portal/request_detail.html"
    context_object_name = "request_obj"

    def dispatch(self, request, *args, **kwargs):
        # allow only staff or supplier
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not (request.user.is_staff or hasattr(request.user, "supplier_profile")):
            return redirect('supplier_portal:supplier_request_list')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # safe supplier retrieval
        supplier = getattr(self.request.user, 'supplier_profile', None)
        context['is_staff'] = self.request.user.is_staff
        context['is_supplier'] = supplier is not None

        # nếu là supplier thì lấy offer của họ (nếu có)
        if supplier:
            context['my_offer'] = self.object.offers.filter(supplier=supplier).first()
        else:
            context['my_offer'] = None

        return context

class SupplierProfileDetailView(LoginRequiredMixin, SupplierOnlyMixin, DetailView):
    model = SupplierProfile
    template_name = "supplier_portal/supplier_profile_detail.html"
    context_object_name = "supplier_profile"

    def get_object(self, queryset=None):
        return self.request.user.supplier_profile

# AJAX endpoint: return materials for a given category key
@login_required
def materials_by_category(request):
    cat_key = request.GET.get('category')
    if not cat_key:
        return HttpResponseBadRequest("Missing 'category' parameter")
    materials_json, _ = RequestCreateView._build_materials_json_and_categories()
    try:
        materials_map = json.loads(materials_json)
    except Exception:
        materials_map = {}
    items = materials_map.get(cat_key, [])
    return JsonResponse({'items': items})


class SendRequestNotificationView(View):
    def post(self, request, pk):
        # 1. Lấy phiếu yêu cầu
        mr = get_object_or_404(MaterialRequest, pk=pk)

        # 2. Lấy SupplierProfile
        supplier_profile = getattr(request.user, "supplier_profile", None)
        if not supplier_profile:
            messages.error(request, "Chỉ nhà cung cấp đã đăng ký mới được gửi đề nghị.")
            return redirect('supplier_portal:supplier_request_list')

        # 3. Tạo SupplierOffer nếu chưa có
        offer, created = SupplierOffer.objects.get_or_create(
            supplier=supplier_profile,
            request=mr,
            defaults={"message": "Vui Lòng Đợi Phản Hồi Từ Cửa Hàng!!!"}
        )

        # 4. Cập nhật trạng thái phiếu yêu cầu
        if mr.status == 'open':
            mr.status = 'offered'
            mr.save()

        # 5. Gửi mail tới shop
        try:
            shop_email = getattr(settings, "SHOP_EMAIL", None)
            if shop_email:
                subject = f"Nhà cung cấp gửi yêu cầu báo giá cho Phiếu #{mr.id}"
                message = f"Nhà cung cấp: {request.user.get_full_name() or request.user.username}\n" \
                          f"Đã gửi yêu cầu báo giá cho phiếu #{mr.id}\n\n" \
                          f"Ghi chú: {mr.note}\n"
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [shop_email],
                    fail_silently=True
                )
        except Exception:
            pass

        messages.success(request, f"Đã gửi đề nghị cung cấp (Offer ID: {offer.id}) cho phiếu #{mr.id}")
        return redirect(request.META.get("HTTP_REFERER", "/"))

class SupplierMyRequestsView(LoginRequiredMixin, SupplierOnlyMixin, ListView):
    template_name = "supplier_portal/supplier_my_requests.html"
    context_object_name = "offers"
    def get_queryset(self):
        supplier_profile = self.request.user.supplier_profile
        queryset = SupplierOffer.objects.filter(
            supplier=supplier_profile
        ).exclude(
            request__status='closed'
        ).order_by('-created_at')
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return queryset

class CloseRequestView(LoginRequiredMixin, UserPassesTestMixin, View):

    # Chỉ cho phép staff
    def test_func(self):
        return self.request.user.is_staff

    def post(self, request, pk):
        req = get_object_or_404(MaterialRequest, pk=pk)
        req.status = "closed"
        req.save()
        messages.success(request, "Phiếu đã được đóng và sẽ không hiển thị với nhà cung cấp.")
        return redirect("supplier_portal:request_detail", pk=pk)

class UpdateRequestStatusView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_staff

    def post(self, request, pk):
        req = MaterialRequest.objects.get(pk=pk)
        new_status = request.POST.get("status")

        # nếu giao hàng thất bại → lưu lý do
        if new_status == "delivery_failed":
            req.failure_reason = request.POST.get("failure_reason")
        else:
            req.failure_reason = None  # reset nếu đổi sang trạng thái khác

        req.status = new_status
        req.save()

        messages.success(request, "Đã cập nhật trạng thái phiếu.")
        return redirect("supplier_portal:request_detail", pk=pk)


class CreateInvoiceFromOfferView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, offer_id):
        offer = get_object_or_404(SupplierOffer, id=offer_id)
        req = offer.request
        print(list(req.items.all()))

        invoice = SupplierInvoice(
            request=req,
            offer=offer,
            supplier=offer.supplier,
            created_by=request.user
        )

        form = SupplierInvoiceForm(instance=invoice)

        # Tự động lấy danh sách nguyên liệu từ request
        initial_items = []
        display_rows = []
        for it in req.items.all():
            desired_price = float(it.desired_price or 0)
            received = 0
            for old_inv in req.invoices.all():
                for old_item in old_inv.items.filter(material=it.material):
                    received += old_item.received_qty
            # Tính số lượng còn thiếu so với yêu cầu (nếu đã từng nhập từng phần)
            missing_qty = float(it.quantity) - float(received)
            initial_items.append({
                "material": it.material.id,
                "requested_qty": it.quantity,
                "received_qty": missing_qty,   # Gợi ý nhập số còn thiếu
                "unit_price": desired_price,
            })
            display_rows.append({
                "missing_qty": missing_qty,
                "desired_price": desired_price,
            })
        num_items = len(initial_items) or 1
        SupplierInvoiceItemFormSet = inlineformset_factory(
            SupplierInvoice,
            SupplierInvoiceItem,
            form=SupplierInvoiceItemForm,
            extra=num_items,
            can_delete=False,
        )
        # KHÔNG cần thêm dòng thừa, chỉ hiện các dòng auto từ request!
        formset = SupplierInvoiceItemFormSet(
            instance=invoice,
            initial=initial_items,
            prefix="inv",
            queryset=SupplierInvoiceItem.objects.none()
        )

        supplier_info = {
            "company_name": offer.supplier.company_name,
            "tax_code": offer.supplier.tax_code,
            "address": offer.supplier.address,
            "phone": offer.supplier.phone,
            "email": offer.supplier.user.email if hasattr(offer.supplier.user, "email") else "",
        }

        return render(request, "supplier_portal/invoice_form.html", {
            "form": form,
            "formset": formset,
            "offer": offer,
            "request_obj": req,
            "display_rows": display_rows,
            "supplier_info": supplier_info,
            "vat_percent": form.instance.vat_percent or 10,
        })

    def post(self, request, offer_id):
        offer = get_object_or_404(SupplierOffer, id=offer_id)
        req = offer.request

        # Không tạo instance invoice trước!
        form = SupplierInvoiceForm(request.POST)
        formset = SupplierInvoiceItemFormSet(
            request.POST,
            prefix="inv"
        )

        if form.is_valid() and formset.is_valid():
            # Tạo và gán thông tin cho invoice
            invoice = form.save(commit=False)
            invoice.request = req
            invoice.offer = offer  # KHÔNG ĐƯỢC THIẾU
            invoice.supplier = offer.supplier
            invoice.created_by = request.user
            invoice.save()

            total = 0
            items = formset.save(commit=False)
            for item in items:
                item.invoice = invoice
                item.save()
                total += item.line_total

                # CẬP NHẬT KHO
                mat = item.material
                mat.quantity += item.received_qty
                mat.save()

            invoice.total = total
            invoice.save()

            messages.success(request, "Đã nhập kho & tạo phiếu nhập.")
            return redirect(f"{reverse('supplier_portal:invoice_detail', args=[invoice.id])}?print=1")

        # Nếu form lỗi, render lại FORM NHẬP (invoice_form.html) để sửa. Không render invoice_detail!!!
        display_rows = []
        for f in formset.forms:
            qty = f["requested_qty"].value() if "requested_qty" in f.fields else ""
            rec = f["received_qty"].value() if "received_qty" in f.fields else ""
            price = f["unit_price"].value() if "unit_price" in f.fields else ""
            try:
                qty_v = float(qty)
            except Exception:
                qty_v = 0
            try:
                rec_v = float(rec)
            except Exception:
                rec_v = 0
            try:
                price_v = float(price)
            except Exception:
                price_v = 0
            display_rows.append({
                "missing_qty": qty_v - rec_v if qty else "",
                "item_total": rec_v * price_v if price and rec else ""
            })

        supplier_info = {
            "company_name": offer.supplier.company_name,
            "tax_code": offer.supplier.tax_code,
            "address": offer.supplier.address,
            "phone": offer.supplier.phone,
            "email": offer.supplier.user.email if hasattr(offer.supplier.user, "email") else "",
        }
        # Render lại form nhập kho với dữ liệu và lỗi để người dùng sửa
        return render(request, "supplier_portal/invoice_form.html", {
            "form": form,
            "formset": formset,
            "offer": offer,
            "request_obj": req,
            "display_rows": display_rows,
            "supplier_info": supplier_info,
            "vat_percent": form.instance.vat_percent or 10,
        })

class InvoiceDetailView(LoginRequiredMixin, StaffOnlyMixin, DetailView):
    model = SupplierInvoice
    template_name = 'supplier_portal/invoice_detail.html'
    context_object_name = 'invoice'

class SupplierInvoicePDFView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, invoice_id):
        invoice = get_object_or_404(SupplierInvoice, id=invoice_id)
        # ... sinh PDF như hướng dẫn ...

        # Tạo PDF
        import pdfkit
        import os
        config = pdfkit.configuration(wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe")
        html = render_to_string("supplier_portal/invoice_pdf.html", {"invoice": invoice})

        pdf = pdfkit.from_string(html, False, configuration=config)
        if not pdf:
            return HttpResponse("Không thể tạo PDF", status=500)

        # Lưu file PDF
        filename = f"PNK_{invoice.id}.pdf"
        media_dir = os.path.join(settings.MEDIA_ROOT, "invoices")
        os.makedirs(media_dir, exist_ok=True)
        filepath = os.path.join(media_dir, filename)
        with open(filepath, "wb") as f:
            f.write(pdf)

        # Lưu đường dẫn vào DB (nếu cần)
        invoice.pdf_file = f"invoices/{filename}"
        invoice.save()

        # **Trả về file PDF cho user**
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f"inline; filename={filename}"
        return response     # <<--- Phải có dòng này cuối hàm!

class SupplierDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        supplier = request.user.supplier_profile
        offers = supplier.supplieroffer_set.order_by("-created_at")[:5]
        return render(request, "supplier_portal/dashboard_supplier.html", {"offers": offers})

class SupplierProfileView(LoginRequiredMixin, View):
    def get(self, request):
        profile = request.user.supplier_profile
        return render(request, "supplier_portal/supplier_profile_detail.html", {"profile": profile})

class SupplierInvoiceConfirmView(View):
    def post(self, request, pk):
        invoice = get_object_or_404(SupplierInvoice, pk=pk)
        if invoice.stocked_in:
            return HttpResponse("Phiếu này đã nhập kho!", status=400)

        with transaction.atomic():
            stockin = StockIn.objects.create(
                created_by=request.user,
                supplier=invoice.supplier,
                note=f"Nhập từ phiếu NCC #{invoice.id} - {invoice.supplier}"
            )

            for item in invoice.items.all():
                StockInItem.objects.create(
                    stockin=stockin,
                    material=item.material,
                    quantity=item.received_qty
                )

                material = item.material
                material.quantity = material.quantity + item.received_qty
                material.save()

                updated = False
                # Hoa lẻ
                try:
                    flower = FlowerItem.objects.get(name=material.name)
                    flower.stock_bunches = (flower.stock_bunches or 0) + item.received_qty
                    flower.save()
                    Inventory.objects.create(
                        flower=flower,
                        quantity=item.received_qty,
                        type='IMPORT',
                        date=timezone.now(),
                        staff=request.user,
                        note=f"Nhập từ phiếu NCC #{invoice.id} (StockIn #{stockin.id})",
                        unit_price=item.unit_price,
                        total_value=item.line_total,
                    )
                    updated = True
                except FlowerItem.DoesNotExist:
                    pass

                # Phụ kiện (nếu chưa là hoa lẻ) - chỉ cập nhật tồn kho, KHÔNG tạo Inventory!
                if not updated:
                    try:
                        accessory = AccessoryItem.objects.get(name=material.name)
                        accessory.stock = (accessory.stock or 0) + item.received_qty
                        accessory.save()
                        # Không tạo Inventory ở đây
                    except AccessoryItem.DoesNotExist:
                        pass

            # --- BẮT ĐẦU: TẠO GoodsReceipt/GoodsReceiptItem để đồng bộ inventory ---
            # 1. Mapping Supplier sang inventory
            inv_supplier, _ = InventorySupplier.objects.get_or_create(
                name=invoice.supplier.company_name,
                defaults={
                    'phone': invoice.supplier.phone,
                    'address': invoice.supplier.address,
                    'email': invoice.supplier.user.email if hasattr(invoice.supplier.user, "email") else None
                }
            )
            # 2. Tạo phiếu nhập GoodsReceipt
            goodsreceipt = GoodsReceipt.objects.create(
                supplier=inv_supplier,
                note=f"Nhập từ phiếu NCC #{invoice.id} ({invoice.supplier.company_name})",
                total_amount=invoice.total,
                created_by=request.user
            )
            # 3. Tạo các dòng GoodsReceiptItem
            for item in invoice.items.all():
                ct = ContentType.objects.get_for_model(item.material)
                GoodsReceiptItem.objects.create(
                    receipt=goodsreceipt,
                    content_type=ct,
                    object_id=item.material.id,
                    quantity_bunch=item.received_qty,
                    unit_price=item.unit_price
                )
            # --- KẾT THÚC ĐỒNG BỘ ---

            invoice.stocked_in = True
            invoice.save()

        return redirect('supplier_portal:invoice_detail', pk)