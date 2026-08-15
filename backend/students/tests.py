from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from audit.models import AuditLog
from batches.models import Batch, BatchEnrollment
from clients.models import Client
from courses.models import Course
from enrollments.models import Enrollment, PaymentInstallment, PaymentPlan
from trainers.models import Trainer

from .models import ParentShareLink, Student
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

    def test_reports_active_batch_enrollment(self):
        admin = get_user_model().objects.create_user(username='admin_student_blockers_batch', password='x', is_staff=True)
        course = Course.objects.create(name='Blockers Batch Course', total_classes=10)
        batch = Batch.objects.create(
            name='Blockers Batch', course=course, total_classes=10, fee_per_student=Decimal('1000'),
            start_date=timezone.localdate(),
        )
        student = Student.objects.create(name='Batch Blocked Student', grade='5', source_type='B2C')
        BatchEnrollment.objects.create(batch=batch, student=student, status='active', joined_date=timezone.localdate())

        factory = APIRequestFactory()
        request = factory.get(f'/api/students/{student.id}/archive-blockers/')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'get': 'archive_blockers'})(request, pk=student.id)

        self.assertEqual(len(response.data['active_batch_enrollments']), 1)
        self.assertEqual(response.data['active_batch_enrollments'][0]['batch_name'], 'Blockers Batch')
        self.assertEqual(response.data['active_batch_enrollments'][0]['course_name'], 'Blockers Batch Course')

    def test_reports_nothing_for_a_clean_student(self):
        admin = get_user_model().objects.create_user(username='admin_student_blockers_clean', password='x', is_staff=True)
        student = Student.objects.create(name='Clean Student', grade='5', source_type='B2C')

        factory = APIRequestFactory()
        request = factory.get(f'/api/students/{student.id}/archive-blockers/')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'get': 'archive_blockers'})(request, pk=student.id)

        self.assertEqual(response.data['ongoing_enrollments'], [])
        self.assertEqual(response.data['active_batch_enrollments'], [])
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

    def test_active_batch_enrollment_blocks_archive(self):
        admin = get_user_model().objects.create_user(username='admin_student_archive_batch_block', password='x', is_staff=True)
        course = Course.objects.create(name='Batch Block Course', total_classes=10)
        batch = Batch.objects.create(
            name='Block Batch', course=course, total_classes=10, fee_per_student=Decimal('1000'),
            start_date=timezone.localdate(),
        )
        student = Student.objects.create(name='In A Batch', grade='5', source_type='B2C')
        BatchEnrollment.objects.create(batch=batch, student=student, status='active', joined_date=timezone.localdate())

        response = self._archive(student, admin)

        self.assertEqual(response.status_code, 400)
        student.refresh_from_db()
        self.assertEqual(student.status, 'active')

    def test_withdrawn_batch_enrollment_does_not_block(self):
        admin = get_user_model().objects.create_user(username='admin_student_archive_batch_ok', password='x', is_staff=True)
        course = Course.objects.create(name='Batch Clean Course', total_classes=10)
        batch = Batch.objects.create(
            name='Clean Batch', course=course, total_classes=10, fee_per_student=Decimal('1000'),
            start_date=timezone.localdate(),
        )
        student = Student.objects.create(name='Left The Batch', grade='5', source_type='B2C')
        BatchEnrollment.objects.create(batch=batch, student=student, status='withdrawn', joined_date=timezone.localdate())

        response = self._archive(student, admin)

        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.status, 'archived')

    def test_archive_and_unarchive_are_written_to_the_audit_log(self):
        admin = get_user_model().objects.create_user(username='admin_student_archive_audit', password='x', is_staff=True)
        student = Student.objects.create(name='Audited Student', grade='5', source_type='B2C')

        self._archive(student, admin)
        factory = APIRequestFactory()
        request = factory.post(f'/api/students/{student.id}/unarchive/')
        force_authenticate(request, user=admin)
        StudentViewSet.as_view({'post': 'unarchive'})(request, pk=student.id)

        actions = list(AuditLog.objects.values_list('action', flat=True))
        self.assertIn('student_archive', actions)
        self.assertIn('student_unarchive', actions)


