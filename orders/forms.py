from django import forms
from .models import Order

class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['full_name', 'address', 'shipping_address', 'phone', 'email', 'note', 'delivery_datetime']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nhập họ và tên của bạn'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Địa chỉ khách hàng'}),
            # Đổi từ Textarea sang TextInput để dùng autocomplete
            'shipping_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nhập địa chỉ nhận hàng (có gợi ý)'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nhập số điện thoại'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Nhập email (nếu có)'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Ví dụ: giao buổi sáng, gọi trước khi giao...'}),
            'delivery_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['address'].required = False
        self.fields['shipping_address'].required = True
        self.fields['delivery_datetime'].required = True