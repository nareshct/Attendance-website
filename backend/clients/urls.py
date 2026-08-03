from rest_framework.routers import DefaultRouter

from .views import ClientContactViewSet, ClientCourseRateViewSet, ClientViewSet

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='client')
router.register('client-rates', ClientCourseRateViewSet, basename='client-rate')
router.register('client-contacts', ClientContactViewSet, basename='client-contact')

urlpatterns = router.urls
