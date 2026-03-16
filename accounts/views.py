from django.views import View
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.urls import reverse, reverse_lazy

from .forms import RegisterForm, LoginForm
from .models import Customer

class RegisterView(View):
    def get(self, request):
        form = RegisterForm()
        return render(request, 'accounts/register.html', {'form': form})

    def post(self, request):
        form = RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            password = form.cleaned_data['password']
            phone = form.cleaned_data['phone']
            address = form.cleaned_data['address']

            username = (first_name + last_name).lower().replace(" ", "")

            if User.objects.filter(email=email).exists():
                messages.error(request, 'Email đã được sử dụng.')
            elif Customer.objects.filter(phone=phone).exists():
                messages.error(request, 'Số điện thoại đã được sử dụng.')
            else:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    password=password
                )
                Customer.objects.create(user=user, phone=phone, address=address)
                messages.success(request, 'Đăng ký thành công!')
                return redirect(reverse('index'))
        return render(request, 'accounts/register.html', {'form': form})


class LoginView(View):
    def get(self, request):
        form = LoginForm()
        role = request.GET.get("role")
        return render(request, 'accounts/login.html', {'form': form, 'role': role})

    def post(self, request):
        form = LoginForm(request.POST)
        if form.is_valid():
            email_or_username = form.cleaned_data['email']
            password = form.cleaned_data['password']

            # Tìm user theo email hoặc username
            try:
                if '@' in email_or_username:
                    user_obj = User.objects.get(email=email_or_username)
                else:
                    user_obj = User.objects.get(username=email_or_username)
            except User.DoesNotExist:
                user_obj = None

            if user_obj:
                user = authenticate(request, username=user_obj.username, password=password)
                if user is not None:
                    login(request, user)
                    messages.success(request, 'Đăng nhập thành công!')

                    # 1) Nếu có next param (GET hoặc POST) thì ưu tiên
                    next_url = request.GET.get('next') or request.POST.get('next')
                    if next_url:
                        return redirect(next_url)

                    # 2) Phân loại theo vai trò
                    # superuser/staff -> dashboard
                    if user.is_superuser or user.is_staff:
                        return redirect('dashboard:dashboard')

                    # supplier -> supplier request list (nếu user có supplier_profile)
                    # dùng hasattr để kiểm tra tránh import vòng
                    if hasattr(user, 'supplier_profile'):
                        # nếu bạn dùng flag approved, có thể kiểm tra thêm:
                        try:
                            profile = user.supplier_profile
                            if not getattr(profile, 'approved', True):
                                # nếu chưa được duyệt, chuyển tới trang thông báo (nếu có)
                                return redirect(reverse('supplier_portal:not_approved'))
                        except Exception:
                            pass
                        return redirect(reverse('supplier_portal:supplier_request_list'))

                    # default: khách hàng -> index
                    return redirect(reverse('index'))
                else:
                    form.add_error(None, 'Mật khẩu không đúng.')
            else:
                form.add_error(None, 'Tài khoản không tồn tại.')

        return render(request, 'accounts/login.html', {'form': form})


class LogoutView(View):
    def get(self, request):
        is_supplier = hasattr(request.user, "supplier_profile")

        logout(request)
        messages.success(request, 'Bạn đã đăng xuất thành công!')

        if is_supplier:
            # Supplier → quay lại login
            return redirect(reverse('accounts:login') + "?role=supplier")


        # Còn lại → về trang index
        return redirect(reverse('index'))
