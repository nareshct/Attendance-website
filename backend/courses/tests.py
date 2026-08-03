from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from .models import Course
from .serializers import CourseSerializer
from .views import CourseViewSet


class CourseHardDeleteBlockedTests(APITestCase):
    """Courses are never hard-deleted — see CourseViewSet.http_method_names."""

    def test_delete_is_not_allowed(self):
        admin = get_user_model().objects.create_user(username='admin_no_delete_course', password='x', is_staff=True)
        course = Course.objects.create(name='Keep Me', total_classes=24, rate_per_class=Decimal('1000'))
        factory = APIRequestFactory()

        request = factory.delete(f'/api/courses/{course.id}/')
        force_authenticate(request, user=admin)
        response = CourseViewSet.as_view({'delete': 'destroy'})(request, pk=course.id)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Course.objects.filter(id=course.id).exists())


class CourseTrainerAccessTests(APITestCase):
    """Trainers can read the course list (e.g. to filter Course Materials by
    course) but can't create/edit/delete — see CourseViewSet.get_permissions().
    """

    def setUp(self):
        from trainers.models import Trainer

        self.factory = APIRequestFactory()
        trainer_user = get_user_model().objects.create_user(username='course_trainer', password='x')
        self.trainer = Trainer.objects.create(
            user=trainer_user, name='T', phone_number='0000000000', place='Here', default_rate_per_class=Decimal('100'),
        )
        self.course = Course.objects.create(name='Course', total_classes=24, rate_per_class=Decimal('1000'))

    def test_trainer_can_list_courses(self):
        request = self.factory.get('/api/courses/')
        force_authenticate(request, user=self.trainer.user)
        response = CourseViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)

    def test_trainer_cannot_create_a_course(self):
        request = self.factory.post('/api/courses/', {'name': 'New', 'total_classes': 24, 'rate_per_class': '500'})
        force_authenticate(request, user=self.trainer.user)
        response = CourseViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 403)


class CourseRateValidationTests(APITestCase):
    def test_negative_rate_per_class_is_rejected(self):
        serializer = CourseSerializer(data={'name': 'Bad Course', 'total_classes': 24, 'rate_per_class': '-500.00'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('rate_per_class', serializer.errors)

    def test_zero_total_classes_is_rejected(self):
        serializer = CourseSerializer(data={'name': 'Bad Course', 'total_classes': 0, 'rate_per_class': '500.00'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('total_classes', serializer.errors)
