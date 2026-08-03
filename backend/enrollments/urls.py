from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import EnrollmentViewSet, MyStudentsView, PaymentInstallmentViewSet, SubstituteAssignmentViewSet

router = DefaultRouter()
router.register('enrollments', EnrollmentViewSet, basename='enrollment')
router.register('installments', PaymentInstallmentViewSet, basename='installment')
router.register('substitute-assignments', SubstituteAssignmentViewSet, basename='substitute-assignment')

urlpatterns = [
    path('my-students/', MyStudentsView.as_view(), name='my-students'),
] + router.urls
