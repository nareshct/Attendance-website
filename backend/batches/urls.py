from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BatchEnrollmentViewSet,
    BatchInstallmentViewSet,
    BatchPayoutViewSet,
    BatchSessionViewSet,
    BatchViewSet,
    MyBatchesView,
)

router = DefaultRouter()
router.register('batches', BatchViewSet, basename='batch')
router.register('batch-enrollments', BatchEnrollmentViewSet, basename='batch-enrollment')
router.register('batch-installments', BatchInstallmentViewSet, basename='batch-installment')
router.register('batch-sessions', BatchSessionViewSet, basename='batch-session')
router.register('batch-payouts', BatchPayoutViewSet, basename='batch-payout')

urlpatterns = [path('my-batches/', MyBatchesView.as_view(), name='my-batches')] + router.urls
