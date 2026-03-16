document.addEventListener('DOMContentLoaded', function () {
  const buttons = document.querySelectorAll('.add-to-cart-btn');

  buttons.forEach(btn => {
    btn.addEventListener('click', async function (event) {
      event.preventDefault();
      const productId = this.dataset.productId;

      try {
        const response = await fetch(`/cart/add/${productId}/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCSRFToken(),
          },
          credentials: 'include', // 🟢 Bắt buộc gửi cookie session để Django biết bạn là ai
          redirect: 'manual',     // 🟢 Ngăn fetch tự động theo redirect (fix lỗi chính!)
        });

        // 🟢 Kiểm tra xem Django có trả về redirect login không
        if (response.type === 'opaqueredirect' || response.status === 302) {
          showToast("⚠️ Bạn cần đăng nhập để thêm sản phẩm vào giỏ hàng!");
          return;
        }

        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('text/html')) {
          showToast("⚠️ Bạn cần đăng nhập để thêm sản phẩm vào giỏ hàng!");
          return;
        }

        const data = await response.json();

        if (data.success) {
          showToast(`🛒 ${data.message}`);
        } else {
          showToast(`⚠️ ${data.message}`);
        }
      } catch (error) {
        console.error("Lỗi fetch:", error);
        showToast('❌ Không thể kết nối máy chủ.');
      }
    });
  });
});

function getCSRFToken() {
  const name = 'csrftoken';
  const cookies = document.cookie.split(';');
  for (let cookie of cookies) {
    cookie = cookie.trim();
    if (cookie.startsWith(name + '=')) {
      return cookie.substring(name.length + 1);
    }
  }
  return '';
}

function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast-message';
  toast.innerText = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}
