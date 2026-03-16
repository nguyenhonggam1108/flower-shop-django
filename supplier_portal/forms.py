from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.forms import inlineformset_factory, modelformset_factory, BaseInlineFormSet

from .models import (
    SupplierProfile,
    StockIn,
    StockInItem,
    StockOut,
    StockOutItem,
    SupplierOffer,
    MaterialRequest,
    RequestItem,
    Material, SupplierInvoice, SupplierInvoiceItem,
)

User = get_user_model()


class SupplierRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    company_name = forms.CharField(max_length=255, label="Company name")
    tax_code = forms.CharField(max_length=100, required=False, label="Tax code")
    phone = forms.CharField(max_length=20, required=False, label="Phone")
    address = forms.CharField(widget=forms.Textarea, required=False, label="Address")

    class Meta:
        model = User
        fields = ("email", "password1", "password2", "company_name", "tax_code", "phone", "address")

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.email = self.cleaned_data["email"]
            user.username = self.cleaned_data["email"]
            user.is_staff = False
            user.is_superuser = False
            if commit:
                user.save()
                SupplierProfile.objects.create(
                    user=user,
                    company_name=self.cleaned_data.get("company_name", ""),
                    tax_code=self.cleaned_data.get("tax_code", ""),
                    phone=self.cleaned_data.get("phone", ""),
                    address=self.cleaned_data.get("address", ""),
                    approved=True,
                )
        return user


class OfferForm(forms.ModelForm):
    class Meta:
        model = SupplierOffer
        fields = ('message',)


class StockInItemForm(forms.ModelForm):
    class Meta:
        model = StockInItem
        fields = ('material', 'quantity')
StockInItemFormSet = inlineformset_factory(StockIn, StockInItem, form=StockInItemForm, extra=1, can_delete=True)


class StockOutItemForm(forms.ModelForm):
    class Meta:
        model = StockOutItem
        fields = ('material', 'quantity')


StockOutItemFormSet = inlineformset_factory(StockOut, StockOutItem, form=StockOutItemForm, extra=1, can_delete=True)


# --- MaterialRequest form + inline formset ---
class MaterialRequestForm(forms.ModelForm):
    # Nếu bạn muốn có "desired_date" trong form và DB, thêm field này vào models.MaterialRequest
    # và đổi fields tuple bên dưới thành ('note', 'desired_date')
    class Meta:
        model = MaterialRequest
        fields = ('note',)


class RequestItemForm(forms.ModelForm):
    # category là non-model field để template render select danh mục
    category = forms.ChoiceField(choices=(), required=False, label='Danh mục')

    # material là ModelChoiceField; để an toàn set queryset = all materials
    material = forms.ModelChoiceField(queryset=Material.objects.all(), required=True)

    class Meta:
        model = RequestItem
        # thêm 'desired_price' vào fields
        fields = ('category', 'material', 'quantity', 'desired_price')

    def __init__(self, *args, categories=None, **kwargs):
        super().__init__(*args, **kwargs)

        # set category choices cho select danh mục (server-side)
        if categories:
            self.fields['category'].choices = categories
        else:
            self.fields['category'].choices = [('', '---------')]

        try:
            self.fields['material'].queryset = Material.objects.all()
        except Exception:
            self.fields['material'].queryset = Material.objects.none()

        # Widget / attrs cho các input (nâng trải nghiệm)
        self.fields['quantity'].widget.attrs.update({'class': 'form-control', 'step': '0.01', 'placeholder': '0'})
        self.fields['material'].widget.attrs.update({'class': 'form-control form-select'})
        # desired_price là không bắt buộc -> hiển thị placeholder
        self.fields['desired_price'].required = False
        self.fields['desired_price'].widget = forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'Ví dụ: 12000'
        })
RequestItemFormSet = inlineformset_factory(
    MaterialRequest,
    RequestItem,
    form=RequestItemForm,
    extra=1,
    can_delete=True
)

InvoiceItemFormSet = inlineformset_factory(
    SupplierInvoice,
    SupplierInvoiceItem,
    fields=('material', 'requested_qty', 'received_qty', 'unit_price'),
    extra=0,
    can_delete=False,
    widgets={
        'material': forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control'}),
        'requested_qty': forms.NumberInput(attrs={'readonly': 'readonly', 'class': 'form-control'}),
        'received_qty': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
    }
)

class SupplierInvoiceForm(forms.ModelForm):
    class Meta:
        model = SupplierInvoice
        fields = ("vat_percent",)


class SupplierInvoiceItemForm(forms.ModelForm):
    class Meta:
        model = SupplierInvoiceItem
        fields = ("material", "requested_qty", "received_qty", "unit_price")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # DÙNG HiddenInput cho material, KHÔNG disabled, KHÔNG select!
        self.fields["material"].widget = forms.HiddenInput()
        self.fields["requested_qty"].widget.attrs["readonly"] = True  # chỉ xem, không sửa
        self.fields["received_qty"].required = True

    def clean_received_qty(self):
        value = self.cleaned_data.get("received_qty")
        if value in (None, ""):
            raise forms.ValidationError("Bạn chưa nhập số lượng nhập kho!")
        if float(value) <= 0:
            raise forms.ValidationError("Số lượng nhập phải lớn hơn 0.")
        return value

SupplierInvoiceItemFormSet = inlineformset_factory(
    SupplierInvoice,
    SupplierInvoiceItem,
    form=SupplierInvoiceItemForm,
    extra=0,
    can_delete=False,
)


class StockOutForm(forms.ModelForm):
    class Meta:
        model = StockOut
        fields = ('note',)

StockOutItemFormSet = inlineformset_factory(
    StockOut,
    StockOutItem,
    fields=('material', 'quantity'),
    extra=1,
    can_delete=True
)
