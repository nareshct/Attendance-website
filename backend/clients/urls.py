from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ClientContactViewSet,
    ClientCourseRateViewSet,
    ClientViewSet,
    MyClientProfileView,
    MyClientStudentDetailView,
    MyClientStudentsView,
)

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='client')
router.register('client-rates', ClientCourseRateViewSet, basename='client-rate')
router.register('client-contacts', ClientContactViewSet, basename='client-contact')

urlpatterns = [
    path('my-client-profile/', MyClientProfileView.as_view(), name='my-client-profile'),
    path('my-client-students/', MyClientStudentsView.as_view(), name='my-client-students'),
    path('my-client-students/<int:student_id>/', MyClientStudentDetailView.as_view(), name='my-client-student-detail'),
] + router.urls
