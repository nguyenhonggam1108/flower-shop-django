from django.apps import apps
from django.forms import inlineformset_factory
from django import forms
from django.forms import inlineformset_factory
from .models import GoodsReceipt, GoodsReceiptItem
from .models import MaterialRequest, RequestItem, Material
class GoodsReceiptForm(forms.ModelForm):
    class Meta:
        model = GoodsReceipt
        fields = ['supplier', 'invoice_file', 'note']

class GoodsReceiptItemForm(forms.ModelForm):
    class Meta:
        model = GoodsReceiptItem
        # không include content_type/object_id ở form, sẽ set trong view từ hidden inputs
        fields = ['quantity_bunch', 'unit_price']
        widgets = {
            'quantity_bunch': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

GoodsReceiptItemFormSet = inlineformset_factory(
    GoodsReceipt,
    GoodsReceiptItem,
    form=GoodsReceiptItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)
try:
    Material = apps.get_model('inventory', 'Material')
except LookupError:
    Material = None

try:
    FlowerCategory = apps.get_model('inventory', 'FlowerCategory')
    FlowerItem = apps.get_model('inventory', 'FlowerItem')
except LookupError:
    FlowerCategory = None
    FlowerItem = None

# Thay 'accessories' bằng tên app chứa AccessoryCategory/AccessoryItem nếu khác
try:
    AccessoryCategory = apps.get_model('accessories', 'AccessoryCategory')
    AccessoryItem = apps.get_model('accessories', 'AccessoryItem')
except LookupError:
    AccessoryCategory = None
    AccessoryItem = None

# RequestItem và MaterialRequest model trong app inventory
try:
    RequestItem = apps.get_model('inventory', 'RequestItem')
    MaterialRequest = apps.get_model('inventory', 'MaterialRequest')
except LookupError:
    RequestItem = None
    MaterialRequest = None


def build_combined_categories():
    """
    Trả về list các choices dạng (value, label)
    value: 'flower-<id>' hoặc 'acc-<id>'
    label: 'Hoa - <tên>' / 'Phụ kiện - <tên>'
    """
    choices = []
    if FlowerCategory:
        for cat in FlowerCategory.objects.all():
            choices.append((f"flower-{cat.id}", f"Hoa - {cat.name}"))
    if AccessoryCategory:
        for cat in AccessoryCategory.objects.all():
            choices.append((f"acc-{cat.id}", f"Phụ kiện - {cat.name}"))
    return choices


class MaterialRequestForm(forms.ModelForm):
    desired_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Ngày muốn nhận hàng"
    )

    class Meta:
        model = MaterialRequest
        fields = ['note', 'desired_date']


