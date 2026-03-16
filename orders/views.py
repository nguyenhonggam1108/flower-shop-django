from django.utils.http import urlencode
from django.views.generic import FormView, DetailView, ListView
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.urls import reverse
from .models import Order, OrderItem,Coupon
from .forms import CheckoutForm
from cart.models import CartItem
from cart.cart_session import Cart
from django.utils import timezone
from django.conf import settings
from paypal.standard.forms import PayPalPaymentsForm
from decimal import Decimal
from django.db import models
from django.views import View
from .utils import AddressDistanceValidator
import logging
from typing import Iterable, Optional
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.dateparse import parse_datetime
import qrcode
import base64
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


class CheckoutView(FormView):
    template_name = 'orders/checkout.html'
    form_class = CheckoutForm

    def get_cart_items(self):
        """Lấy danh sách sản phẩm trong giỏ hàng"""
        if self.request.user.is_authenticated:
            items = CartItem.objects.filter(user=self.request.user).select_related('product')
            cart_data = []
            for item in items:
                cart_data.append({
                    'product': item.product,
                    'quantity': item.quantity,
                    'price': item.product.price,
                    'total_price': item.product.price * item.quantity,
                })
            total = sum(i['total_price'] for i in cart_data)
            return cart_data, total
        else:
            cart = Cart(self.request)
            cart_data = list(cart)
            total = cart.get_total_price()
            return cart_data, total

    def get_context_data(self, **kwargs):
        # ... giữ nguyên không đổi ...
        context = super().get_context_data(**kwargs)
        cart_items, total = self.get_cart_items()
        context['cart_items'] = cart_items
        context['cart_total'] = total
        if self.request.user.is_authenticated:
            available_coupons = Coupon.objects.filter(
                active=True,
            ).filter(
                models.Q(start_date__lte=timezone.now()) | models.Q(start_date__isnull=True),
                models.Q(expiry_date__gte=timezone.now()) | models.Q(expiry_date__isnull=True)
            ).order_by('-start_date')
            context['available_coupons'] = available_coupons
        else:
            context['available_coupons'] = None

        return context

    def post(self, request, *args, **kwargs):
        """Bỏ qua validate để xử lý form tùy chỉnh"""
        return self.form_valid(None)

    def form_valid(self, form):
        cart_items, total = self.get_cart_items()
        if not cart_items:
            messages.error(self.request, "Giỏ hàng trống!")
            return redirect('cart:view_cart')

        order = Order()

        # --- LẤY THÔNG TIN FORM ---
        order.full_name = self.request.POST.get('full_name', '')
        order.phone = self.request.POST.get('phone', '')
        order.email = self.request.POST.get('email', '')
        order.address = self.request.POST.get('customer_address', '') or ''
        order.note = self.request.POST.get('note', '') or ''

        shipping_address = self.request.POST.get('shipping_address')
        if shipping_address:
            order.shipping_address = shipping_address
        else:
            order.shipping_address = order.address

        # --- Xử lý hình thức giao hàng ---
        order_type = self.request.POST.get('order_type', 'delivery')
        if order_type == 'pickup':
            order.shipping_method = Order.SHIPPING_PICKUP
            order.address = "Khách nhận hàng trực tiếp tại cửa hàng Bloom & Story"
            order.note = (order.note or "") + " | Hình thức: Nhận hàng tại cửa hàng"
        else:
            # DELIVERY: Tiến hành kiểm tra KHU VỰC & GIỜ
            order.shipping_method = Order.SHIPPING_DELIVERY

            delivery_datetime_str = self.request.POST.get('delivery_datetime')
            delivery_datetime = parse_datetime(delivery_datetime_str) if delivery_datetime_str else None
            # ---- Kiểm tra nội thành TP Hồ Chí Minh ----
            IN_HCM_DISTRICTS = [
                "quận 1", "quận 3", "quận 4", "quận 5", "quận 6", "quận 7", "quận 8",
                "quận 10", "quận 11", "quận 12", "phú nhuận", "gò vấp",
                "bình thạnh", "tân bình", "tân phú",
            ]

            def is_inner_hcm(address):
                if not address:
                    return False
                address = address.lower()
                # Bắt buộc phải có "hồ chí minh" hoặc các quận nội thành
                return any(q in address for q in IN_HCM_DISTRICTS) or "hồ chí minh" in address or "tp hcm" in address or "tphcm" in address

            if not is_inner_hcm(shipping_address):
                messages.error(self.request,
                               "Chúng tôi chỉ giao hàng trong KHU VỰC NỘI THÀNH TP.HCM, vui lòng nhập lại!")
                return redirect('orders:checkout')

            # BỎ gần hết phần logic giờ sớm nhất; để bắt buộc KH chọn thời gian trong tương lai (xử lý ở JS là đủ với luận văn).
            order.delivery_datetime = parse_datetime(self.request.POST.get('delivery_datetime'))

        # ... Gán user và phần còn lại giữ nguyên ...
        if self.request.user.is_authenticated:
            order.user = self.request.user
            if not order.full_name:
                order.full_name = f"{self.request.user.first_name} {self.request.user.last_name}".strip() or self.request.user.username
            if not order.email:
                order.email = self.request.user.email
            if not order.phone and hasattr(self.request.user, 'customer'):
                order.phone = self.request.user.customer.phone
            if not order.address and hasattr(self.request.user, 'customer') and order_type != 'pickup':
                order.address = self.request.user.customer.address
            if not order.shipping_address and hasattr(self.request.user, 'customer') and order_type != 'pickup':
                order.shipping_address = self.request.user.customer.address

        order.total_amount = total
        order.final_total = total

        pm = (self.request.POST.get('payment_method', 'cod') or 'cod').lower()
        if pm == 'paypal':
            order.payment_method = Order.PAYMENT_PAYPAL
        elif pm == 'cod':
            order.payment_method = Order.PAYMENT_COD
        elif pm == 'qr':
            order.payment_method = Order.PAYMENT_PAYPAL
        else:
            order.payment_method = Order.PAYMENT_COD

        order.save()
        full_order_url = self.request.build_absolute_uri(order.get_absolute_url())
        order.generate_qr(full_url=full_order_url, save_instance=True)

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                quantity=item['quantity'],
                price=item['price']
            )

        # ... Thanh toán các phương thức phía dưới giữ nguyên của bạn ...
        # --- Thanh toán Paypal / QR / COD ---
        if pm == 'paypal':
            self.request.session['order_id'] = order.id
            self.request.session['cart_total_vnd'] = float(order.final_total)
            return redirect('orders:payment')
        elif pm == 'qr':
            return redirect(reverse('orders:payment_qr', kwargs={'order_id': order.id}))
        elif pm == 'cod':
            try:
                recipient = order.email or (order.user.email if getattr(order, 'user', None) else None)
                if recipient:
                    from django.core.mail import send_mail
                    subject = f"[Bloom & Story] Xác nhận đơn hàng #{order.id}"
                    text_message = (
                        f"Xin chào {order.full_name},\n\n"
                        f"Chúng tôi đã nhận đơn hàng #{order.id}. Tổng: {order.final_total} VND.\n"
                        "Bạn sẽ thanh toán khi nhận hàng (COD).\n\n"
                        "Cảm ơn bạn đã mua hàng tại Bloom & Story."
                    )
                    html_message = f"""
                        <p>Xin chào <strong>{order.full_name}</strong>,</p>
                        <p>Chúng tôi đã nhận đơn hàng <strong>#{order.id}</strong>.</p>
                        <p><strong>Tổng cộng:</strong> {order.final_total} VND</p>
                        <p>Hình thức thanh toán: <strong>COD</strong> (thu khi nhận hàng)</p>
                        <p>Chúng tôi sẽ liên hệ để xác nhận và giao hàng sớm nhất 💐</p>
                    """
                    send_mail(
                        subject,
                        text_message,
                        settings.DEFAULT_FROM_EMAIL,
                        [recipient],
                        html_message=html_message,
                        fail_silently=False,
                    )
            except Exception:
                messages.warning(self.request, "Không gửi được email xác nhận — kiểm tra cấu hình email.")

            if self.request.user.is_authenticated:
                CartItem.objects.filter(user=self.request.user).delete()
            else:
                Cart(self.request).clear()

            messages.success(self.request, "Đặt hàng thành công! Thanh toán khi nhận hàng.")
            return redirect(reverse('orders:order_success', kwargs={'order_id': order.id}))

        messages.success(self.request, "Đặt hàng thành công!")
        return redirect(reverse('orders:order_success', kwargs={'order_id': order.id}))


