"""
URL configuration for first_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from first_app import views

from first_app.views import IndexView

from first_app.views import AboutView,  DesignView

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('',IndexView.as_view(),name='index'),
    path('orders/', include('orders.urls')),
    path('admin/orders/', include('orders.urls_admin')),
    path('user_profile/',include('user_profile.urls')),
    path('accounts/',include('accounts.urls')),
    path('wishlist/',include('wishlist.urls')),
    path('category/', include('category.urls')),
    path('cart/', include('cart.urls')),
    path('product/', include('product.urls')),
    path('admin/products/', include('product.urls_admin')),
    path('dropdown/',include('first_app.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('inventory/', include('inventory.urls')),
    path('accessories/', include('accessories.urls')),
    path("supplier/", include("supplier_portal.urls", namespace="supplier_portal")),
    path('index/', IndexView.as_view(), name='index'),
    path('about/', AboutView.as_view(), name='about'),
    path('design/',DesignView.as_view(), name='design'),
    path('paypal/', include('paypal.standard.ipn.urls')),
    path("admin/", admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
