from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    EnrollmentViewSet,
    MyClientEnrollmentCertificateView,
    MyClientEnrollmentReportView,
    MyClientEnrollmentsView,
    MyStudentsView,
    PaymentInstallmentViewSet,
    SubstituteAssignmentViewSet,
)

router = DefaultRouter()
router.register('enrollments', EnrollmentViewSet, basename='enrollment')
router.register('installments', PaymentInstallmentViewSet, basename='installment')
router.register('substitute-assignments', SubstituteAssignmentViewSet, basename='substitute-assignment')

urlpatterns = [
    path('my-students/', MyStudentsView.as_view(), name='my-students'),
    path('my-client-enrollments/', MyClientEnrollmentsView.as_view(), name='my-client-enrollments'),
    path('my-client-enrollments/<int:pk>/report/', MyClientEnrollmentReportView.as_view(), name='my-client-enrollment-report'),
    path('my-client-enrollments/<int:pk>/certificate/', MyClientEnrollmentCertificateView.as_view(), name='my-client-enrollment-certificate'),
] + router.urls
