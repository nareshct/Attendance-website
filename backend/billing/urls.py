from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminAlertsView,
    BillingCycleViewSet,
    ClientInvoiceViewSet,
    CycleRevenueHistoryView,
    CycleRevenueView,
    MyClientBillingHistoryView,
    MyClientCurrentCycleView,
    MyClientInvoiceViewSet,
    MyCurrentCycleView,
    MyEarningsView,
    PayoutViewSet,
)

router = DefaultRouter()
router.register('billing-cycles', BillingCycleViewSet, basename='billing-cycle')
router.register('payouts', PayoutViewSet, basename='payout')
router.register('client-invoices', ClientInvoiceViewSet, basename='client-invoice')
router.register('my-client-invoices', MyClientInvoiceViewSet, basename='my-client-invoice')

urlpatterns = [
    path('my-earnings/current/', MyCurrentCycleView.as_view(), name='my-earnings-current'),
    path('my-earnings/', MyEarningsView.as_view(), name='my-earnings'),
    path('my-client-billing/current/', MyClientCurrentCycleView.as_view(), name='my-client-billing-current'),
    path('my-client-billing/history/', MyClientBillingHistoryView.as_view(), name='my-client-billing-history'),
    path('cycle-revenue/history/', CycleRevenueHistoryView.as_view(), name='cycle-revenue-history'),
    path('cycle-revenue/', CycleRevenueView.as_view(), name='cycle-revenue'),
    path('alerts/', AdminAlertsView.as_view(), name='admin-alerts'),
] + router.urls
