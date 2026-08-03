from rest_framework.routers import DefaultRouter

from .views import TrainerCourseRateViewSet, TrainerViewSet

router = DefaultRouter()
router.register('trainers', TrainerViewSet, basename='trainer')
router.register('trainer-rates', TrainerCourseRateViewSet, basename='trainer-rate')

urlpatterns = router.urls
