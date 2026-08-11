import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from .models import Course, CourseMaterial
from .serializers import CourseSerializer
from .views import CourseMaterialViewSet, CourseViewSet


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

    def test_trainer_does_not_see_rate_per_class(self):
        # rate_per_class is the B2C price list — billing data a trainer has no reason
        # to see, even though they need list access for the Course Materials filter.
        request = self.factory.get('/api/courses/')
        force_authenticate(request, user=self.trainer.user)
        response = CourseViewSet.as_view({'get': 'list'})(request)
        self.assertNotIn('rate_per_class', response.data['results'][0])

    def test_admin_still_sees_rate_per_class(self):
        admin = get_user_model().objects.create_user(username='course_admin', password='x', is_staff=True)
        request = self.factory.get('/api/courses/')
        force_authenticate(request, user=admin)
        response = CourseViewSet.as_view({'get': 'list'})(request)
        self.assertIn('rate_per_class', response.data['results'][0])

    def test_trainer_cannot_create_a_course(self):
        request = self.factory.post('/api/courses/', {'name': 'New', 'total_classes': 24, 'rate_per_class': '500'})
        force_authenticate(request, user=self.trainer.user)
        response = CourseViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 403)


class CourseRateChangeAuditLogTests(APITestCase):
    """Course.rate_per_class edits are money-affecting (feed every B2C billing
    calculation) — see log_rate_change()'s RateHistory trail, which has no actor field.
    CourseViewSet.perform_update fills that gap with a real audit log entry."""

    def setUp(self):
        from audit.models import AuditLog

        self.AuditLog = AuditLog
        self.admin = get_user_model().objects.create_user(username='course_rate_audit_admin', password='x', is_staff=True)
        self.course = Course.objects.create(name='Rate Audit Course', total_classes=24, rate_per_class=Decimal('500'))
        self.factory = APIRequestFactory()

    def test_changing_the_rate_writes_an_audit_log_entry(self):
        request = self.factory.patch(f'/api/courses/{self.course.id}/', {'rate_per_class': '750.00'}, format='json')
        force_authenticate(request, user=self.admin)
        response = CourseViewSet.as_view({'patch': 'partial_update'})(request, pk=self.course.id)
        self.assertEqual(response.status_code, 200, response.data)
        entry = self.AuditLog.objects.get(action='course_rate_change', object_repr='Rate Audit Course')
        self.assertIn('500', entry.detail)
        self.assertIn('750', entry.detail)
        self.assertEqual(entry.actor_id, self.admin.id)

    def test_editing_without_changing_the_rate_writes_nothing(self):
        request = self.factory.patch(f'/api/courses/{self.course.id}/', {'name': 'Renamed Course'}, format='json')
        force_authenticate(request, user=self.admin)
        response = CourseViewSet.as_view({'patch': 'partial_update'})(request, pk=self.course.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(self.AuditLog.objects.filter(action='course_rate_change').exists())


class CourseRateValidationTests(APITestCase):
    def test_negative_rate_per_class_is_rejected(self):
        serializer = CourseSerializer(data={'name': 'Bad Course', 'total_classes': 24, 'rate_per_class': '-500.00'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('rate_per_class', serializer.errors)

    def test_zero_total_classes_is_rejected(self):
        serializer = CourseSerializer(data={'name': 'Bad Course', 'total_classes': 0, 'rate_per_class': '500.00'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('total_classes', serializer.errors)


class CourseMaterialFileSizeValidationTests(APITestCase):
    """Django has no built-in file-size validator, so this is a custom one —
    see courses.models.validate_course_material_size / MAX_COURSE_MATERIAL_SIZE.
    Without it, an upload had no server-side size limit at all.
    """

    def test_oversized_file_is_rejected(self):
        from .models import MAX_COURSE_MATERIAL_SIZE

        course = Course.objects.create(name='Size Course', total_classes=24, rate_per_class=Decimal('500'))
        oversized = SimpleUploadedFile(
            'huge.pdf', b'%PDF-1.4 ' + b'x' * (MAX_COURSE_MATERIAL_SIZE + 1), content_type='application/pdf',
        )
        from .serializers import CourseMaterialSerializer

        serializer = CourseMaterialSerializer(data={'course': course.id, 'title': 'Huge', 'file': oversized})
        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    def test_normal_sized_file_is_accepted(self):
        course = Course.objects.create(name='Size Course Ok', total_classes=24, rate_per_class=Decimal('500'))
        small = SimpleUploadedFile('small.pdf', b'%PDF-1.4 fake', content_type='application/pdf')
        from .serializers import CourseMaterialSerializer

        serializer = CourseMaterialSerializer(data={'course': course.id, 'title': 'Small', 'file': small})
        self.assertTrue(serializer.is_valid(), serializer.errors)


class CourseMaterialTrainerScopingTests(APITestCase):
    """A trainer only sees/downloads materials for courses they actually have
    some current tie to — their own enrollments, a batch they're on, or a
    course they're substitute-covering. See CourseMaterialViewSet.get_queryset().
    """

    def setUp(self):
        from enrollments.models import Enrollment
        from students.models import Student
        from trainers.models import Trainer

        self.factory = APIRequestFactory()
        trainer_user = get_user_model().objects.create_user(username='material_scope_trainer', password='x')
        self.trainer = Trainer.objects.create(
            user=trainer_user, name='Material Trainer', phone_number='0000000000', place='Here',
            default_rate_per_class=Decimal('100'),
        )
        self.my_course = Course.objects.create(name='My Course', total_classes=24, rate_per_class=Decimal('500'))
        self.other_course = Course.objects.create(name='Other Course', total_classes=24, rate_per_class=Decimal('500'))
        student = Student.objects.create(name='Kid', grade='5', source_type='B2C')
        Enrollment.objects.create(
            student=student, course=self.my_course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )

        def _pdf(name):
            return SimpleUploadedFile(name, b'%PDF-1.4 fake', content_type='application/pdf')

        self.my_material = CourseMaterial.objects.create(course=self.my_course, title='Mine', file=_pdf('mine.pdf'))
        self.other_material = CourseMaterial.objects.create(course=self.other_course, title='Not mine', file=_pdf('other.pdf'))

    def test_trainer_only_sees_materials_for_their_own_courses(self):
        request = self.factory.get('/api/course-materials/')
        force_authenticate(request, user=self.trainer.user)
        response = CourseMaterialViewSet.as_view({'get': 'list'})(request)

        titles = [row['title'] for row in response.data['results']]
        self.assertIn('Mine', titles)
        self.assertNotIn('Not mine', titles)

    def test_trainer_cannot_download_a_material_for_a_course_they_do_not_teach(self):
        request = self.factory.get(f'/api/course-materials/{self.other_material.id}/download/')
        force_authenticate(request, user=self.trainer.user)
        response = CourseMaterialViewSet.as_view({'get': 'download'})(request, pk=self.other_material.id)

        self.assertEqual(response.status_code, 404)

    def test_admin_sees_every_material(self):
        admin = get_user_model().objects.create_user(username='material_scope_admin', password='x', is_staff=True)
        request = self.factory.get('/api/course-materials/')
        force_authenticate(request, user=admin)
        response = CourseMaterialViewSet.as_view({'get': 'list'})(request)

        titles = [row['title'] for row in response.data['results']]
        self.assertIn('Mine', titles)
        self.assertIn('Not mine', titles)


class CourseMaterialInvalidCourseFilterTests(APITestCase):
    """?course= previously went straight into a queryset filter with no validation —
    a non-numeric value raised an unhandled ValueError (500) instead of a clean 400."""

    def test_non_numeric_course_filter_returns_400_not_a_500(self):
        admin = get_user_model().objects.create_user(username='material_filter_admin', password='x', is_staff=True)
        factory = APIRequestFactory()
        request = factory.get('/api/course-materials/?course=not-a-number')
        force_authenticate(request, user=admin)
        response = CourseMaterialViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 400)