class OrderSuccessView(DetailView):
    model = Order
    template_name = 'orders/orders_success.html'
    context_object_name = 'order'

    def get_object(self):
        order_id = self.kwargs.get('order_id')
        return get_object_or_404(Order, id=order_id)


class PaymentView(FormView):
    """Hiển thị form thanh toán PayPal"""
    template_name = 'orders/payment.html'

    def get(self, request, *args, **kwargs):
        order_id = request.session.get('order_id')
        total_vnd = request.session.get('cart_total_vnd')

        if not order_id or not total_vnd:
            messages.error(request, "Không tìm thấy đơn hàng cần thanh toán.")
            return redirect('orders:checkout')

        # Quy đổi từ VND → USD (1 USD = 24,000 VND)
        rate = Decimal('24000')
        usd_amount = (Decimal(total_vnd) / rate).quantize(Decimal('0.01'))

        paypal_dict = {
            'business': settings.PAYPAL_RECEIVER_EMAIL,
            'amount': str(usd_amount),
            'item_name': f'Đơn hàng #{order_id} - Bloom & Story',
            'invoice': f'INV-{order_id}',
            'currency_code': 'USD',
            'notify_url': request.build_absolute_uri('/paypal/'),
            'return_url': request.build_absolute_uri(reverse('orders:payment_done')),
            'cancel_return': request.build_absolute_uri(reverse('orders:payment_cancelled')),
        }

        form = PayPalPaymentsForm(initial=paypal_dict)
        context = {
            'form': form,
            'usd_amount': usd_amount,
            'total_vnd': total_vnd
        }
        return render(request, self.template_name, context)