class RequestItemForm(forms.ModelForm):
    # category chỉ dùng để giúp chọn loại & lọc material; không lưu xuống model
    category = forms.ChoiceField(choices=[], required=False, label="Danh mục")

    class Meta:
        model = RequestItem
        # material là FK tới Material; quantity giữ như model
        fields = ['category', 'material', 'quantity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # set choices cho category
        self.fields['category'].choices = build_combined_categories()

        # nếu không có model Material thì chuyển material thành ChoiceField rỗng để tránh lỗi
        if Material is None:
            self.fields['material'] = forms.ChoiceField(choices=[], required=False, label="Nguyên liệu")
            return

        # mặc định để queryset rỗng; JS client-side sẽ populate select dựa vào materials_json
        self.fields['material'].queryset = Material.objects.none()

        # Nếu có dữ liệu POST, lọc queryset để server-side validation pass
        data = kwargs.get('data')
        if data:
            cat_val = data.get(self.add_prefix('category'))
            if cat_val:
                # format: 'flower-<id>' or 'acc-<id>'
                if cat_val.startswith('flower-') and FlowerItem:
                    try:
                        cat_id = int(cat_val.split('-')[1])
                        flower_names = list(FlowerItem.objects.filter(category_id=cat_id).values_list('name', flat=True))
                        if flower_names:
                            self.fields['material'].queryset = Material.objects.filter(name__in=flower_names)
                    except Exception:
                        self.fields['material'].queryset = Material.objects.none()
                elif cat_val.startswith('acc-') and AccessoryItem:
                    try:
                        acc_id = int(cat_val.split('-')[1])
                        accessory_names = list(AccessoryItem.objects.filter(category_id=acc_id).values_list('name', flat=True))
                        if accessory_names:
                            self.fields['material'].queryset = Material.objects.filter(name__in=accessory_names)
                    except Exception:
                        self.fields['material'].queryset = Material.objects.none()

        # Nếu instance tồn tại (edit), cố gắng set initial category + material queryset
        if getattr(self, 'instance', None) and getattr(self.instance, 'pk', None) and getattr(self.instance, 'material', None):
            try:
                mat = self.instance.material
                mat_name = getattr(mat, 'name', None)
                if FlowerItem and FlowerItem.objects.filter(name=mat_name).exists():
                    fi = FlowerItem.objects.filter(name=mat_name).first()
                    self.fields['category'].initial = f"flower-{fi.category_id}"
                    self.fields['material'].queryset = Material.objects.filter(name=mat_name)
                    self.fields['material'].initial = mat.pk
                elif AccessoryItem and AccessoryItem.objects.filter(name=mat_name).exists():
                    ai = AccessoryItem.objects.filter(name=mat_name).first()
                    self.fields['category'].initial = f"acc-{ai.category_id}"
                    self.fields['material'].queryset = Material.objects.filter(name=mat_name)
                    self.fields['material'].initial = mat.pk
                else:
                    self.fields['material'].queryset = Material.objects.all()
            except Exception:
                self.fields['material'].queryset = Material.objects.none()


# Inline formset factory (sử dụng RequestItem và MaterialRequest)
if RequestItem is not None and MaterialRequest is not None:
    RequestItemFormSet = inlineformset_factory(
        MaterialRequest,
        RequestItem,
        form=RequestItemForm,
        extra=1,
        can_delete=True
    )
else:
    RequestItemFormSet = None(forms.ModelForm)
    # category chỉ dùng để giúp chọn loại & lọc material; không lưu xuống model
    category = forms.ChoiceField(choices=[], required=False, label="Danh mục")

    class Meta:
        model = RequestItem
        # material là FK tới Material; quantity giữ như model
        fields = ['category', 'material', 'quantity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # set choices cho category
        self.fields['category'].choices = build_combined_categories()

        # nếu không có model Material thì chuyển material thành ChoiceField rỗng để tránh lỗi
        if Material is None:
            # fallback: dùng CharField/ChoiceField để tránh crash; tuy nhiên save sẽ lỗi nếu model expects FK
            self.fields['material'] = forms.ChoiceField(choices=[], required=False, label="Nguyên liệu")
            return

        # mặc định để queryset rỗng; JS client-side sẽ populate select dựa vào materials_json
        self.fields['material'].queryset = Material.objects.none()

        # Nếu có dữ liệu POST, lọc queryset để server-side validation pass
        data = kwargs.get('data')
        if data:
            cat_val = data.get(self.add_prefix('category'))
            if cat_val:
                # format: 'flower-<id>' or 'acc-<id>'
                if cat_val.startswith('flower-') and FlowerItem:
                    try:
                        cat_id = int(cat_val.split('-')[1])
                        # Lấy tên các FlowerItem trong category -> lọc Material theo name tương ứng
                        flower_names = list(FlowerItem.objects.filter(category_id=cat_id).values_list('name', flat=True))
                        if flower_names:
                            self.fields['material'].queryset = Material.objects.filter(name__in=flower_names)
                    except Exception:
                        # fallback để tránh crash
                        self.fields['material'].queryset = Material.objects.none()
                elif cat_val.startswith('acc-') and AccessoryItem:
                    try:
                        acc_id = int(cat_val.split('-')[1])
                        accessory_names = list(AccessoryItem.objects.filter(category_id=acc_id).values_list('name', flat=True))
                        if accessory_names:
                            self.fields['material'].queryset = Material.objects.filter(name__in=accessory_names)
                    except Exception:
                        self.fields['material'].queryset = Material.objects.none()
        # Nếu instance tồn tại (edit), cố gắng set initial category + material queryset
        if getattr(self, 'instance', None) and getattr(self.instance, 'pk', None) and getattr(self.instance, 'material', None):
            try:
                # cố lấy Material name -> tìm FlowerItem hoặc AccessoryItem có cùng tên để set category ban đầu
                mat = self.instance.material
                mat_name = getattr(mat, 'name', None)
                if FlowerItem and FlowerItem.objects.filter(name=mat_name).exists():
                    fi = FlowerItem.objects.filter(name=mat_name).first()
                    self.fields['category'].initial = f"flower-{fi.category_id}"
                    self.fields['material'].queryset = Material.objects.filter(name=mat_name)
                    self.fields['material'].initial = mat.pk
                elif AccessoryItem and AccessoryItem.objects.filter(name=mat_name).exists():
                    ai = AccessoryItem.objects.filter(name=mat_name).first()
                    self.fields['category'].initial = f"acc-{ai.category_id}"
                    self.fields['material'].queryset = Material.objects.filter(name=mat_name)
                    self.fields['material'].initial = mat.pk
                else:
                    # nếu không tìm thấy ánh xạ, mặc định cho phép tất cả material để edit
                    self.fields['material'].queryset = Material.objects.all()
            except Exception:
                self.fields['material'].queryset = Material.objects.none()