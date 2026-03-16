from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from product.models import Product
from cart.models import CartItem
from django.db.models import Sum

# 🛒 Xem giỏ hàng
class CartView(View):
    def get(self, request):
        if request.user.is_authenticated:
            items = CartItem.objects.filter(user=request.user).select_related('product')
            total_quantity = CartItem.objects.filter(user=request.user).aggregate(Sum('quantity'))['quantity__sum'] or 0
        else:
            session_cart = request.session.get('cart', {})
            items = []
            total_quantity = 0
            for product_id, item in session_cart.items():
                product = get_object_or_404(Product, id=product_id)
                item_obj = type('CartItemTemp', (), {})()
                item_obj.product = product
                item_obj.quantity = item['quantity']
                item_obj.subtotal = product.price * item['quantity']
                item_obj.id = product.id
                items.append(item_obj)
                total_quantity += item['quantity']

        total = sum(item.product.price * item.quantity for item in items)

        return render(request, 'cart/cart_view.html', {
            'cart_items': items,
            'total': total,
            'cart_total_quantity': total_quantity,
        })




class AddToCartView(View):
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        if product.status == 'out_of_stock':
            # Nếu dùng Ajax: trả về JSON lỗi luôn!
            return JsonResponse({
                'success': False,
                'message': "Sản phẩm đã hết hàng, không thể thêm vào giỏ!",
                'cart_count': None
            })
        quantity = int(request.POST.get('quantity', 1))

        if request.user.is_authenticated:
            # 🔹 Giỏ hàng lưu trong DB
            cart_item, created = CartItem.objects.get_or_create(
                user=request.user,
                product=product,
                defaults={'quantity': quantity}
            )
            if not created:
                # ✅ Nếu người dùng chỉ click thêm, không truyền số lượng cụ thể, chỉ cộng +1
                cart_item.quantity += quantity
                cart_item.save()

            cart_count = CartItem.objects.filter(user=request.user).aggregate(
                Sum('quantity')
            )['quantity__sum'] or 0

        else:
            # 🔹 Giỏ hàng lưu trong session
            cart = request.session.get('cart', {})
            product_key = str(product_id)

            # ✅ Nếu chưa có thì thêm mới
            if product_key not in cart:
                cart[product_key] = {
                    'quantity': quantity,
                    'price': str(product.price)
                }
            else:
                # ✅ Nếu có rồi thì chỉ cộng thêm nếu chưa update_quantity
                cart[product_key]['quantity'] += quantity

            # Lưu lại session
            request.session['cart'] = cart

            cart_count = sum(item['quantity'] for item in cart.values())

        # ✅ Trả về JSON cho Ajax
        return JsonResponse({
            'success': True,
            'message': "Đã thêm vào giỏ hàng",
            'cart_count': cart_count
        })
# 🔄 Cập nhật số lượng
class UpdateCartView(View):
    def post(self, request, item_id):
        quantity = int(request.POST.get('quantity', 1))

        if request.user.is_authenticated:
            item = get_object_or_404(CartItem, id=item_id, user=request.user)
            if quantity > 0:
                item.quantity = quantity
                item.save()
            else:
                item.delete()
        else:
            cart = request.session.get('cart', {})
            if str(item_id) in cart:
                if quantity > 0:
                    cart[str(item_id)]['quantity'] = quantity
                else:
                    del cart[str(item_id)]
                request.session['cart'] = cart

        return redirect('cart:view_cart')


# ❌ Xóa sản phẩm khỏi giỏ hàng
class RemoveFromCartView(View):
    def post(self, request, item_id):
        if request.user.is_authenticated:
            item = get_object_or_404(CartItem, id=item_id, user=request.user)
            item.delete()
        else:
            cart = request.session.get('cart', {})
            if str(item_id) in cart:
                del cart[str(item_id)]
                request.session['cart'] = cart

        return redirect('cart:view_cart')