class PaymentQRView(View):
    template_name = 'orders/payment_qr.html'

    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)

        if order.is_paid:
            return redirect(reverse('orders:order_success', kwargs={'order_id': order.id}))

        # Chuyển VND -> USD
        rate = getattr(settings, 'VND_TO_USD_RATE', 24000)
        usd_amount = (Decimal(order.final_total) / Decimal(rate)).quantize(Decimal('0.01'))

        # Thay vì trỏ trực tiếp tới PayPal bằng GET, chúng ta trỏ QR tới endpoint nội bộ
        # endpoint này sẽ auto-submit một form POST đến PayPal (PaypalRedirectView)
        redirect_url = request.build_absolute_uri(reverse('orders:paypal_redirect', kwargs={'order_id': order.id}))

        # Tạo QR code trỏ tới redirect_url nội bộ
        qr_img = qrcode.make(redirect_url)
        buffer = BytesIO()
        qr_img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        buffer.close()

        context = {
            'order': order,
            'qr_base64': qr_base64,
            'paypal_link': redirect_url,  # template vẫn dùng biến paypal_link
            'usd_amount': usd_amount,
            'vnd_amount': order.final_total,
        }
        return render(request, self.template_name, context)


class PaymentDoneView(FormView):
    template_name = 'orders/payment_done.html'

    def get(self, request, *args, **kwargs):
        order_id = request.session.get('order_id')
        if not order_id:
            messages.error(request, "Không tìm thấy thông tin đơn hàng.")
            return redirect('orders:checkout')

        order = Order.objects.filter(id=order_id).first()
        if order:
            order.is_paid = True
            order.status = 'paid'
            order.save()

            # 👉 GỬI EMAIL XÁC NHẬN THANH TOÁN PAYPAL
            try:
                sender = OrderEmailSender(order)
                sender.send()
            except Exception as e:
                logger.exception("Lỗi gửi email PayPal: %s", e)

            # Xóa giỏ hàng
            if request.user.is_authenticated:
                CartItem.objects.filter(user=request.user).delete()
            else:
                Cart(request).clear()

        # Xóa session
        request.session.pop('order_id', None)
        request.session.pop('cart_total_vnd', None)

        messages.success(request, "Thanh toán PayPal thành công!")
        return redirect(reverse('orders:order_success', kwargs={'order_id': order.id}))


class PaymentCancelledView(FormView):
    """Khi người dùng hủy thanh toán"""
    template_name = 'orders/payment_cancelled.html'

    def get(self, request, *args, **kwargs):
        messages.warning(request, "Bạn đã hủy thanh toán PayPal.")
        return redirect('orders:checkout')

