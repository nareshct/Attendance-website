from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ParentCertificateView, ParentShareView, StudentViewSet

router = DefaultRouter()
router.register('students', StudentViewSet, basename='student')

urlpatterns = [
    path('parent-view/<uuid:token>/', ParentShareView.as_view(), name='parent-view'),
    path(
        'parent-view/<uuid:token>/enrollments/<int:enrollment_id>/certificate/',
        ParentCertificateView.as_view(),
        name='parent-certificate',
    ),
] + router.urls