class StudentSourceTypeClientChangeGuardTests(APITestCase):
    """billing/services.py reads student.source_type live, not a per-enrollment
    snapshot — changing source_type or client while an enrollment is actively being
    billed would silently change how it bills without reconciling the existing
    PaymentPlan/client rate. Same hard-block condition as StudentViewSet.archive()."""

    def _patch(self, student, admin, **body):
        factory = APIRequestFactory()
        request = factory.patch(f'/api/students/{student.id}/', body, format='json')
        force_authenticate(request, user=admin)
        return StudentViewSet.as_view({'patch': 'partial_update'})(request, pk=student.id)

    def test_cannot_change_source_type_with_an_ongoing_enrollment(self):
        admin = get_user_model().objects.create_user(username='admin_source_type_guard', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='trainer_source_type_guard', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='Guard Trainer', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        course = Course.objects.create(name='Guard Course', total_classes=10)
        student = Student.objects.create(name='Guarded B2C', grade='5', source_type='B2C')
        Enrollment.objects.create(student=student, course=course, trainer=trainer, start_date=timezone.localdate(), status='ongoing')

        client_obj = Client.objects.create(company_name='Guard Co', contact_phone='123', rate_per_class=Decimal('200'))
        response = self._patch(student, admin, source_type='B2B', client=client_obj.id)

        self.assertEqual(response.status_code, 400)
        student.refresh_from_db()
        self.assertEqual(student.source_type, 'B2C')

    def test_cannot_change_client_with_an_active_batch_enrollment(self):
        admin = get_user_model().objects.create_user(username='admin_client_change_guard', password='x', is_staff=True)
        course = Course.objects.create(name='Guard Batch Course', total_classes=10)
        batch = Batch.objects.create(
            name='Guard Batch', course=course, total_classes=10, fee_per_student=Decimal('1000'),
            start_date=timezone.localdate(),
        )
        original_client = Client.objects.create(company_name='Original Co', contact_phone='123', rate_per_class=Decimal('200'))
        student = Student.objects.create(name='Guarded B2B', grade='5', source_type='B2B', client=original_client)
        BatchEnrollment.objects.create(batch=batch, student=student, status='active', joined_date=timezone.localdate())

        new_client = Client.objects.create(company_name='New Co', contact_phone='456', rate_per_class=Decimal('250'))
        response = self._patch(student, admin, client=new_client.id)

        self.assertEqual(response.status_code, 400)
        student.refresh_from_db()
        self.assertEqual(student.client_id, original_client.id)

    def test_can_change_source_type_once_nothing_is_active(self):
        admin = get_user_model().objects.create_user(username='admin_source_type_ok', password='x', is_staff=True)
        student = Student.objects.create(name='Free To Change', grade='5', source_type='B2C')

        client_obj = Client.objects.create(company_name='Free Co', contact_phone='123', rate_per_class=Decimal('200'))
        response = self._patch(student, admin, source_type='B2B', client=client_obj.id)

        self.assertEqual(response.status_code, 200, response.data)
        student.refresh_from_db()
        self.assertEqual(student.source_type, 'B2B')
        self.assertEqual(student.client_id, client_obj.id)

    def test_unrelated_field_edit_is_unaffected_by_the_guard(self):
        admin = get_user_model().objects.create_user(username='admin_unrelated_edit', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='trainer_unrelated_edit', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='Unrelated Trainer', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        course = Course.objects.create(name='Unrelated Course', total_classes=10)
        student = Student.objects.create(name='Old Name', grade='5', source_type='B2C')
        Enrollment.objects.create(student=student, course=course, trainer=trainer, start_date=timezone.localdate(), status='ongoing')

        response = self._patch(student, admin, name='New Name')

        self.assertEqual(response.status_code, 200, response.data)
        student.refresh_from_db()
        self.assertEqual(student.name, 'New Name')


class StudentB2CCannotHaveClientTests(APITestCase):
    """The inverse of B2B's 'client is required' rule — client-scoped billing
    (clients/services.py client_totals) and the client portal both filter purely by
    student.client_id, not source_type, so a B2C student left with a client set would
    bleed into that client's billing/portal. See StudentSerializer.validate()."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_b2c_client_guard', password='x', is_staff=True)
        self.client_obj = Client.objects.create(company_name='B2C Guard Co', contact_phone='123', rate_per_class=Decimal('200'))
        self.factory = APIRequestFactory()

    def test_cannot_create_a_b2c_student_with_a_client(self):
        request = self.factory.post('/api/students/', {
            'name': 'B2C With Client', 'grade': '5', 'source_type': 'B2C', 'client': self.client_obj.id,
        }, format='json')
        force_authenticate(request, user=self.admin)
        response = StudentViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Student.objects.filter(name='B2C With Client').exists())

    def test_cannot_patch_a_b2c_student_to_add_a_client(self):
        student = Student.objects.create(name='B2C No Client', grade='5', source_type='B2C')
        request = self.factory.patch(f'/api/students/{student.id}/', {'client': self.client_obj.id}, format='json')
        force_authenticate(request, user=self.admin)
        response = StudentViewSet.as_view({'patch': 'partial_update'})(request, pk=student.id)
        self.assertEqual(response.status_code, 400)
        student.refresh_from_db()
        self.assertIsNone(student.client_id)

    def test_b2c_student_with_no_client_is_still_valid(self):
        request = self.factory.post('/api/students/', {
            'name': 'Plain B2C', 'grade': '5', 'source_type': 'B2C',
        }, format='json')
        force_authenticate(request, user=self.admin)
        response = StudentViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 201, response.data)


class StudentListInvalidClientFilterTests(APITestCase):
    """A non-numeric ?client= previously went straight into a queryset filter with no
    validation, raising an unhandled ValueError (500) instead of a clean 400."""

    def test_rejects_a_malformed_client_filter(self):
        admin = get_user_model().objects.create_user(username='admin_bad_student_client_filter', password='x', is_staff=True)
        request = APIRequestFactory().get('/api/students/?client=abc')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 400)


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


class ProfileIncludesBatchEnrollmentsTests(APITestCase):
    """A student can be in both a 1:1 Enrollment and a group Batch at once — the
    profile page's admin view shows both, see StudentViewSet.profile."""

    def test_admin_profile_includes_batch_enrollments(self):
        from decimal import Decimal as D

        from batches.models import Batch, BatchEnrollment
        from batches.services import create_batch_installments

        admin = get_user_model().objects.create_user(username='admin_profile_batches', password='x', is_staff=True)
        course = Course.objects.create(name='Robotics', total_classes=10)
        student = Student.objects.create(name='Batch Kid', grade='6', source_type='B2C')
        batch = Batch.objects.create(
            name='Robotics — August batch', course=course, total_classes=10,
            fee_per_student=D('4000'), payment_type='one_time', start_date=timezone.localdate(),
        )
        enrollment = BatchEnrollment.objects.create(batch=batch, student=student, joined_date=timezone.localdate())
        create_batch_installments(enrollment)

        factory = APIRequestFactory()
        request = factory.get(f'/api/students/{student.id}/profile/')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'get': 'profile'})(request, pk=student.id)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['batch_enrollments']), 1)
        row = response.data['batch_enrollments'][0]
        self.assertEqual(row['batch_name'], 'Robotics — August batch')
        self.assertEqual(row['course_name'], 'Robotics')
        self.assertEqual(row['status'], 'active')
        self.assertEqual(len(row['installments']), 1)

    def test_trainer_profile_view_does_not_include_batch_enrollments(self):
        # Trainer visibility for batches isn't implemented — batches don't have a
        # single owning trainer the way a 1:1 Enrollment does (trainer_names is
        # free text, can be co-taught), so this stays admin-only for now.
        from decimal import Decimal as D

        from batches.models import Batch, BatchEnrollment
        from courses.models import Course as CourseModel

        trainer_user = get_user_model().objects.create_user(username='trainer_profile_batches', password='x')
        trainer = Trainer.objects.create(
            user=trainer_user, name='T Batches', phone_number='1', place='X', default_rate_per_class=Decimal('100'),
        )
        course = CourseModel.objects.create(name='Robotics', total_classes=10)
        batch_course = CourseModel.objects.create(name='Robotics Batch Course', total_classes=10)
        student = Student.objects.create(name='Batch Kid Two', grade='6', source_type='B2C')
        Enrollment.objects.create(
            student=student, course=course, trainer=trainer, start_date=timezone.localdate(), status='ongoing',
        )
        batch = Batch.objects.create(
            name='Robotics — August batch 2', course=batch_course, total_classes=10,
            fee_per_student=D('4000'), payment_type='one_time', start_date=timezone.localdate(),
        )
        BatchEnrollment.objects.create(batch=batch, student=student, joined_date=timezone.localdate())

        factory = APIRequestFactory()
        request = factory.get(f'/api/students/{student.id}/profile/')
        force_authenticate(request, user=trainer_user)
        response = StudentViewSet.as_view({'get': 'profile'})(request, pk=student.id)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('batch_enrollments', response.data)