class PaypalRedirectView(View):
    """
    Endpoint nội bộ: render 1 form hidden chứa các field PayPal rồi auto-submit (POST).
    QR sẽ trỏ tới endpoint này thay vì trỏ thẳng tới sandbox.paypal.com.
    """
    template_name = 'orders/paypal_post.html'

    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        if order.is_paid:
            return redirect(reverse('orders:order_success', kwargs={'order_id': order.id}))

        rate = getattr(settings, 'VND_TO_USD_RATE', 24000)
        usd_amount = (Decimal(order.final_total) / Decimal(rate)).quantize(Decimal('0.01'))

        use_sandbox = getattr(settings, 'PAYPAL_USE_SANDBOX', True)
        if use_sandbox:
            paypal_url = 'https://www.sandbox.paypal.com/cgi-bin/webscr'
        else:
            paypal_url = 'https://www.paypal.com/cgi-bin/webscr'

        paypal_fields = {
            'cmd': '_xclick',
            'business': getattr(settings, 'PAYPAL_RECEIVER_EMAIL', ''),
            'amount': str(usd_amount),
            'currency_code': 'USD',
            'item_name': f'Đơn hàng #{order.id} - Bloom & Story',
            'invoice': f'INV-{order.id}',
            'return': request.build_absolute_uri(reverse('orders:payment_done')),
            'cancel_return': request.build_absolute_uri(reverse('orders:payment_cancelled')),
            'notify_url': request.build_absolute_uri('/paypal/'),  # nếu bạn dùng IPN
        }

        logger.info("PaypalRedirectView: order=%s, usd=%s, paypal_url=%s", order.id, usd_amount, paypal_url)
        context = {
            'paypal_url': paypal_url,
            'paypal_fields': paypal_fields,
            'order': order,
        }
        return render(request, self.template_name, context)

class OrderEmailSender:
    """
    Class để gửi email liên quan tới order.
    Sử dụng:
        sender = OrderEmailSender(order)
        sender.send()  # gửi email xác nhận mặc định
    Có thể tùy chỉnh template, subject hoặc recipient_list khi tạo instance.
    """

    def __init__(
        self,
        order,
        template_name: str = "orders/order_confirmation.html",
        subject_template: Optional[str] = None,
        from_email: Optional[str] = None,
        recipient_list: Optional[Iterable[str]] = None,
    ):
        self.order = order
        self.template_name = template_name
        # nếu không truyền subject_template, dùng mặc định
        self.subject_template = subject_template or f"[Bloom & Story] Xác nhận đơn hàng #{order.id}"
        self.from_email = from_email or settings.DEFAULT_FROM_EMAIL
        # nhận email từ order.email nếu không truyền recipient_list
        self.recipient_list = list(recipient_list) if recipient_list is not None else [order.email] if getattr(order, "email", None) else (
            [order.user.email] if getattr(order, "user", None) and getattr(order.user, "email", None) else []
        )

    def get_context(self) -> dict:
        """Context mặc định truyền vào template"""
        return {"order": self.order}

    def render_messages(self) -> tuple[str, str]:
        """
        Trả về (plain_message, html_message)
        """
        html_message = render_to_string(self.template_name, self.get_context())
        plain_message = strip_tags(html_message)
        return plain_message, html_message

    def send(self, fail_silently: bool = False) -> bool:
        """
        Thực hiện gửi mail. Trả về True nếu gửi (và recipient_list không rỗng),
        False nếu không có recipient để gửi.
        Exceptions được ném ra nếu fail_silently=False.
        """
        if not self.recipient_list:
            logger.warning("OrderEmailSender: no recipient for order %s, skipping email", getattr(self.order, "id", "unknown"))
            return False

        plain_message, html_message = self.render_messages()
        subject = self.subject_template

        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=self.from_email,
                recipient_list=self.recipient_list,
                html_message=html_message,
                fail_silently=fail_silently,
            )
            logger.info("OrderEmailSender: sent email '%s' to %s for order %s", subject, self.recipient_list, getattr(self.order, "id", "unknown"))
            return True
        except Exception:
            logger.exception("OrderEmailSender: error sending email for order %s", getattr(self.order, "id", "unknown"))
            if not fail_silently:
                raise
            return False

    def send_async(self) -> None:
        """
        Gửi không đồng bộ nhanh bằng threading (đơn giản). Nếu cần production-scale, dùng Celery/RQ.
        """
        import threading
        threading.Thread(target=self.send, daemon=True).start()

class QRDetailView(DetailView):
    model = Order
    template_name = 'orders/qr_detail.html'
    context_object_name = 'order'

    def get_object(self):
        order_id = self.kwargs.get('order_id')
        return get_object_or_404(Order, id=order_id)

