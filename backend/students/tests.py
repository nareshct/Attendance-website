from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from courses.models import Course
from enrollments.models import Enrollment, PaymentInstallment, PaymentPlan
from trainers.models import Trainer

from .models import Student
from .views import StudentViewSet


class StudentSearchTests(APITestCase):
    """?search= must match name OR student_id server-side (see
    StudentViewSet.search_fields), so a match is found regardless of which
    page it would otherwise fall on — the bug this replaced was client-side
    filtering over only the first loaded page.
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_search_student', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        self.target = Student.objects.create(name='Ishani Warrier', grade='5', source_type='B2C')
        Student.objects.create(name='Someone Else', grade='6', source_type='B2C')

    def _search(self, term):
        request = self.factory.get(f'/api/students/?search={term}')
        force_authenticate(request, user=self.admin)
        return StudentViewSet.as_view({'get': 'list'})(request)

    def test_search_by_name_finds_the_student(self):
        response = self._search('warrier')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Ishani Warrier'])

    def test_search_by_student_id_finds_the_student(self):
        response = self._search(self.target.student_id)
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Ishani Warrier'])

    def test_search_is_case_insensitive_and_partial(self):
        response = self._search('ISHA')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Ishani Warrier'])


class StudentHardDeleteBlockedTests(APITestCase):
    """Students are only ever archived, never hard-deleted — see
    StudentViewSet.http_method_names and the archive/unarchive actions.
    """

    def test_delete_is_not_allowed(self):
        admin = get_user_model().objects.create_user(username='admin_no_delete_student', password='x', is_staff=True)
        student = Student.objects.create(name='Keep Me', grade='5', source_type='B2C')
        factory = APIRequestFactory()

        request = factory.delete(f'/api/students/{student.id}/')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'delete': 'destroy'})(request, pk=student.id)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Student.objects.filter(id=student.id).exists())


class StudentArchiveBlockersTests(APITestCase):
    """Checklist shown in ArchiveStudentModal before confirming — see
    StudentViewSet.archive_blockers. ongoing_enrollments also hard-blocks
    archive() itself (see StudentArchiveHardBlockTests below); pending_
    installments is informational only.
    """

    def test_reports_ongoing_enrollment_and_pending_installment(self):
        admin = get_user_model().objects.create_user(username='admin_student_blockers', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='trainer_student_blockers', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='T One', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        course = Course.objects.create(name='Blockers Course', total_classes=10)
        student = Student.objects.create(name='Blocked Student', grade='5', source_type='B2C')
        enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=trainer, start_date=timezone.localdate(), status='ongoing',
        )
        plan = PaymentPlan.objects.create(enrollment=enrollment, plan_type='two_installments', total_amount=Decimal('5000.00'))
        PaymentInstallment.objects.create(plan=plan, sequence=1, due_at_classes=None, amount=Decimal('2000.00'), paid_status='pending')

        factory = APIRequestFactory()
        request = factory.get(f'/api/students/{student.id}/archive-blockers/')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'get': 'archive_blockers'})(request, pk=student.id)

        self.assertEqual(len(response.data['ongoing_enrollments']), 1)
        self.assertEqual(response.data['ongoing_enrollments'][0]['course_name'], 'Blockers Course')
        self.assertEqual(len(response.data['pending_installments']), 1)
        self.assertEqual(response.data['pending_installments'][0]['amount'], Decimal('2000.00'))

    def test_reports_nothing_for_a_clean_student(self):
        admin = get_user_model().objects.create_user(username='admin_student_blockers_clean', password='x', is_staff=True)
        student = Student.objects.create(name='Clean Student', grade='5', source_type='B2C')

        factory = APIRequestFactory()
        request = factory.get(f'/api/students/{student.id}/archive-blockers/')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'get': 'archive_blockers'})(request, pk=student.id)

        self.assertEqual(response.data['ongoing_enrollments'], [])
        self.assertEqual(response.data['pending_installments'], [])


class StudentArchiveHardBlockTests(APITestCase):
    """archive() must refuse a student with an ongoing enrollment (mirroring
    TrainerViewSet.archive/ClientViewSet.archive) — see StudentViewSet.archive.
    A withdrawn/completed enrollment, or an unpaid installment on one, must
    NOT block: withdrawing already auto-cancels any pending installment tied
    to it, so there's nothing left to resolve once nothing is ongoing.
    """

    def _archive(self, student, admin):
        factory = APIRequestFactory()
        request = factory.post(f'/api/students/{student.id}/archive/')
        force_authenticate(request, user=admin)
        return StudentViewSet.as_view({'post': 'archive'})(request, pk=student.id)

    def test_ongoing_enrollment_blocks_archive(self):
        admin = get_user_model().objects.create_user(username='admin_student_archive_block', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='trainer_student_archive_block', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='T Two', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        course = Course.objects.create(name='Block Course', total_classes=10)
        student = Student.objects.create(name='Has Ongoing', grade='5', source_type='B2C')
        Enrollment.objects.create(student=student, course=course, trainer=trainer, start_date=timezone.localdate(), status='ongoing')

        response = self._archive(student, admin)

        self.assertEqual(response.status_code, 400)
        student.refresh_from_db()
        self.assertEqual(student.status, 'active')

    def test_withdrawn_enrollment_with_cancelled_installment_does_not_block(self):
        admin = get_user_model().objects.create_user(username='admin_student_archive_ok', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='trainer_student_archive_ok', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='T Three', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        course = Course.objects.create(name='Clean Course', total_classes=10)
        student = Student.objects.create(name='All Clear', grade='5', source_type='B2C')
        enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=trainer, start_date=timezone.localdate(), status='withdrawn',
        )
        plan = PaymentPlan.objects.create(enrollment=enrollment, plan_type='two_installments', total_amount=Decimal('5000.00'))
        PaymentInstallment.objects.create(plan=plan, sequence=1, due_at_classes=None, amount=Decimal('2000.00'), paid_status='cancelled')

        response = self._archive(student, admin)

        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.status, 'archived')


class StudentProfileHiddenFromTrainerWhenArchivedTests(APITestCase):
    """A trainer shouldn't be able to reach an archived student's profile
    directly (e.g. a stale bookmark) any more than they can find them listed
    in My Students — see StudentViewSet.profile().
    """

    def test_trainer_cannot_view_an_archived_students_profile(self):
        trainer_user = get_user_model().objects.create_user(username='trainer_archived_profile', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='T Four', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        course = Course.objects.create(name='Profile Course', total_classes=10)
        student = Student.objects.create(name='Archived Kid', grade='5', source_type='B2C', status='archived')
        Enrollment.objects.create(
            student=student, course=course, trainer=trainer, start_date=timezone.localdate(), status='completed',
        )

        factory = APIRequestFactory()
        request = factory.get(f'/api/students/{student.id}/profile/')
        force_authenticate(request, user=trainer_user)
        response = StudentViewSet.as_view({'get': 'profile'})(request, pk=student.id)

        self.assertEqual(response.status_code, 404)

    def test_admin_can_still_view_an_archived_students_profile(self):
        admin = get_user_model().objects.create_user(username='admin_archived_profile', password='x', is_staff=True)
        student = Student.objects.create(name='Archived Kid Admin View', grade='5', source_type='B2C', status='archived')

        factory = APIRequestFactory()
        request = factory.get(f'/api/students/{student.id}/profile/')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'get': 'profile'})(request, pk=student.id)

        self.assertEqual(response.status_code, 200)
