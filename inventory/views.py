import re
from decimal import Decimal, InvalidOperation
import logging
from django.apps import apps as django_apps
from django.core.paginator import Paginator
from django.views.generic import TemplateView
from accessories.models import AccessoryCategory, AccessoryItem
from django.contrib.contenttypes.models import ContentType
from django.forms import modelform_factory
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views import View
from django.views.generic import ListView, DetailView
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from datetime import datetime, timedelta
from .forms import GoodsReceiptForm, GoodsReceiptItemFormSet
from .models import (
    Inventory,
    FlowerCategory,
    FlowerItem,
    Supplier,
    GoodsReceipt,
)
from django.db.models import Sum, Q

from category.models import Category

from supplier_portal.models import StockIn, StockOut

logger = logging.getLogger(__name__)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff


# ---------- Inventory (nhập lẻ / xuất lẻ) ----------
class InventoryListView(LoginRequiredMixin, StaffRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        inventory_qs = Inventory.objects.select_related('flower', 'staff').order_by('-date')
        return render(request, 'inventory/inventory_list.html', {'inventory': inventory_qs})
# quản lý thông kê kho
class InventoryStatsView(LoginRequiredMixin, StaffRequiredMixin, View):
    template_name = 'inventory/inventory_stats.html'
    NOTE_RE = re.compile(r'(?P<app>[\w_]+)\.(?P<model>[\w_]+)\s+id=(?P<id>\d+)', re.IGNORECASE)

    def _parse_note(self, note):
        if not note:
            return None
        m = self.NOTE_RE.search(note)
        if not m:
            return None
        return (m.group('app'), m.group('model'), int(m.group('id')))

    def _read_stock(self, obj):
        if hasattr(obj, 'stock') and getattr(obj, 'stock', None) is not None:
            try:
                return int(getattr(obj, 'stock') or 0)
            except Exception:
                return None
        if hasattr(obj, 'stock_bunches') and getattr(obj, 'stock_bunches', None) is not None:
            try:
                return int(getattr(obj, 'stock_bunches') or 0)
            except Exception:
                return None
        return None

    def get(self, request):
        # date range (last 7 days)
        today = timezone.now().date()
        start_date = today - timedelta(days=6)
        end_date = today

        # read GET filters (category ids)
        flower_cat_id = request.GET.get('flower_cat')  # inventory.FlowerCategory id
        acc_cat_id = request.GET.get('acc_cat')        # accessories.AccessoryCategory id

        # 1) build inventory aggregates mapped by (app, model, id) using note pattern
        inv_qs = Inventory.objects.filter(date__date__range=(start_date, end_date))
        inv_map = {}  # key -> {'imported': x, 'exported': y}
        for rec in inv_qs.values('note', 'quantity', 'type'):
            parsed = self._parse_note(rec.get('note') or '')
            if not parsed:
                continue
            key = parsed
            entry = inv_map.setdefault(key, {'imported': 0, 'exported': 0})
            if rec.get('type') == 'IMPORT':
                entry['imported'] += (rec.get('quantity') or 0)
            else:
                entry['exported'] += (rec.get('quantity') or 0)

        report_flowers = []
        report_accessories = []

        # 2) Flowers (inventory app)
        flower_cats = []
        try:
            FlowerCategoryModel = django_apps.get_model('inventory', 'FlowerCategory')
            flower_cats = list(FlowerCategoryModel.objects.order_by('name').values('id', 'name'))
        except LookupError:
            flower_cats = []

        flowers_qs = FlowerItem.objects.all().select_related('category')
        if flower_cat_id:
            try:
                flowers_qs = flowers_qs.filter(category_id=int(flower_cat_id))
            except Exception:
                pass

        for f in flowers_qs:
            key = ('inventory', f.__class__.__name__, f.id)
            ag = inv_map.get(key, {'imported': 0, 'exported': 0})
            stock = self._read_stock(f)
            if stock is None:
                stock = ag['imported'] - ag['exported']
            report_flowers.append({
                'obj': f,
                'imported': ag['imported'],
                'exported': ag['exported'],
                'stock': stock,
                'low_stock': stock is not None and stock < 5,
            })

        # 3) Accessories (if installed)
        try:
            AccCategory = django_apps.get_model('accessories', 'AccessoryCategory')
            accessory_cats = list(AccCategory.objects.order_by('name').values('id', 'name'))
        except LookupError:
            accessory_cats = []

        AccItem = None
        try:
            AccItem = django_apps.get_model('accessories', 'AccessoryItem')
        except LookupError:
            AccItem = None

        if AccItem:
            acc_qs = AccItem.objects.all().select_related('category')
            if acc_cat_id:
                try:
                    acc_qs = acc_qs.filter(category_id=int(acc_cat_id))
                except Exception:
                    pass

            for a in acc_qs:
                key = ('accessories', a.__class__.__name__, a.id)
                ag = inv_map.get(key, {'imported': 0, 'exported': 0})
                stock = self._read_stock(a)
                if stock is None:
                    stock = ag['imported'] - ag['exported']
                report_accessories.append({
                    'obj': a,
                    'imported': ag['imported'],
                    'exported': ag['exported'],
                    'stock': stock,
                    'low_stock': stock is not None and stock < 5,
                })
        else:
            accessory_cats = []

        # sort by name
        report_flowers = sorted(report_flowers, key=lambda r: getattr(r['obj'], 'name', '').lower() or '')
        report_accessories = sorted(report_accessories, key=lambda r: getattr(r['obj'], 'name', '').lower() or '')

        # 4) Timeseries import/export across Inventory for last 7 days
        daily_data = (
            Inventory.objects
            .filter(date__date__range=(start_date, end_date))
            .annotate(day=TruncDay('date'))
            .values('day', 'type')
            .annotate(total=Sum('quantity'))
            .order_by('day')
        )
        days = []
        import_map = {}
        export_map = {}
        for d in daily_data:
            day_obj = d['day'].date() if hasattr(d['day'], 'date') else d['day']
            label = day_obj.strftime('%Y-%m-%d')
            if label not in days:
                days.append(label)
            if d['type'] == 'IMPORT':
                import_map[label] = d['total'] or 0
            else:
                export_map[label] = d['total'] or 0
        import_list = [import_map.get(l, 0) for l in days]
        export_list = [export_map.get(l, 0) for l in days]

        context = {
            'flower_cats': flower_cats,
            'accessory_cats': accessory_cats,
            'selected_flower_cat': int(flower_cat_id) if flower_cat_id else None,
            'selected_acc_cat': int(acc_cat_id) if acc_cat_id else None,
            'report_flowers': report_flowers,
            'report_accessories': report_accessories,
            'total_stock': sum((r['stock'] or 0) for r in (report_flowers + report_accessories)),
            'labels': [datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m') for d in days] if days else [],
            'import_list': import_list,
            'export_list': export_list,
        }
        goods_receipts = GoodsReceipt.objects.order_by('-created_at')[:20]
        context['goods_receipts'] = goods_receipts
        stockout_list = StockOut.objects.order_by('-created_at')[:20]
        context['stockout_list'] = stockout_list
        return render(request, self.template_name, context)
# API: time series nhập/xuất
class InventoryTimeseriesAPI(LoginRequiredMixin, StaffRequiredMixin, View):

    def get(self, request):
        group = request.GET.get('group', 'day')
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        item_id = request.GET.get('item_id')

        # determine date range
        now = timezone.now()
        try:
            if end_str:
                end = datetime.date.fromisoformat(end_str)
            else:
                end = now.date()
            if start_str:
                start = datetime.date.fromisoformat(start_str)
            else:
                # default: last 7 days
                start = end - datetime.timedelta(days=6)
        except Exception:
            return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

        qs = Inventory.objects.filter(date__date__range=(start, end))
        if item_id:
            # assumes Inventory has foreign key 'flower' pointing to item
            qs = qs.filter(flower_id=item_id)

        # annotate period
        if group == 'week':
            qs = qs.annotate(period=TruncWeek('date'))
        elif group == 'month':
            qs = qs.annotate(period=TruncMonth('date'))
        else:
            qs = qs.annotate(period=TruncDay('date'))

        agg = qs.values('period', 'type').annotate(total=Sum('quantity')).order_by('period')

        # build ordered labels and series
        labels = []
        import_map = {}
        export_map = {}
        for row in agg:
            period = row['period']
            # Trunc functions return datetime-like; normalize to date string
            try:
                label = period.date().isoformat()
            except Exception:
                label = str(period)
            if label not in labels:
                labels.append(label)
            if row['type'] == 'IMPORT':
                import_map[label] = row['total'] or 0
            else:
                export_map[label] = row['total'] or 0

        import_list = [import_map.get(l, 0) for l in labels]
        export_list = [export_map.get(l, 0) for l in labels]

        return JsonResponse({'labels': labels, 'import': import_list, 'export': export_list})

# API: top items by imported/exported quantity
class InventoryTopItemsAPI(LoginRequiredMixin, StaffRequiredMixin, View):
    """
    GET params:
      - n: number of items to return (default 10)
      - start, end (YYYY-MM-DD) optional to limit period
    Returns JSON:
      { top: [{id, name, imported, exported, net}, ...] }
    """
    def get(self, request):
        try:
            n = int(request.GET.get('n', 10))
        except Exception:
            n = 10

        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        try:
            if start_str and end_str:
                start = datetime.date.fromisoformat(start_str)
                end = datetime.date.fromisoformat(end_str)
                qs = Inventory.objects.filter(date__date__range=(start, end))
            else:
                qs = Inventory.objects.all()
        except Exception:
            return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

        # aggregate by flower (assumes Inventory.flower FK -> FlowerItem). If you use generic items, adapt keys.
        annotated = (
            qs.values('flower_id', 'flower__name')
              .annotate(total_import=Sum('quantity', filter=Q(type='IMPORT')),
                        total_export=Sum('quantity', filter=Q(type='EXPORT')))
        )
        # compute net or ordering by imports
        results = []
        for a in annotated:
            imported = a.get('total_import') or 0
            exported = a.get('total_export') or 0
            results.append({
                'id': a.get('flower_id'),
                'name': a.get('flower__name') or '',
                'imported': imported,
                'exported': exported,
                'net': imported - exported,
            })

        # sort by imported desc then by net desc
        results = sorted(results, key=lambda x: (x['imported'], x['net']), reverse=True)[:n]

        return JsonResponse({'top': results})
# ---------- GoodsReceipt (phiếu nhập theo nhà cung cấp) ----------
class GoodsReceiptListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = GoodsReceipt
    template_name = 'inventory/receipt_list.html'
    context_object_name = 'receipts'
    paginate_by = 20
    ordering = ['-created_at']

class GoodsReceiptDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = GoodsReceipt
    template_name = 'inventory/receipt_detail.html'
    context_object_name = 'receipt'
    pk_url_kwarg = 'receipt_id'

class GoodsReceiptCreateView(LoginRequiredMixin, StaffRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        form = GoodsReceiptForm()
        formset = GoodsReceiptItemFormSet()
        return render(request, 'inventory/receipt_form.html', {
            'form': form,
            'formset': formset,
            'empty_form': formset.empty_form,
            'formset_prefix': formset.prefix,
        })

    def post(self, request, *args, **kwargs):
        form = GoodsReceiptForm(request.POST, request.FILES)
        formset = GoodsReceiptItemFormSet(request.POST, request.FILES)
        if not form.is_valid() or not formset.is_valid():
            logger.debug("Receipt form errors: %s", form.errors)
            logger.debug("Receipt formset errors: %s", formset.errors)
            messages.error(request, "Dữ liệu không hợp lệ. Vui lòng kiểm tra các trường.")
            return render(request, 'inventory/receipt_form.html', {
                'form': form,
                'formset': formset,
                'empty_form': formset.empty_form,
                'formset_prefix': formset.prefix,
            })

        try:
            with transaction.atomic():
                receipt = form.save(commit=False)
                receipt.created_by = request.user
                receipt.save()

                total = Decimal('0')
                saved_items = []
                items = formset.save(commit=False)

                # handle deletions flagged in formset
                for obj in formset.deleted_objects:
                    obj.delete()

                # Pair forms and items so we can read hidden inputs per row
                form_item_pairs = []
                form_index = 0
                for form_row in formset.forms:
                    # skip forms marked for deletion
                    if form_row.cleaned_data.get('DELETE', False):
                        continue
                    # the corresponding instance is next from items list in order
                    instance = items[form_index]
                    form_item_pairs.append((form_row, instance))
                    form_index += 1

                for form_row, item in form_item_pairs:
                    # read hidden inputs rendered in template: item_app, item_model, item_id
                    prefix = form_row.prefix  # e.g. items-0
                    item_app = request.POST.get(f"{prefix}-item_app")
                    item_model = request.POST.get(f"{prefix}-item_model")
                    item_obj_id = request.POST.get(f"{prefix}-item_id")

                    if not item_app or not item_model or not item_obj_id:
                        raise ValueError("Thiếu thông tin vật phẩm ở một dòng.")

                    # set generic relation: find content type
                    ct = ContentType.objects.get(app_label=item_app, model=item_model.lower())
                    item.content_type = ct
                    item.object_id = int(item_obj_id)
                    item.receipt = receipt
                    item.save()
                    total += Decimal(item.total_price or 0)
                    saved_items.append(item)

                    # update stock on actual model (lock row)
                    Model = django_apps.get_model(item_app, item_model)
                    target = Model.objects.select_for_update().get(pk=item.object_id)

                    # update fields safely: prefer stock_bunches then stock
                    if hasattr(target, 'stock_bunches'):
                        target.stock_bunches = (target.stock_bunches or 0) + item.quantity_bunch
                    elif hasattr(target, 'stock'):
                        target.stock = (target.stock or 0) + item.quantity_bunch
                    else:
                        logger.warning("Model %s.%s has no stock field.", item_app, item_model)

                    target.save()

                    # 🔥 Tạo Inventory record để thống kê hoạt động nhập kho
                    Inventory.objects.create(
                        flower=target,
                        quantity=item.quantity_bunch,
                        type='IMPORT',
                        note=f"Phiếu nhập #{receipt.id}",
                        staff=request.user,
                        unit_price=item.unit_price,
                        total_value=item.total_price
                    )

                receipt.total_amount = total
                receipt.save()

        except (InvalidOperation, ValueError) as e:
            logger.exception("Lỗi khi tạo phiếu nhập")
            messages.error(request, f"Lỗi khi lưu phiếu: {e}")
            return render(request, 'inventory/receipt_form.html', {
                'form': form,
                'formset': formset,
                'empty_form': formset.empty_form,
                'formset_prefix': formset.prefix,
            })
        except Exception as e:
            logger.exception("Unexpected error saving GoodsReceipt")
            messages.error(request, "Có lỗi xảy ra khi lưu phiếu nhập. Liên hệ admin.")
            return render(request, 'inventory/receipt_form.html', {
                'form': form,
                'formset': formset,
                'empty_form': formset.empty_form,
                'formset_prefix': formset.prefix,
            })

        messages.success(request, "Đã tạo phiếu nhập thành công.")
        return redirect(reverse('inventory:receipts_detail', kwargs={'receipt_id': receipt.id}))

# ---------- API endpoints (class-based) ----------
class FlowerCategoryListAPI(LoginRequiredMixin, StaffRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        qs = FlowerCategory.objects.order_by('name').values('id', 'name', 'slug')
        return JsonResponse(list(qs), safe=False)


class FlowersByCategoryAPI(LoginRequiredMixin, StaffRequiredMixin, View):
    def get(self, request, category_id, *args, **kwargs):
        qs = FlowerItem.objects.filter(category_id=category_id).values('id', 'name', 'stock_bunches', 'price')
        return JsonResponse(list(qs), safe=False)

# Các model category được phép quản lý ở đây (app_label, model_name, label hiển thị)
ALLOWED_CATEGORY_MODELS = [
    ('category', 'Category', 'Danh mục sản phẩm'),
    ('inventory', 'FlowerCategory', 'Danh mục hoa lẻ'),
    ('accessories', 'AccessoryCategory', 'Danh mục phụ kiện'),
]

# ----- Category manager -----
class CategoryManagerView(LoginRequiredMixin, StaffRequiredMixin, View):
    """
    Hiển thị danh sách tất cả category từ nhiều model, filter theo nguồn (app/model) và tìm kiếm theo tên.
    """
    template_name = 'inventory/manage_categories.html'

    def get_allowed_models(self):
        allowed = []
        for app_label, model_name, label in ALLOWED_CATEGORY_MODELS:
            try:
                model = django_apps.get_model(app_label, model_name)
                allowed.append((app_label, model_name, label, model))
            except LookupError:
                # ignore missing models (ví dụ accessories chưa tồn tại)
                continue
        return allowed

    def get(self, request):
        q = request.GET.get('q', '').strip()
        source = request.GET.get('source', '')  # source = "app_label.model_name" hoặc empty = tất cả
        allowed = self.get_allowed_models()
        results = []
        for app_label, model_name, label, model in allowed:
            qs = model.objects.all().order_by('id')
            if source and source != f"{app_label}.{model_name}":
                continue
            if q:
                qs = qs.filter(name__icontains=q)
            for obj in qs:
                results.append({
                    'app_label': app_label,
                    'model_name': model_name,
                    'label': label,
                    'id': obj.pk,
                    'name': getattr(obj, 'name', str(obj)),
                })
        # sort by label->name
        results = sorted(results, key=lambda r: (r['label'], r['name']))
        context = {
            'results': results,
            'allowed': [(f"{a}.{m}", lab) for a,m,lab,_ in allowed],
            'q': q,
            'source': source,
        }
        return render(request, self.template_name, context)

PREFERRED_CATEGORY_FIELDS = ['name', 'slug', 'image', 'is_featured', 'is_visible']

class CategoryCreateView(LoginRequiredMixin, StaffRequiredMixin, View):
    template_name = 'inventory/category_form.html'

    def get(self, request):
        """
        Nếu request có param `app_model` (ví dụ từ select hoặc ?app_model=accessories.AccessoryCategory)
        thì render form tạo cho model đó; nếu không, render màn chọn nguồn (allowed).
        """
        app_model = request.GET.get('app_model') or request.GET.get('app_label_model')
        allowed = [(f"{a}.{m}", label) for a, m, label in ALLOWED_CATEGORY_MODELS if django_apps.is_installed(a)]
        if not app_model:
            return render(request, self.template_name, {'allowed': allowed, 'obj': None})

        # parse app_model = "app_label.model_name"
        if '.' not in app_model:
            messages.error(request, "Nguồn danh mục không hợp lệ.")
            return redirect('inventory:category_add')
        app_label, model_name = app_model.split('.', 1)
        try:
            Model = django_apps.get_model(app_label, model_name)
        except LookupError:
            messages.error(request, "Loại danh mục không tồn tại.")
            return redirect('inventory:category_add')

        # build fields list: lấy những field ưu tiên tồn tại trên model
        fields = [f for f in PREFERRED_CATEGORY_FIELDS if any(fd.name == f for fd in Model._meta.fields)]
        # nếu không có field nào (lạ) thì mặc định 'name'
        if not fields:
            fields = ['name'] if any(fd.name == 'name' for fd in Model._meta.fields) else [Model._meta.fields[0].name]

        Form = modelform_factory(Model, fields=fields)
        form = Form()
        # cho template biết app/model để post về
        return render(request, self.template_name, {
            'form': form,
            'obj': None,
            'allowed': None,
            'app_label': app_label,
            'model_name': model_name,
        })

    def post(self, request):
        # xử lý submit form tạo: template gửi hidden app_label_model or app_label & model_name
        app_model = request.POST.get('app_label_model') or request.POST.get('app_model') or request.POST.get('app_label') and (request.POST.get('app_label') + '.' + request.POST.get('model_name'))
        name = request.POST.get('name', '').strip()
        if not app_model or '.' not in app_model:
            messages.error(request, "Bạn phải chọn nguồn danh mục.")
            return redirect('inventory:category_add')

        app_label, model_name = app_model.split('.', 1)
        try:
            Model = django_apps.get_model(app_label, model_name)
        except LookupError:
            messages.error(request, "Loại danh mục không hợp lệ.")
            return redirect('inventory:category_add')

        # build fields list same as in get
        fields = [f for f in PREFERRED_CATEGORY_FIELDS if any(fd.name == f for fd in Model._meta.fields)]
        if not fields:
            fields = ['name'] if any(fd.name == 'name' for fd in Model._meta.fields) else [Model._meta.fields[0].name]

        Form = modelform_factory(Model, fields=fields)
        form = Form(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Đã tạo danh mục mới.")
            return redirect('inventory:manage_categories')
        # nếu lỗi, show lại form (để user sửa)
        return render(request, self.template_name, {
            'form': form,
            'obj': None,
            'allowed': None,
            'app_label': app_label,
            'model_name': model_name,
        })


class CategoryUpdateView(LoginRequiredMixin, StaffRequiredMixin, View):
    template_name = 'inventory/category_form.html'

    def dispatch(self, request, app_label, model_name, pk, *args, **kwargs):
        try:
            self.model = django_apps.get_model(app_label, model_name)
        except LookupError:
            raise Http404("Model không tồn tại.")
        self.obj = get_object_or_404(self.model, pk=pk)
        return super().dispatch(request, app_label, model_name, pk, *args, **kwargs)

    def _build_fields_for_model(self):
        fields = [f for f in PREFERRED_CATEGORY_FIELDS if any(fd.name == f for fd in self.model._meta.fields)]
        if not fields:
            fields = ['name'] if any(fd.name == 'name' for fd in self.model._meta.fields) else [self.model._meta.fields[0].name]
        return fields

    def get(self, request, app_label, model_name, pk):
        fields = self._build_fields_for_model()
        Form = modelform_factory(self.model, fields=fields)
        form = Form(instance=self.obj)
        return render(request, self.template_name, {'form': form, 'obj': self.obj, 'app_label': app_label, 'model_name': model_name})

    def post(self, request, app_label, model_name, pk):
        fields = self._build_fields_for_model()
        Form = modelform_factory(self.model, fields=fields)
        form = Form(request.POST, request.FILES, instance=self.obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Đã cập nhật danh mục.")
            return redirect('inventory:manage_categories')
        return render(request, self.template_name, {'form': form, 'obj': self.obj, 'app_label': app_label, 'model_name': model_name})
# Replace the existing CategoryDeleteView class with this version
class CategoryDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'inventory/category_confirm_delete.html'

    def test_func(self):
        # vẫn giới hạn xóa cho superuser theo quyết định tạm thời
        return self.request.user.is_active and self.request.user.is_superuser

    def dispatch(self, request, app_label, model_name, pk, *args, **kwargs):
        try:
            self.model = django_apps.get_model(app_label, model_name)
        except LookupError:
            raise Http404("Model không tồn tại.")
        self.obj = get_object_or_404(self.model, pk=pk)
        return super().dispatch(request, app_label, model_name, pk, *args, **kwargs)

    def _collect_related(self):

        related = []
        for rel in self.model._meta.related_objects:
            accessor = rel.get_accessor_name()
            try:
                manager = getattr(self.obj, accessor)
            except Exception:
                continue
            try:
                cnt = manager.count()
            except Exception:
                cnt = 0
            samples = []
            if cnt:
                try:
                    # fetch up to 50 sample instances
                    insts = list(manager.all()[:50])
                    for inst in insts:
                        # prepare safe display values
                        try:
                            display = str(inst)
                        except Exception:
                            display = f"{rel.related_model.__name__} #{getattr(inst, 'pk', '')}"
                        # get url if available and callable
                        url = None
                        if hasattr(inst, 'get_absolute_url'):
                            try:
                                maybe = inst.get_absolute_url
                                url = maybe() if callable(maybe) else maybe
                            except Exception:
                                url = None
                        # field value on related (if exists)
                        field_val = None
                        field_name = getattr(rel.field, 'name', None)
                        if field_name and hasattr(inst, field_name):
                            try:
                                val = getattr(inst, field_name)
                                # avoid callable output for field value
                                if callable(val):
                                    field_val = None
                                else:
                                    field_val = val
                            except Exception:
                                field_val = None
                        samples.append({
                            'display': display,
                            'url': url,
                            'field_value': field_val,
                        })
                except Exception:
                    samples = []
            # human-friendly verbose plural name for related model
            try:
                related_verbose = rel.related_model._meta.verbose_name_plural
            except Exception:
                related_verbose = rel.related_model.__name__ + "s"

            related.append({
                'related_model': rel.related_model,
                'accessor': accessor,
                'count': cnt or 0,
                'samples': samples,
                'can_set_null': getattr(rel.field, 'null', False),
                'field_name_on_related': getattr(rel.field, 'name', ''),
                'related_verbose': related_verbose,
            })
        return related

    def get(self, request, app_label, model_name, pk):
        related = self._collect_related()
        total_related_count = sum(r['count'] for r in related)
        return render(request, self.template_name, {
            'obj': self.obj,
            'related': related,
            'total_related_count': total_related_count,
        })

    def post(self, request, app_label, model_name, pk):
        # kiểm tra lại các liên kết trước khi xóa
        related = self._collect_related()
        # nếu có liên kết mà field không cho NULL -> chặn xóa cho non-superuser
        blocking = []
        for r in related:
            if r['count'] and not r['can_set_null']:
                blocking.append(r)
        if blocking and not request.user.is_superuser:
            messages.error(request, "Không thể xóa: còn bản ghi liên quan. Vui lòng chuyển hoặc xóa các sản phẩm trước.")
            return redirect('inventory:manage_categories')

        # nếu user là superuser: bulk set NULL cho các quan hệ có field.null=True
        for r in related:
            if r['count'] and r['can_set_null']:
                rel_manager = getattr(self.obj, r['accessor'])
                try:
                    kwargs = {r['field_name_on_related']: None}
                    rel_manager.all().update(**kwargs)
                except Exception:
                    messages.error(request, f"Không thể tự động set NULL cho {r['related_verbose']}. Hủy xóa.")
                    return redirect('inventory:manage_categories')

        # cuối cùng xóa object
        try:
            self.obj.delete()
            messages.success(request, "Đã xóa danh mục.")
        except Exception as e:
            messages.error(request, f"Không thể xóa: {e}")
        return redirect('inventory:manage_categories')

# ----- API for dynamic item loading -----
class FlowerCategoryListAPI(LoginRequiredMixin, StaffRequiredMixin, View):
    def get(self, request):
        qs = FlowerCategory.objects.order_by('name').values('id','name')
        return JsonResponse(list(qs), safe=False)


class ItemsByCategoryAPI(LoginRequiredMixin, StaffRequiredMixin, View):
    """
    Generic API: /api/items-by-category/<app_label>/<category_id>/
    - tries to find model 'Accessory' or 'AccessoryItem' under given app_label; returns id,name,stock if found.
    """
    def get(self, request, app_label, category_id):
        # try common accessory model names
        candidates = ['Accessory', 'AccessoryItem', 'Product']  # adjust if your app uses other model names
        for candidate in candidates:
            try:
                model = django_apps.get_model(app_label, candidate)
            except LookupError:
                continue
            # assume model has category_id and stock or stock_bunches fields
            qs = model.objects.filter(category_id=category_id).values('id','name','price')
            # try include stock fields if present
            out = []
            for o in qs:
                obj = model.objects.get(pk=o['id'])
                stock = None
                if hasattr(obj, 'stock'):
                    stock = getattr(obj, 'stock')
                elif hasattr(obj, 'stock_bunches'):
                    stock = getattr(obj, 'stock_bunches')
                o['stock'] = stock
                out.append(o)
            return JsonResponse(out, safe=False)
        raise Http404("No item model found for given app_label")


