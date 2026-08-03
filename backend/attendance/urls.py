from rest_framework.routers import DefaultRouter

from .views import AttendanceRequestViewSet, AttendanceViewSet

router = DefaultRouter()
router.register('attendance', AttendanceViewSet, basename='attendance')
router.register('attendance-requests', AttendanceRequestViewSet, basename='attendance-request')

urlpatterns = router.urls
