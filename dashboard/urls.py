from django.urls import path
from .views import DashboardView, RevenueStatsView, MaterialRequestCreateView

app_name = 'dashboard'
urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('revenue/', RevenueStatsView.as_view(), name='revenue_stats'),
]
