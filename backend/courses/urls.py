from rest_framework.routers import DefaultRouter

from .views import CourseMaterialViewSet, CourseViewSet

router = DefaultRouter()
router.register('courses', CourseViewSet, basename='course')
router.register('course-materials', CourseMaterialViewSet, basename='coursematerial')

urlpatterns = router.urls