class RegenerateParentLinkTests(APITestCase):
    """regenerate_parent_link previously did a separate delete() then create() —
    since `student` is a OneToOneField, two near-simultaneous regenerate clicks
    racing that could 500 on the unique constraint instead of cleanly
    regenerating. Now updates the existing row in place (or creates one if
    none exists) as a single operation. See StudentViewSet.regenerate_parent_link.
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_regen_link', password='x', is_staff=True)
        self.factory = APIRequestFactory()

    def _regenerate(self, student_id):
        request = self.factory.post(f'/api/students/{student_id}/regenerate_parent_link/')
        force_authenticate(request, user=self.admin)
        return StudentViewSet.as_view({'post': 'regenerate_parent_link'})(request, pk=student_id)

    def test_creates_a_link_when_none_exists_yet(self):
        student = Student.objects.create(name='No Link Yet', grade='5', source_type='B2C')
        response = self._regenerate(student.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ParentShareLink.objects.filter(student=student).count(), 1)

    def test_regenerating_changes_the_token_without_creating_a_second_row(self):
        student = Student.objects.create(name='Has Link', grade='5', source_type='B2C')
        original = ParentShareLink.objects.create(student=student)
        response = self._regenerate(student.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ParentShareLink.objects.filter(student=student).count(), 1)
        link = ParentShareLink.objects.get(student=student)
        self.assertEqual(link.pk, original.pk)
        self.assertNotEqual(str(link.token), str(original.token))

    def test_regenerating_a_revoked_link_makes_it_usable_again(self):
        student = Student.objects.create(name='Revoked Link', grade='5', source_type='B2C')
        ParentShareLink.objects.create(student=student, revoked=True)
        response = self._regenerate(student.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['revoked'])
